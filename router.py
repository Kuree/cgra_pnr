from __future__ import print_function, division
from arch.cgra import parse_placement, save_routing_result
from arch.cgra_packer import load_packed_file
from arch.cgra import determine_pin_ports
from arch.cgra_route import parse_routing_resource, build_routing_resource
from arch import parse_cgra
import sys
import os
import numpy as np
from visualize import draw_board, draw_cell
import matplotlib.pyplot as plt
from util import parse_args, deepcopy


class Router:
    def __init__(self, cgra_filename,
                 board_meta, packed_filename, placement_filename,
                 avoid_congestion=True):
        self.board_meta = board_meta
        self.layout_board = board_meta[0]
        netlists, _, id_to_name, = load_packed_file(packed_filename)
        self.id_to_name = id_to_name
        self.netlists = netlists

        placement, _ = parse_placement(placement_filename)
        self.placement = placement

        board_info = board_meta[-1]
        width = board_info["width"]
        height = board_info["height"]
        self.margin = board_info["margin"]

        # NOTE: it's width x height
        self.board_size = (width, height)
        # TODO: fix this after parsing routing info from the arch
        self.channel_width = 5

        # result
        self.route_result = {}

        print("Building routing resurce")
        r = parse_routing_resource(cgra_filename)
        self.routing_resource = build_routing_resource(r)

        self.avoid_congestion = avoid_congestion

        base_filename = os.path.basename(packed_filename)
        design_name, _ = os.path.splitext(base_filename)
        self.design_name = design_name

    @staticmethod
    def manhattan_dist(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

    def compute_direction(self, src, dst):
        """ right -> 0 bottom -> 1 left -> 2 top -> 3 and mem is a special
            case"""
        assert (src != dst)
        x1, y1 = src
        x2, y2 = dst
        assert ((abs(x1 - x2) == 0 and abs(y1 - y2) == 1) or (
                    abs(x1 - x2) == 1
                    and abs(y1 - y2)
                    == 0))
        direction = -1
        if x1 == x2:
            if y2 > y1:
                direction = 1
            else:
                direction = 3
        if y1 == y2:
            if x2 > x1:
                direction = 0
            else:
                direction = 2
        else:
            Exception("direction error " + "{}->{}".format(src, dst))

        # if the current position is in the middle of a special
        # FIXME: use the height to compute
        if self.layout_board[y1][x1] is None and y1 > self.margin and \
                self.layout_board[y1 - 1][x1] == "m":
            direction += 4

        return direction

    def heuristic_dist(self, depth, pos, dst, bus):
        if len(pos) == 3:
            pos, _, _ = pos
        x, y = pos
        dist = abs(x - dst[0]) + abs(y - dst[1]) + depth[(x, y)]
        if self.avoid_congestion and (y, x) in self.routing_resource:
            route_resource = self.routing_resource[(y, x)]["route_resource"]
            available_res_bus = len([x for x in route_resource if x[0][0] ==
                                     bus])
            if available_res_bus == 0:
                extra = 100 # a large number
            else:
                extra = 20 / available_res_bus
            extra = 0
            dist += extra
        return dist

    def get_port_neighbors(self, routing_resource, bus, chan, pos, port):
        port_chan = routing_resource[pos]["port"][port]
        x, y = pos
        results = []
        working_set = set()
        # hard coded the pos for now
        x_max = min(self.board_size[0] - 1, x + 1)
        x_min = max(0, x - 1)
        y_max = min(self.board_size[1] - 1, y + 1)
        y_min = max(0, y - 1)
        working_set.add((x, y_max))
        working_set.add((x, y_min))
        working_set.add((x_min, y))
        working_set.add((x_max, y))
        # remove itself, if there is any
        if pos in working_set:
            working_set.remove(pos)

        board_layout = self.board_meta[0]
        is_io = board_layout[pos[1]][pos[0]] == "i"
        for new_pos in working_set:
            out_direction = self.compute_direction(pos, new_pos)
            in_direction = self.compute_direction(new_pos, pos)
            route_resource_current_pos2 = self.get_route_resource(
                self.board_meta,
                routing_resource,
                new_pos)
            # check if out is okay
            dir_out = (bus, 1, out_direction, chan)
            dir_in = (bus, 0, in_direction, chan)
            if is_io:
                if dir_out in port_chan:
                    results.append((new_pos, dir_out, dir_in))
            else:
                if dir_out in port_chan:
                    can_turn = False
                    for conn_in, conn_out in route_resource_current_pos2:
                        if conn_out == dir_out:
                            can_turn = True
                            break
                    if can_turn:
                        results.append((new_pos, dir_out, dir_in))
        return results

    @staticmethod
    def get_route_resource(board_meta, routing_resource, pos):
        # FIXME: use height for searching
        if pos not in routing_resource:
            # FIXME: use height for searching
            pos_fixed = (pos[0], pos[1] - 1)
            assert(board_meta[0][pos_fixed[1]][pos_fixed[0]] == "m")
            return routing_resource[pos_fixed]["route_resource"]
        else:
            return routing_resource[pos]["route_resource"]

    @staticmethod
    def get_port_resource(board_meta, routing_resource, pos):
        # FIXME: use height for searching
        if pos not in routing_resource:
            # FIXME: use height for searching
            pos_fixed = (pos[0], pos[1] - 1)
            assert (board_meta[0][pos_fixed[1]][pos_fixed[0]] == "m")
            return routing_resource[pos_fixed]["port"]
        else:
            return routing_resource[pos]["port"]

    def get_neighbors(self, routing_resource, bus, chan, pos, track_in,
                      pin_ports):
        # tricky in the current CGRA design:
        # if pos is in the bottom of a MEM tile, it won't have an entry
        route_resource_current_pos = self.get_route_resource(self.board_meta,
                                                             routing_resource,
                                                             pos)
        # just needs to pos, the later logic will handle the connection to
        # the port
        pin_pos = set()
        for pp, _ in pin_ports:
            pin_pos.add(pp)
        x, y = pos
        results = []
        working_set = set()
        # hard coded the pos for now
        x_max = min(self.board_size[0] - 1, x + 1)
        x_min = max(0, x - 1)
        y_max = min(self.board_size[1] - 1, y + 1)
        y_min = max(0, y - 1)
        working_set.add((x, y_max))
        working_set.add((x, y_min))
        working_set.add((x_min, y))
        working_set.add((x_max, y))
        # remove itself, if there is any
        if pos in working_set:
            working_set.remove(pos)

        # another override for mem tile jumping
        # FIXME
        if self.layout_board[pos[1]][pos[0]] == "m" and \
                track_in[2] == 1:
            track_in = (track_in[0], 1, 7, track_in[-1])

        for new_pos in working_set:
            out_direction = self.compute_direction(pos, new_pos)
            route_resource_current_pos2 = self.get_route_resource(
                self.board_meta,
                routing_resource,
                new_pos)
            # check if out is okay
            dir_out = (bus, 1, out_direction, chan)
            in_direction = self.compute_direction(new_pos, pos)
            dir_in = (bus, 0, in_direction, chan)

            if self.layout_board[pos[1]][pos[0]] == "m" and \
                    dir_out[2] == 1:
                dir_out = (dir_out[0], dir_out[1], 7, dir_out[-1])

            if (track_in, dir_out) not in route_resource_current_pos:
                # can't make the turn
                continue
            can_turn = False
            if new_pos not in pin_pos:
                for conn_in, conn_out in route_resource_current_pos2:
                    if conn_in == dir_in:
                        can_turn = True
                        break
                if can_turn:
                    results.append((new_pos, dir_out, dir_in))
            else:
                results.append((new_pos, dir_out, dir_in))
        return results

    def is_pin_available(self, routing_resource,
                         pre_point, current_point, port, bus, chan,
                         is_self_connection=False):
        """returns True/False, [connection list + port]"""
        direction = self.compute_direction(current_point, pre_point)
        route_resource = routing_resource[current_point]["route_resource"]
        sink_resource = routing_resource[current_point]["port"]
        operand_channels = sink_resource[port]

        operand_channels = [entry for entry in operand_channels
                            if entry[-1] == chan]

        # test if we have direct connection to the operand
        # that is, in -> op
        dir_in = (bus, 0, direction, chan)

        if self.layout_board[current_point[1]][current_point[0]] == "m" and \
                dir_in[2] == 1:
            # make the dir in as dir_out from the bottom tile
            dir_in = (bus, 1, 7, chan)
        if dir_in in operand_channels:
            return True, [dir_in, current_point, port]


        # need to determine if we can connect to a out bus
        # that is, in_sxtx -> out_sxtx
        #          out_sxts -> op
        for conn in operand_channels:
            # the format in operand_channels is out -> in
            conn_chann = (dir_in, conn)
            if conn_chann in route_resource:
                return True, [dir_in, conn, current_point, port]
        if is_self_connection:
            # because we already remove the routing resource from the
            # routing resource, it won't be able to handle that
            # brute forcing to see if we can make the connection
            for i in range(4):
                dir_out = (bus, 1, i, chan)
                if dir_out in operand_channels:
                    return True, [dir_in, dir_out, current_point, port]
        return False, None

    @staticmethod
    def get_bus_type(net):
        for pos, port in net:
            # FIXME
            if "bit" in port or "en" in port:
                return 1
        return 16

    def copy_resource(self):
        res = deepcopy(self.routing_resource)
        return res

    @staticmethod
    def sort_netlist_id_for_io(netlist):
        netlist_ids = list(netlist.keys())
        def sort(nets):
            for blk_id, _ in nets:
                if blk_id[0] == "i":
                    return 0
            return 1
        netlist_ids.sort(key=lambda net_id: sort(netlist[net_id]))
        return netlist_ids

    @staticmethod
    def find_pre_pos(pos, path):
        for i in range(len(path) - 1, -1, -1):
            path_entry = path[i]
            # TODO: FIXME
            if isinstance(path_entry, list):
                # it could be src
                if not isinstance(path_entry[-1], str) and \
                        len(path_entry[0][0]) == 2:
                    pos1 = path_entry[0][0]
                    if pos1 != pos:
                        return pos1
                continue
            pos1 = path_entry[0][0]
            pos2 = path_entry[1][0]
            if pos2 != pos:
                return pos2
            if pos1 != pos:
                return pos1
        raise Exception("Unable to find pre pos for pos " + str(pos))

    @staticmethod
    def sort_net(net, placement):
        new_net = [net[0]]
        working_set = net[1:]
        for i in range(len(net) - 1):
            src_id, _ = new_net[-1]
            working_set.sort(key=lambda pin:
                             Router.manhattan_dist(placement[src_id],
                                                   placement[pin[0]]))
            new_net.append(working_set[0])
            working_set.pop(0)
        assert(len(net) == len(new_net))
        return new_net

    def route(self):
        print("INFO: Performing greedy BFS/A* routing")
        net_list_ids = self.sort_netlist_id_for_io(self.netlists)
        for net_id in net_list_ids:
            net = self.netlists[net_id]
            if len(net) == 1:
                continue    # no need to route
            bus = Router.get_bus_type(net)
            src_id, src_port = net[0]
            # avoid going back
            net = self.sort_net(net, self.placement)
            pin_port_set = determine_pin_ports(net, self.placement)

            dst_set_cpy = net[1:]
            route_path = {}
            # TODO: change how to present failure
            failed_route = [None] * 100
            chan_resources = {}
            for chan in range(self.channel_width):
                final_path = []
                # this is used for rough route (no port control)
                # usefully when we have a net connected to two pins in a same
                # tile
                dst_set = dst_set_cpy[:]
                src_pos = self.placement[src_id]
                # local routing resource
                routing_resource = self.copy_resource()
                pos_set = set()
                # used for bitstream
                is_src = True
                while len(dst_set) > 0:
                    dst_point = dst_set.pop(0)
                    dst_id, dst_port = dst_point
                    dst_pos = self.placement[dst_id]

                    # self loop prevention
                    # this will happen if two operands share the same input
                    # in a single block
                    if dst_pos == src_pos:
                        # FIXME use path instead
                        pre_pos = self.find_pre_pos(dst_pos, final_path)
                        available, pin_info = \
                            self.is_pin_available(routing_resource,
                                                  pre_pos, dst_pos, dst_port,
                                                  bus, chan,
                                                  is_self_connection=True)

                        if not available:
                            # failed to connect
                            final_path = failed_route
                            break
                        # just that it won't blow up the later logic
                        link = {(dst_pos, dst_port): pin_info}
                    else:
                        link = self.connect_two_points((src_pos, src_port),
                                                       (dst_id,
                                                        dst_pos, dst_port),
                                                       bus,
                                                       chan,
                                                       pin_port_set,
                                                       is_src,
                                                       final_path,
                                                       pos_set,
                                                       routing_resource)
                    if (dst_pos, dst_port) not in link:
                        # failed to route in this channel
                        final_path = failed_route
                        dst_set = []
                        # early termination
                        break
                    # merge the search path to channel path
                    pp = dst_pos
                    pos_set.add(pp)
                    path = []
                    while pp != src_pos:
                        path.append(link[pp])
                        pp = link[pp][0][0]
                        pos_set.add(pp)

                    path.reverse()

                    entry = (dst_pos, dst_port)
                    if entry not in link:
                        # routing failed
                        assert(final_path[0] is None)
                        break
                    path.append(link[entry])

                    # append this to the final path
                    if len(final_path) == 0:
                        final_path = path
                    else:
                        # skip the first one since src and dst overlap
                        final_path = final_path + path

                    # move along the hyper edge
                    src_pos = dst_pos
                    # disable the src since we're moving along the net
                    is_src = False

                route_path[chan] = final_path

                # update the routing info
                if len(final_path) > 1 and final_path[0] is not None:
                    # update routing resource
                    self.update_routing_resource(routing_resource,
                                                 final_path)
                    chan_resources[chan] = routing_resource
                elif len(final_path) == 0:
                    raise Exception("no path found. unexpected error")

            # find the minimum route path
            min_chan = 0
            for i in range(1, self.channel_width):
                if len(route_path[i]) < len(route_path[min_chan]):
                    min_chan = i
            if len(route_path[min_chan]) == len(failed_route):
                raise Exception("Failed to route for net " + net_id)
            # add the final path to the design
            self.route_result[net_id] = route_path[min_chan]

            # update the actual routing resource
            # self-loop is fixed up
            self.routing_resource = chan_resources[min_chan]

    @staticmethod
    def get_track_in_from_path(src_pos, path):
        for i in range(len(path) - 1, -1, -1):
            if isinstance(path[i][-1], str):
                continue
            if len(path[i]) == 1:
                pos, _, _, conn = path[i][0]
            elif len(path[i]) == 2:
                pos, conn = path[i][-1]
                src_pp, src_conn = path[i][0]
            else:
                raise Exception("Unknown path")
            if pos == src_pos:
                if src_conn[1] == 0:
                    return src_conn
            assert conn[1] == 0    # it's actually coming in
            return conn
        raise Exception("Unable to find track in")

    def connect_two_points(self, src, dst, bus, chan, pin_ports,
                           is_src, final_path,
                           pos_set, routing_resource):
        src_pos, src_port = src
        (dst_id, dst_pos, dst_port) = dst
        working_set = []
        finished_set = set()
        link = {}
        working_set.append(src_pos)
        terminate = False
        depth = {src_pos: 0}
        track_in = None
        while len(working_set) > 0 and not terminate:
            # using manhattan distance as heuristics
            working_set.sort(
                key=lambda pos: self.heuristic_dist(depth, pos,
                                                    dst_pos, bus))
            point = working_set.pop(0)
            if len(point) == 3:
                point, _, track_in = point
            finished_set.add(point)
            if is_src:
                points = self.get_port_neighbors(routing_resource, bus, chan,
                                                 point, src_port)
            else:
                if track_in is None:
                    assert len(final_path) > 0
                    track_in = self.get_track_in_from_path(src_pos, final_path)
                    # get previous track in
                points = self.get_neighbors(routing_resource,
                                            bus, chan, point, track_in,
                                            pin_ports)
            for entry in points:
                if is_src:
                    p, dir_out, dir_in = entry
                else:
                    p, dir_out, dir_in = entry
                if p in finished_set or entry in working_set or \
                        p in pos_set:
                    # we have already explored this position
                    continue
                # point backwards
                if is_src:
                    assert(point == src_pos)
                    link[p] = [(point, src_port, dir_out, dir_in)]
                else:
                    link[p] = ((point, dir_out), (p, dir_in))
                depth[p] = depth[point] + 1
                if p == dst_pos:
                    # we have found it!
                    # but hang on as we need to make sure the
                    # pin resource is available
                    if (dst_pos, dst_port) in pin_ports:
                        available, pin_info = \
                            self.is_pin_available(routing_resource,
                                                  point, p,
                                                  dst_port,
                                                  bus,
                                                  chan)
                        if not available:
                            # we're doomed for this chan
                            # consider to re-route?
                            link.pop(p, None)
                            depth.pop(p, None)
                        else:
                            link[(p, dst_port)] = pin_info
                    terminate = True
                    break
                else:
                    working_set.append(entry)

            # we're done with the src
            is_src = False
        return link

    def update_routing_resource(self, routing_resource, path):
        for pin_info in path:
            if len(pin_info) == 1:
                # this is src
                p, port, dir_out, dir_in = pin_info[0]
                ports = routing_resource[p]["port"][port]
                ports.remove(dir_out)
                # also remove the routing resource
                res = self.get_route_resource(self.board_meta,
                                              routing_resource,
                                              p)
                conn_remove = set()
                for conn1, conn2 in res:
                    if conn2 == dir_out:
                        conn_remove.add((conn1, conn2))
                for entry in conn_remove:
                    res.remove(entry)
            if len(pin_info) == 2:
                # passing through
                p1, dir_out = pin_info[0]
                p2, dir_in = pin_info[1]
                res1 = self.get_route_resource(self.board_meta,
                                               routing_resource,
                                               p1)
                res2 = self.get_route_resource(self.board_meta,
                                               routing_resource,
                                               p2)

                # out is the first one and in is the second one
                conn_remove = set()
                for conn1, conn2 in res1:
                    if conn2 == dir_out:
                        conn_remove.add((conn1, conn2))
                for entry in conn_remove:
                    res1.remove(entry)
                # also disable any in/out port that can connect to this tile
                port_resource = self.get_port_resource(self.board_meta,
                                                       routing_resource,
                                                       p1)
                for port in port_resource:
                    port_conn = port_resource[port]
                    if dir_out in port_conn:
                        port_conn.remove(dir_out)

                conn_remove = set()
                for conn1, conn2 in res2:
                    if conn1 == dir_in:
                        conn_remove.add((conn1, conn2))
                for entry in conn_remove:
                    res2.remove(entry)

                # also disable any in/out port that can connect to this tile
                port_resource = self.get_port_resource(self.board_meta,
                                                       routing_resource,
                                                       p2)
                for port in port_resource:
                    port_conn = port_resource[port]
                    if dir_in in port_conn:
                        port_conn.remove(dir_in)
            elif len(pin_info) == 3:
                if not(isinstance(pin_info[-1], str)) and \
                       not(isinstance(pin_info[-1], unicode)):
                    raise Exception("Unknown pin_info " + str(pin_info))
                # no turn sink
                # need to delete the port path
                # it might be redundant for PE tiles, but for IO ports
                # it's critical?
                conn, pos, port = pin_info
                ports = routing_resource[pos]["port"][port]
                if conn in ports:
                    ports.remove(conn)
                continue

            elif len(pin_info) == 4:
                # need to take care of the extra out
                # [dir_in, conn, current_point, port]
                conn = pin_info[1]  # conn is out
                pos = pin_info[2]
                res = routing_resource[pos]["route_resource"]
                conn_remove = set()
                for conn1, conn2 in res:
                    if conn2 == conn:
                        conn_remove.add((conn1, conn2))
                for entry in conn_remove:
                    res.remove(entry)
                #ports = routing_resource[pos]["port"][pin_info[-1]]
                #ports.remove(conn)

                # disable any port output to it
                for port in routing_resource[pos]["port"]:
                    ports = routing_resource[pos]["port"][port]
                    if conn in ports:
                        ports.remove(conn)

    def compute_stats(self):
        top_10 = []
        margin = self.board_meta[-1]["margin"]
        height = self.board_meta[-1]["height"]
        width = self.board_meta[-1]["width"]
        for i in range(self.board_size[0]):
            for j in range(self.board_size[1]):
                if \
                        (i in range(0, margin) or j in range(0, margin) or
                                i in range(height - margin, height) or
                                j in range(width - margin,
                                           width)):  # IO is special:
                    continue
                else:
                    route_r = self.get_route_resource(self.board_meta,
                                                      self.routing_resource,
                                                      (i, j))
                    un_used_16 = set()
                    for conn1, conn2 in route_r:
                        if conn1[0] == 16:
                            un_used_16.add(conn1)
                    res = np.sum(len(un_used_16))
                    top_10.append(((i, j), res))
                    if len(top_10) > 10:
                        top_10.sort(key=lambda x: x[1])
                        top_10.pop(len(top_10) - 1)
        print("Top 10 most used tiles:")
        for pos, res in top_10:
            print(pos, "\tchannels left:", res)

    def vis_routing_resource(self):
        scale = 30
        margin = self.board_meta[-1]["margin"]
        height = self.board_meta[-1]["height"]
        width = self.board_meta[-1]["width"]
        im, draw = draw_board(self.board_size[0], self.board_size[1], scale)
        for i in range(self.board_size[0]):
            for j in range(self.board_size[1]):
                if  \
                        (i in range(0, margin) or j in range(0, margin) or
                         i in range(height - margin, height) or
                         j in range(width - margin, width)):    # IO is special:
                    color = 255
                else:
                    route_r = self.get_route_resource(self.board_meta,
                                                      self.routing_resource,
                                                      (i, j))
                    un_used_16 = set()
                    for conn1, conn2 in route_r:
                        if conn1[0] == 16:
                            un_used_16.add(conn1)
                    res = np.sum(len(un_used_16))
                    # mem tiles strike again!
                    if self.layout_board[j][i] == "m" or \
                            self.layout_board[j - 1][i] == "m":
                        res /= 2
                    color = int(255 * res / 4 / self.channel_width)
                draw_cell(draw, (i, j), color=(255 - color, 0, color),
                          scale=scale)
        plt.axis('off')
        plt.imshow(im)
        plt.show()
        file_dir = os.path.dirname(os.path.realpath(__file__))
        output_png = self.design_name + "_route.png"
        output_path = os.path.join(file_dir, "figures", output_png)
        im.save(output_path)
        print("Image saved to", output_path)


if __name__ == "__main__":
    options, argv = parse_args(sys.argv)
    if len(argv) != 4:
        print("Usage:", sys.argv[0], "[options] <arch_file> <netlist.packed>",
              "<netlist.place>", file=sys.stderr)
        print("[options]: -no-vis", file=sys.stderr)
        exit(1)
    vis_opt = "no-vis" not in options
    arch_file = argv[1]
    meta = parse_cgra(arch_file)["CGRA"]
    r = Router(arch_file, meta, argv[2], argv[3])
    r.route()
    if vis_opt:
        r.vis_routing_resource()
    r.compute_stats()

    route_file = sys.argv[3].replace(".place", ".route")

    save_routing_result(r.route_result, route_file)

