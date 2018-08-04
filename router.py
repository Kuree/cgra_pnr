from __future__ import print_function, division
from arch.cgra import parse_placement, save_routing_result
from arch.cgra_packer import load_packed_file
from arch.cgra import compute_direction, determine_pin_direction
from arch.cgra import get_opposite_direction
from arch import parse_cgra
import sys
import numpy as np
from visualize import draw_board, draw_cell
import matplotlib.pyplot as plt
from util import parse_args


class Router:
    def __init__(self, board_meta, packed_filename, placement_filename,
                 avoid_congestion=True):
        self.board_meta = board_meta
        netlists, _, id_to_name, = load_packed_file(packed_filename)
        self.id_to_name = id_to_name
        self.netlists = netlists

        placement, _ = parse_placement(placement_filename)
        self.placement = placement

        board_info = board_meta[-1]
        width = board_info["width"]
        height = board_info["height"]

        # NOTE: it's width x height
        self.board_size = (width, height)
        # TODO: fix this after parsing routing info from the arch
        self.channel_width = 5

        # result
        self.route_result = {}
        self.route_ports = {}

        margin = board_info["margin"]
        # 4 directions
        self.routing_resource = np.zeros((height,               # height
                                          width,                # width
                                          4,                    # four sides
                                          self.channel_width,   # channel width
                                          2),                   # in/out
                                         dtype=np.bool)
        for i in range(margin, self.board_size[0] - margin):
            for j in range(margin, self.board_size[1] - margin):
                for k in range(4):
                    for l in range(self.channel_width):
                        self.routing_resource[i][j][k][l][0] = True
                        self.routing_resource[i][j][k][l][1] = True

        # only allow certain IO tiles to have routing resources
        self.routing_resource[2][1][0][:, :] = True
        self.routing_resource[1][2][1][:, :] = True
        self.routing_resource[18][2][3][:, :] = True
        self.routing_resource[2][18][2][:, :] = True

        self.avoid_congestion = avoid_congestion

    @staticmethod
    def manhattan_dist(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

    def heuristic_dist(self, depth, pos, dst):
        x, y = pos
        dist = abs(x - dst[0]) + abs(y - dst[1]) + depth[(x, y)]
        if self.avoid_congestion:
            route_resource = np.sum(self.routing_resource[y, x])
            if route_resource == 0:
                extra = 100 # a large number
            else:
                extra = 40 / route_resource
            extra = 0
            dist += extra
        return dist

    def get_neighbors(self, routing_resource, chan, pos):
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
        for new_pos in working_set:
            direction = compute_direction(pos, new_pos)
            # check if out is okay
            if not routing_resource[y][x][direction][chan][1]:
                continue
            direction = compute_direction(new_pos, pos)
            new_x, new_y = new_pos
            if not routing_resource[new_y][new_x][direction][chan][0]:
                continue
            results.append(new_pos)
        return results

    def is_pin_available(self, routing_resource,
                         pre_point, current_point, fixed_direction, chan):
        direction = compute_direction(current_point, pre_point)
        x, y = current_point
        # if direction is the fixed direction, we are good
        if direction == fixed_direction:
            return True, None
        else:
            # we need to determine if either dir-in or dir-out is available
            # current direction_in -> fixed_direction_out
            # for now it's fixed order, that is
            # direction_in -> fixed_direction_out
            # fixed_direction_out -> op <- this is done by bitstream builder
            # NOTE: we still need to mark that channel as unavailable
            if fixed_direction == 1:
                r1 = routing_resource[y][x][fixed_direction][chan][1]
                r2 = routing_resource[y][x][fixed_direction][chan][0]
                return r1 and r2, (current_point, fixed_direction, fixed_direction)
            elif fixed_direction == 2:
                r1 = routing_resource[y][x][fixed_direction][chan][1]
                r2 = routing_resource[y][x][fixed_direction][chan][0]
                return r1 and r2, (current_point, fixed_direction, fixed_direction)
            else:
                raise Exception("unknown fixed direction " +
                                str(fixed_direction))

    def update_pin_resource(self, routing_resource, pin_info, chan):
        if pin_info is None:
            # easy job
            return
        (x, y), direction, fixed_direction = pin_info
        routing_resource[y][x][direction][chan][1] = False
        routing_resource[y][x][fixed_direction][chan][0] = False


    def handle_self_loop(self, routing_resource, point, pre_direction,
                         fixed_direction_dst, chan):
        (x, y) = point
        # in and out should be open
        # we go out from that direction and come in
        r1 = routing_resource[y][x][fixed_direction_dst][chan][0]
        r2 = routing_resource[y][x][fixed_direction_dst][chan][1]
        if not r1 or not r2:
            return False
        # because we fixed the channel in the pin set up already
        # no need to do it again
        if pre_direction != fixed_direction_dst:
            routing_resource[y][x][fixed_direction_dst][chan][0] = False
            routing_resource[y][x][fixed_direction_dst][chan][1] = False
        return True

    def route(self):
        print("INFO: Performing greedy BFS/A* routing")
        for net_id in self.netlists:
            net = self.netlists[net_id]
            if len(net) == 1:
                continue    # no need to route
            src_id, src_port = net[0]
            # avoid going back
            net.sort(key=lambda pos:
                     self.manhattan_dist(self.placement[src_id],
                     self.placement[pos[0]]))
            pin_directions = determine_pin_direction(net, self.placement)

            dst_set_cpy = net[1:]
            route_path = {}
            # TODO: change how to present failure
            failed_route = [None] * 100
            chan_resources = {}
            chan_pin_ports = {}
            for chan in range(self.channel_width):
                final_path = []
                dst_set = dst_set_cpy[:]
                src_pos = self.placement[src_id]
                # local routing resource
                routing_resource = np.copy(self.routing_resource)
                # used for bitstream
                pin_ports = [(src_pos, src_id, src_port)]
                while len(dst_set) > 0:
                    dst_point = dst_set.pop(0)
                    dst_id, dst_port = dst_point
                    dst_pos = self.placement[dst_id]

                    # self loop prevention
                    # this will happen if two operands share the same input
                    # in a single block
                    if dst_pos == src_pos:
                        # skip over the loop
                        #src_pos = dst_pos
                        # we have two options here
                        # either to reroute the pre->new one
                        # or do tricks on the same tile

                        # go for doing tricks on the same tile
                        # to avoid using routing resource too much
                        # also notice that if the previous route is coming
                        # to the "other" operand, we only need to update
                        # one side of the channel

                        if len(net) == 2 and "reg" in src_port:
                            # we already absorbed them
                            pin_ports.append((dst_pos, dst_id, dst_port))
                            break

                        pre_pos = final_path[-2]
                        pre_port = pin_ports[-1][-1]
                        pre_direction = compute_direction(dst_pos, pre_pos)
                        fixed_direction_dst = \
                            pin_directions[(dst_pos, dst_port)]
                        #fixed_direction_dst()
                        result = self.handle_self_loop(routing_resource,
                                                       src_pos,
                                                       pre_direction,
                                                       fixed_direction_dst,
                                                       chan)

                        if not result:
                            # failed to connect
                            final_path = failed_route
                            break
                        # just that it won't blow up the later logic
                        final_path.append(dst_pos)
                        pin_ports.append((dst_pos, dst_id, dst_port))
                        continue
                    else:
                        link = self.connect_two_points(src_pos,
                                                       (dst_id,
                                                        dst_pos, dst_port),
                                                       chan,
                                                       pin_directions,
                                                       final_path,
                                                       pin_ports,
                                                       routing_resource)
                    if dst_pos not in link:
                        # failed to route in this channel
                        final_path = failed_route
                        dst_set = []
                        # early termination
                        break
                    # merge the search path to channel path
                    pp = dst_pos
                    path = []
                    while pp != src_pos:
                        path.append(pp)
                        pp = link[pp]
                    path.append(pp)
                    path.reverse()
                    # append this to the final path
                    if len(final_path) == 0:
                        final_path = path
                    else:
                        # skip the first one since src and dst overlap
                        final_path = final_path + path[1:]

                    # move along the hyper edge
                    src_pos = dst_pos

                route_path[chan] = final_path

                # update the routing info
                if len(final_path) > 1 and final_path[0] is not None:
                    # I'm a little scared
                    self.update_routing_resource(routing_resource, chan,
                                                 final_path)
                    chan_resources[chan] = routing_resource
                    assert(len(net) == len(pin_ports))
                    chan_pin_ports[chan] = pin_ports
                elif len(final_path) == 1:
                    # self connection
                    # happens when you have a source drives to the same
                    # sinks
                    # already been take care off
                    chan_resources[chan] = routing_resource
                    assert (len(net) == len(pin_ports))
                    chan_pin_ports[chan] = pin_ports
                elif len(final_path) == 0:
                    # only okay if it's a absorbed register
                    if pin_ports[0][-1][0] != "r":
                        raise Exception("no path found. unexpected error")
                    chan_resources[chan] = routing_resource
                    chan_pin_ports[chan] = pin_ports

            # find the minimum route path
            min_chan = 0
            for i in range(1, self.channel_width):
                if len(route_path[i]) < len(route_path[min_chan]):
                    min_chan = i
            if len(route_path[min_chan]) == len(failed_route):
                raise Exception("Failed to route for net " + net_id)
            # add the final path to the design
            self.route_result[net_id] = (min_chan, route_path[min_chan])
            self.route_ports[net_id] = chan_pin_ports[min_chan]

            # update the actual routing resource
            # self-loop is fixed up
            self.routing_resource = chan_resources[min_chan]

    def connect_two_points(self, src_pos, dst, chan, pin_directions,
                           final_path, pin_ports, routing_resource):
        (dst_id, dst_pos, dst_port) = dst
        working_set = []
        finished_set = set()
        link = {}
        working_set.append(src_pos)
        terminate = False
        depth = {src_pos: 0}
        while len(working_set) > 0 and not terminate:
            # using manhattan distance as heuristics
            working_set.sort(
                key=lambda pos: self.heuristic_dist(depth, pos,
                                                    dst_pos))
            point = working_set.pop(0)
            finished_set.add(point)
            points = self.get_neighbors(routing_resource,
                                        chan, point)
            for p in points:
                if p in finished_set or p in working_set or \
                        p in final_path:
                    # we have already explored this position
                    continue
                link[p] = point  # point backwards
                depth[p] = depth[point] + 1
                if p == dst_pos:
                    # we have found it!
                    # but hang on as we need to make sure the
                    # pin resource is available
                    if (dst_pos, dst_port) in pin_directions:
                        fixed_direction = pin_directions[(dst_pos, dst_port)]
                        available, pin_info = \
                            self.is_pin_available(routing_resource,
                                                  point, p,
                                                  fixed_direction,
                                                  chan)
                        if not available:
                            # we're doomed for this chan
                            # consider to re-route?
                            link.pop(p, None)
                            depth.pop(p, None)
                        else:
                            self.update_pin_resource(
                                routing_resource, pin_info, chan)
                            # put it to the pin_ports so that we know
                            # what's going on in the bitstream stage
                    terminate = True
                    pin_ports.append((p, dst_id, dst_port))
                    break
                else:
                    working_set.append(p)
        return link

    def update_routing_resource(self, routing_resource,
                                chan, path):
        for index in range(0, len(path) - 1):
            path_src = path[index]
            path_dst = path[index + 1]
            if path_src == path_dst:
                continue    # self loop
            direction = compute_direction(path_src, path_dst)
            path_src_x, path_src_y = path_src
            path_dst_x, path_dst_y = path_dst
            # out
            assert(routing_resource[path_src_y][path_src_x][direction][chan][1])
            routing_resource[path_src_y][path_src_x][direction][chan][1] = False
            # in
            direction = compute_direction(path_dst, path_src)
            assert(routing_resource[path_dst_y][path_dst_x][direction][chan][0])
            routing_resource[path_dst_y][path_dst_x][direction][chan][0] = False

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
                    route_r = self.routing_resource[i][j]
                    r = np.sum(route_r)
                    color = int(255 * r / 4 / self.channel_width / 2)
                draw_cell(draw, (j, i), color=(255 - color, 0, color),
                          scale=scale)
        plt.imshow(im)
        plt.show()


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
    r = Router(meta, argv[2], argv[3])
    r.route()
    if vis_opt:
        r.vis_routing_resource()

    route_file = sys.argv[3].replace(".place", ".route")

    save_routing_result(r.route_result, r.route_ports, route_file)

