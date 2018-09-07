from __future__ import print_function, division
from arch.cgra import parse_placement, save_routing_result
from arch.netlist import group_reg_nets
from arch.cgra_packer import load_packed_file
from arch.cgra import determine_pin_ports
from arch.cgra_route import parse_routing_resource, build_routing_resource
from arch import parse_cgra
import os
import numpy as np
from visualize import draw_board, draw_cell
import matplotlib.pyplot as plt
from util import deepcopy
from tqdm import tqdm
from argparse import ArgumentParser


class Router:
    MAX_PATH_LENGTH = 10000

    def __init__(self, cgra_filename,
                 board_meta, packed_filename, placement_filename,
                 use_tie_breaker=False, fold_reg=True, channel_width=None):
        self.board_meta = board_meta
        self.layout_board = board_meta[0]
        netlists, _, id_to_name, _, track_mode = load_packed_file(
            packed_filename, load_track_mode=True)
        self.id_to_name = id_to_name
        self.netlists = netlists
        self.track_mode = track_mode

        placement, _ = parse_placement(placement_filename)
        self.placement = placement

        board_info = board_meta[-1]
        width = board_info["width"]
        height = board_info["height"]
        self.margin = board_info["margin"]

        # NOTE: it's width x height
        self.board_size = (width, height)

        # whether to fold registers when do routing
        self.fold_reg = fold_reg

        # result
        self.route_result = {}

        print("Building routing resource")
        r = parse_routing_resource(cgra_filename)
        self.routing_resource = build_routing_resource(r)

        self.use_tie_breaker = use_tie_breaker

        base_filename = os.path.basename(packed_filename)
        design_name, _ = os.path.splitext(base_filename)
        self.design_name = design_name

        if channel_width is not None:
            self.channel_width = channel_width
        else:
            # loop through the routing resource to figure out the channel width
            # automatically
            channel_set = set()
            for pos in self.routing_resource:
                chans = self.routing_resource[pos]["route_resource"]
                for entry in chans:
                    channel_set.add(entry[0][-1])
            self.channel_width = len(channel_set)
        print("Using", self.channel_width, "channels to route")

    @staticmethod
    def manhattan_dist(p1, p2):
        return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])

    @staticmethod
    def compute_direction(src, dst):
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
        # # FIXME: use the height to compute
        # if self.layout_board[y1][x1] is None and y1 > self.margin and \
        #         self.layout_board[y1 - 1][x1] == "m":
        #     direction += 4

        return direction

    def heuristic_dist(self, depth, pos, dst, src=None):
        if len(pos) == 3:
            pos, _, _ = pos
        x, y = pos
        dst_x, dst_y = dst
        dist = abs(x - dst_x) + abs(y - dst_y) + depth[(x, y)]
        if self.use_tie_breaker:
            # http://theory.stanford.edu/~amitp/GameProgramming/Heuristics.html#breaking-ties
            assert (src is not None) and (len(src) == 2)
            src_x, src_y = src
            dx1 = x - dst_x
            dy1 = y - dst_y
            dx2 = x - src_x
            dy2 = y - src_y
            cross = abs(dx1 * dy2 + dx2 * dy1)
            dist += cross * 0.001
        return dist

    def get_port_neighbors(self, routing_resource, bus, chan, pos, port):
        route_resource_current_pos = self.get_route_resource(self.board_meta,
                                                             routing_resource,
                                                             pos)
        if port not in routing_resource[pos]["port"]:
            if not self.fold_reg or port != "reg":
                raise Exception("Unexpected port " + port +
                                " in reg folding mode at pos " + str(pos))
            port_chan = set()
            for _, conn_out in route_resource_current_pos:
                if conn_out[-1] == chan and conn_out[0] == bus:
                    # as long as there is an out, we are good
                    port_chan.add(conn_out)
        else:
            # normal ports
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
                    for conn_in, _ in route_resource_current_pos2:
                        if conn_in == dir_in:
                            can_turn = True
                            break
                    if can_turn:
                        results.append((new_pos, dir_out, dir_in))
        return results

    @staticmethod
    def get_route_resource(_, routing_resource, pos):
        # FIXME: use height for searching
        if pos not in routing_resource:
            # # FIXME: use height for searching
            # pos_fixed = (pos[0], pos[1] - 1)
            # assert(board_meta[0][pos_fixed[1]][pos_fixed[0]] == "m")
            # return routing_resource[pos_fixed]["route_resource"]
            raise Exception("Illegal position")
        else:
            return routing_resource[pos]["route_resource"]

    @staticmethod
    def get_port_resource(_, routing_resource, pos):
        # FIXME: use height for searching
        if pos not in routing_resource:
            # # FIXME: use height for searching
            # pos_fixed = (pos[0], pos[1] - 1)
            # assert (board_meta[0][pos_fixed[1]][pos_fixed[0]] == "m")
            # return routing_resource[pos_fixed]["port"]
            raise Exception("Illegal position")
        else:
            return routing_resource[pos]["port"]

    def get_neighbors(self, routing_resource, bus, chan, pos, track_in,
                      pin_ports, force_connect=False):
        # Keyi:
        # force connect is used when track_in has been updated but you still
        # want to connect to the next tile
        # ONLY useful in reg src connection
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

        # # another override for mem tile jumping
        # # FIXME
        # if self.layout_board[pos[1]][pos[0]] == "m" and \
        #         track_in[2] == 1:
        #    track_in = (track_in[0], 1, 7, track_in[-1])

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

            # if self.layout_board[pos[1]][pos[0]] == "m" and \
            #         dir_out[2] == 1:
            #    dir_out = (dir_out[0], dir_out[1], 7, dir_out[-1])
            if not force_connect:
                if (track_in, dir_out) not in route_resource_current_pos:
                    # can't make the turn
                    continue
            else:
                dir_out_set = set()
                for _, conn_out in route_resource_current_pos:
                    if conn_out[-2] != track_in[-2] and \
                            conn_out[0] == track_in[0] and \
                            conn_out[-1] == track_in[-1]:
                        dir_out_set.add(conn_out)
                if dir_out not in dir_out_set:
                    continue
            can_turn = False
            if new_pos not in pin_pos:
                for conn_in, _ in route_resource_current_pos2:
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
        if len(pre_point) == 2:
            direction = self.compute_direction(current_point, pre_point)
            # test if we have direct connection to the operand
            # that is, in -> op
            dir_in = (bus, 0, direction, chan)
        else:
            assert len(pre_point) == 4
            dir_in = pre_point
        route_resource = routing_resource[current_point]["route_resource"]
        sink_resource = routing_resource[current_point]["port"]
        if port not in sink_resource:
            assert(self.fold_reg and port == "reg")
            for i in range(4):
                dir_out = (bus, 1, i, chan)
                if (dir_in, dir_out) in route_resource:
                    return True, [dir_in, current_point, port]
            return False, None
        else:
            operand_channels = sink_resource[port]

            operand_channels = [entry for entry in operand_channels
                                if entry[-1] == chan]

            route_resource = [entry for entry in route_resource
                              if entry[-1][-1] == chan and
                              entry[-1][0] == bus]

            # if self.layout_board[current_point[1]][current_point[0]]
            #  == "m" and \
            #         dir_in[2] == 1:
            #     # make the dir in as dir_out from the bottom tile
            #    dir_in = (bus, 1, 7, chan)
            if dir_in in operand_channels:
                return True, [dir_in, current_point, port]

            # need to determine if we can connect to a out bus
            # that is, in_sxtx -> out_sxtx
            #          out_sxtx -> op
            for conn in operand_channels:
                # the format in operand_channels is out -> in
                conn_chan = (dir_in, conn)
                if conn_chan in route_resource:
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
    def copy_resource(routing_resource):
        res = deepcopy(routing_resource)
        return res

    @staticmethod
    def sort_netlist_id_for_io(netlist, reg_nets):
        netlist_ids = list(netlist.keys())

        def sort(net_id):
            net = netlist[net_id]
            if net_id in reg_nets:
                return 1
            for blk_id, _ in net:
                if blk_id[0] == "i":
                    return 0
            return 2
        netlist_ids.sort(key=lambda net_id: int(net_id[1:]))
        # in-place sort
        netlist_ids.sort(key=lambda net_id: sort(net_id))
        return netlist_ids

    @staticmethod
    def find_pre_track_in(pos, path):
        for i in range(len(path) - 1, 0, -1):
            path_entry = path[i]
            if len(path_entry) == 2:
                if path_entry[1][0] == pos:
                    assert path_entry[1][1][1] == 0
                    return path_entry[1][1]
            elif len(path_entry) == 3:
                if path_entry[1] == pos:
                    assert path_entry[0][1] == 0
                    return path_entry[0]
            elif len(path_entry) == 4:
                if path_entry[2] == pos:
                    assert path_entry[0][1] == 0
                    return path_entry[0]
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

    @staticmethod
    def dis_allow_chan(pos, port, bus, chan, route_resource, pos_set):
        if port == "reg":
            pos_set.add(pos)
        else:
            port_operands = route_resource[pos]["port"][port]
            port_operands = [x for x in port_operands if x[0] == bus
                             and x[-1] == chan]
            for conn in port_operands:
                pos_set.add((pos, conn))

    @staticmethod
    def allow_chan(pos, pos_set):
        if pos in pos_set:
            pos_set.remove(pos)
        entry_to_remove = set()
        for entry in pos_set:
            if len(entry) == 2 and not isinstance(entry[-1], int):
                assert (isinstance(entry[1], tuple))
                entry_pos = entry[0]
                if pos == entry_pos:
                    entry_to_remove.add(entry)
        for entry in entry_to_remove:
            pos_set.remove(entry)

    def route(self):
        print("INFO: Performing MST/A* routing")
        if self.fold_reg:
            linked_nets, reg_nets, reg_net_order = group_reg_nets(self.netlists)
        else:
            linked_nets = {}
            reg_nets = set()
            reg_net_order = {}
        net_list_ids = self.sort_netlist_id_for_io(self.netlists, reg_nets)
        for net_id in tqdm(net_list_ids):
            if net_id in reg_nets:
                continue
            net = self.netlists[net_id]
            assert (len(net) > 1)
            bus = self.track_mode[net_id]
            # avoid going back
            net = self.sort_net(net, self.placement)

            route_path = {}
            route_length = {}
            chan_resources = {}
            reg_route_path = {}
            for chan in range(self.channel_width):
                # FIXME: force to use channel one
                # need to fix it after IO is re-worked
                if net[0][0][0] == "i":
                    if chan != 0:
                        route_length[chan] = self.MAX_PATH_LENGTH
                        continue
                # make sure that it won't route on top of reg net
                if net_id in linked_nets:
                    pos_set = set()
                    for reg_net_id in linked_nets[net_id]:
                        reg_net = self.netlists[reg_net_id]
                        for blk_id, port in reg_net:
                            pos = self.placement[blk_id]
                            self.dis_allow_chan(pos, port, bus, chan,
                                                self.routing_resource,
                                                pos_set)
                else:
                    pos_set = None

                path_len, final_path, routing_resource = \
                    self.route_net(bus, chan, net,
                                   self.routing_resource,
                                   pos_set=pos_set)
                chan_resources[chan] = routing_resource
                route_path[chan] = final_path
                route_length[chan] = path_len
                if path_len >= self.MAX_PATH_LENGTH:
                    continue    # don't even bother
                if net_id in linked_nets:
                    if chan not in reg_route_path:
                        reg_route_path[chan] = {}
                    reg_route_path[chan][net_id] = final_path
                    for reg_net_id in linked_nets[net_id]:
                        parent_net_id = reg_net_order[reg_net_id]
                        reg_path = reg_route_path[chan][parent_net_id]
                        reg_net = self.netlists[reg_net_id]
                        # because routing resource has been updated, we don't
                        # need to keep track of old ones
                        # pos_set = set()
                        reg_length, reg_path, routing_resource = \
                            self.route_reg_net(reg_net, bus, chan,
                                               routing_resource,
                                               reg_path,
                                               pos_set)
                        route_length[chan] += reg_length
                        if route_length[chan] >= self.MAX_PATH_LENGTH:
                            break   # just terminate without proceeding next
                        reg_route_path[chan][reg_net_id] = reg_path
                        chan_resources[chan] = routing_resource

            # find the minimum route path
            min_chan = 0
            for i in range(1, self.channel_width):
                if route_length[i] < route_length[min_chan]:
                    min_chan = i
            if route_length[min_chan] >= self.MAX_PATH_LENGTH:
                raise Exception("Failed to route for net " + net_id)
            # add the final path to the design
            self.route_result[net_id] = route_path[min_chan]
            if net_id in linked_nets:
                reg_path = reg_route_path[min_chan]
                for reg_net_id in reg_path:
                    self.route_result[reg_net_id] = reg_path[reg_net_id]

            # update the actual routing resource
            # self-loop is fixed up
            self.routing_resource = chan_resources[min_chan]

    @staticmethod
    def find_closet_src(pos, final_path, is_reg_net=False):
        # Keyi:
        # reg_net introduces some complications on where to find the closest
        # src points
        reg_pos = None
        distance = {}

        for index, conn in enumerate(final_path):
            if is_reg_net and index == 0:
                if len(final_path[index]) != 2:
                    assert (len(final_path[index + 1]) == 2)
                    reg_pos = final_path[index + 1][0][0]
                else:
                    reg_pos = final_path[index][-1][0]
                continue
            p = None
            if len(conn) == 1:
                # src
                p, _, _, _ = conn[0]

            elif len(conn) == 2:
                # passing through
                p, _ = conn[0]
            elif len(conn) == 3:
                # direct sink
                _, p, _ = conn
            elif len(conn) == 4:
                # self-connection sink
                _, _, p, _ = conn
            assert (p is not None)
            if p not in distance:
                distance[p] = Router.manhattan_dist(pos, p)
        keys = list(distance.keys())
        # we have to find reg_src if it's a reg net
        if is_reg_net:
            assert reg_pos is not None
            assert (reg_pos in keys)
            keys.remove(reg_pos)
            # also disable the coming in path which is used to direct reg net
            # just in case
            conn = final_path[0]
            assert len(conn) == 1 or len(conn) == 2
            src_pos = conn[0][0]
            if src_pos in keys:
                keys.remove(src_pos)
        keys.sort(key=lambda x: distance[x])

        return keys[0]

    def route_net(self, bus, chan, net, routing_resource, final_path=None,
                  is_src=True, pos_set=None, reg_pos=None):
        src_id, src_port = net[0]
        pin_port_set = determine_pin_ports(net,
                                           self.placement,
                                           fold_reg=self.fold_reg)

        path_length = 0
        if final_path is None:
            final_path = []
            force_connect = False
            final_path_index = 0
        else:
            force_connect = True
            assert (len(final_path) == 1)
            final_path_index = 1
        # this is used for rough route (no port control)
        # usefully when we have a net connected to two pins in a same
        # tile
        dst_set = net[1:]
        src_pos = self.placement[src_id]
        # local routing resource
        routing_resource = self.copy_resource(routing_resource)
        # Keyi:
        # because of the way it updates routing resource, the router is not
        # allowed to re-visit a pos it's been used for routing. It's fine until
        # we have a very complex net where there are lots of "semi-circles".
        # *Solution*
        # we can use pos_set to enforce the router won't go through it
        # Update:
        # need to relax so that we can still route though it, but not using
        # the wires required to connected to operands.
        if pos_set is None:
            pos_set = set()
        # reg_net's logic is different
        if reg_pos is None:
            is_reg_net = False
        else:
            is_reg_net = True
            pos_set.add(reg_pos)

        for (p_id, p_port) in dst_set:
            p_pos = self.placement[p_id]
            self.dis_allow_chan(p_pos, p_port, bus, chan, routing_resource,
                                pos_set)

        while len(dst_set) > 0:
            dst_point = dst_set.pop(0)
            dst_id, dst_port = dst_point
            dst_pos = self.placement[dst_id]
            self.allow_chan(dst_pos, pos_set)

            # get the new src position from the path we've already routed
            # > 1 because we don't want to interfere with reg net routing
            if len(final_path) > 1:
                src_pos = self.find_closet_src(dst_pos, final_path, is_reg_net)
                if src_pos == self.placement[src_id]:
                    is_src = True

            # self loop prevention
            # this will happen if two operands share the same input
            # in a single block
            if dst_pos == src_pos:
                pre_pos = self.find_pre_track_in(dst_pos, final_path)
                available, pin_info = \
                    self.is_pin_available(routing_resource,
                                          pre_pos, dst_pos, dst_port,
                                          bus, chan,
                                          is_self_connection=True)

                if not available:
                    # failed to connect
                    path_length = self.MAX_PATH_LENGTH
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
                                               routing_resource,
                                               force_connect=force_connect)
                force_connect = False
            if (dst_pos, dst_port) not in link:
                # failed to route in this channel
                path_length = self.MAX_PATH_LENGTH
                # early termination
                break
            # merge the search path to channel path
            pp = dst_pos
            # pos_set.add(pp)
            path = []
            while pp != src_pos:
                path.append(link[pp])

                pos_set.add(link[pp][0])
                if len(link[pp]) == 2:
                    pos_set.add(link[pp][1])
                else:
                    assert len(link[pp]) == 1

                pp = link[pp][0][0]

            path.reverse()

            entry = (dst_pos, dst_port)
            if entry not in link:
                # routing failed
                assert (final_path[0] is None)
                break
            path.append(link[entry])

            # append this to the final path
            if len(final_path) == 0:
                final_path = path
            else:
                # skip the first one since src and dst overlap
                final_path = final_path + path

            # disable the src since we're moving along the net
            is_src = False
        # update the routing info
        if len(final_path) > 1 and path_length != self.MAX_PATH_LENGTH:
            # update routing resource
            self.update_routing_resource(routing_resource,
                                         final_path[final_path_index:])
            path_length = len(final_path)
        elif len(final_path) == 0 and path_length != self.MAX_PATH_LENGTH:
            raise Exception("no path found. unexpected error")

        assert (path_length != 0)
        return path_length, final_path, routing_resource

    @staticmethod
    def get_track_in_from_path(src_pos, src_port, path):
        for i in range(len(path)):
            if len(path[i]) == 1:
                continue
            elif len(path[i]) == 2:
                pos, src_conn = path[i][-1]
                # src_pp, src_conn = path[i][0]
            elif len(path[i]) == 3:
                src_conn, pos, _ = path[i]
            elif len(path[i]) == 4:
                src_conn, _, pos, _ = path[i]
            else:
                raise Exception("Unknown path")
            if pos == src_pos:
                assert (src_conn[1] == 0)
                return True, src_conn
        # couldn't find it
        # going forwards to see if it comes directly from a src
        for i in range(len(path) - 1):
            if len(path[i]) == 1:
                pos = path[i][0][0]
                if pos == src_pos:
                    return False, None
                if len(path[i + 1]) == 2:
                    pos, _ = path[i + 1][0]
                    if pos == src_pos:
                        _, _, _, src_conn = path[i][0]
                        assert (src_conn[1] == 0)
                        return True, src_conn
        # last resort:
        # if it's a reg net and coming directly from a port
        if src_port == "reg":
            assert len(path) == 1
            pos, _, _, src_conn = path[0][0]
            assert Router.manhattan_dist(pos, src_pos) == 1
            assert (src_conn[1] == 0)
            return True, src_conn
        raise Exception("Unable to find track in")

    @staticmethod
    def is_sink(path_entry):
        return isinstance(path_entry[-1], str)

    def route_reg_net(self, net, bus, chan, routing_resource,
                      main_path, pos_set):
        # obtain the out direction of the reg from main path
        # notice that is is possible the reg is the last sink. If so,
        # pick up any
        src_id, src_port = net[0]
        src_pos = self.placement[src_id]
        assert (src_port == "reg")
        # traverse the main path to make sure that the main reg sink has an
        # out direction. If not, create one accordingly
        reg_index = -1
        for i in range(len(main_path) - 1, -1, -1):
            entry = main_path[i]
            # it can't be the src
            # if len(entry) == 1:
            #    raise Exception("reg cannot be src twice")
            # it has to be a direct sink
            if len(entry) == 3:
                conn, pos, port = entry
                if pos == src_pos and port == src_port:
                    # we have found it
                    reg_index = i
                    break
        assert (reg_index != 0 and reg_index != -1)

        # Keyi:
        # because of the way `route_net` works, if the entry is a src, it will
        # ignore any previous track and try to use port channels to figure the
        # shortest path. since we disabled the port channel searching for "reg",
        # it will try to route any direction possible. Hence we will arrive at
        # this illegal situation:
        # (x, y) -> (x, y + 1) : (16, 1, 1, 0) -> (16, 0, 3, 0)
        # where (x, y + 1) is a reg
        # then it will try to route back as the next destination is (x, y - 1)
        # (x, y + 1) -> (x, y) : (16, 1, 3, 0) -> (16, 0, 1, 0)
        # if we simply pick up the out as reg, we will end up as
        # (x, y + 1)::reg  (16, 0, 3, 0) -> (16, 1, 3, 0) (r)
        # *Solution:*
        # pass in the tail of `main_path` and disable `is_src` so that
        # `route_net` will handle the connection properly.
        # However, we need to be careful about cross over the old tiles
        tail_main_path = [main_path[reg_index - 1]]

        # sort the net first
        net = self.sort_net(net, self.placement)
        # route the wire
        path_length, final_path, routing_resource = \
            self.route_net(bus, chan, net, routing_resource, is_src=False,
                           final_path=tail_main_path,
                           pos_set=pos_set,
                           reg_pos=src_pos)
        if path_length == self.MAX_PATH_LENGTH:
            # not routable
            # just return that and the rest of the logic is going to handle
            # this failure
            return path_length, final_path, routing_resource
        # fill in the gap
        # reconnect to in -> out (reg)
        dir_in, pos, port = main_path[reg_index]
        final_path.pop(0)

        # Keyi:
        # More complications here
        # if the reg is the same position as the connected blocks
        # things will get very very tricky.
        assert (not self.is_sink(final_path[0]))
        (p, dir_out), (next_pos, conn_in) = final_path[0]
        # rewrite the first entry as the src format
        reg_src_entry = [(pos, port, dir_out, conn_in)]
        final_path[0] = reg_src_entry
        assert(p == pos)
        # Keyi:
        # More complications here
        # insert src entry if any of the reg net reuse the reg src
        # also we may keep inserting things, so a conventional loop
        # doesn't work here
        terminated = False
        start_index = 2
        while not terminated:
            index = len(final_path)
            for index in range(start_index, len(final_path)):
                entry = final_path[index]
                if len(entry) == 2:
                    # it's a link
                    if entry[0][0] == next_pos:
                        # we need to insert
                        break
            if index == len(final_path) - 1:
                terminated = True
            else:
                final_path.insert(index, reg_src_entry)
                start_index = index + 2

        main_path[reg_index] = (dir_in, pos, dir_out)

        return path_length, final_path, routing_resource

    def connect_two_points(self, src, dst, bus, chan, pin_ports,
                           is_src, final_path,
                           pos_set, routing_resource, force_connect=False):
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
                                                    dst_pos, src=src_pos),)
            point = working_set.pop(0)
            if len(point) == 3:
                point, _, track_in = point
            finished_set.add(point)
            if is_src:
                points = self.get_port_neighbors(routing_resource, bus,
                                                 chan,
                                                 point, src_port)
            else:
                if track_in is None:
                    # sink to sink
                    # need to figure out the last track in
                    assert len(final_path) > 0
                    # get previous track in
                    found, track_in = self.get_track_in_from_path(src_pos,
                                                                  src_port,
                                                                  final_path)
                    if found:
                        assert track_in is not None
                if track_in is None:
                    points = self.get_port_neighbors(routing_resource, bus,
                                                     chan,
                                                     point, src_port)
                    is_src = True
                else:
                    points = self.get_neighbors(routing_resource,
                                                bus, chan, point, track_in,
                                                pin_ports,
                                                force_connect=force_connect)
                force_connect = False
            for entry in points:
                if is_src:
                    p, dir_out, dir_in = entry
                else:
                    p, dir_out, dir_in = entry
                if p in finished_set or entry in working_set or \
                        p in pos_set or (point, dir_out) in pos_set or \
                        (p, dir_in) in pos_set:
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
                            # re-route!
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

                # disable any out -> port or port -> out
                for p_port in routing_resource[p]["port"]:
                    ports = routing_resource[p]["port"][p_port]
                    if dir_out in ports:
                        ports.remove(dir_out)
                # if port != "reg":
                #     ports = routing_resource[p]["port"][port]
                #     ports.remove(dir_out)
                # else:
                #    assert self.fold_reg
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
                if not(isinstance(pin_info[-1], str)):
                    raise Exception("Unknown pin_info " + str(pin_info))
                # no turn sink
                # need to delete the port path
                # it might be redundant for PE tiles, but for IO ports
                # it's critical?
                conn, pos, port = pin_info
                if port == "reg":
                    assert self.fold_reg
                else:
                    ports = routing_resource[pos]["port"][port]
                    if conn in ports:
                        ports.remove(conn)
                # disable any coming in connections
                res = self.get_route_resource(self.board_meta,
                                              routing_resource,
                                              pos)
                conn_remove = set()
                for conn1, conn2 in res:
                    if conn1 == conn:
                        conn_remove.add((conn1, conn2))
                for entry in conn_remove:
                    res.remove(entry)

            elif len(pin_info) == 4:
                # need to take care of the extra out
                # [dir_in, conn, current_point, port]
                dir_in = pin_info[0]
                conn = pin_info[1]  # conn is out
                pos = pin_info[2]
                res = routing_resource[pos]["route_resource"]
                conn_remove = set()
                for conn1, conn2 in res:
                    if conn2 == conn:
                        conn_remove.add((conn1, conn2))
                    elif conn1 == dir_in:
                        conn_remove.add((conn1, conn2))
                for entry in conn_remove:
                    res.remove(entry)
                # ports = routing_resource[pos]["port"][pin_info[-1]]
                # ports.remove(conn)

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
                         j in range(width - margin, width)):  # IO is special:
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
                    # if self.layout_board[j][i] == "m" or \
                    #         self.layout_board[j - 1][i] == "m":
                    #     res /= 2
                    color = int(255 * res / 4 / self.channel_width)
                draw_cell(draw, (i, j), color=(255 - color, 0, color),
                          scale=scale)
        plt.axis('off')
        plt.imshow(im)
        plt.show()
        file_dir = os.path.dirname(os.path.realpath(__file__))
        output_png = self.design_name + "_route.png"
        output_dir = os.path.join(file_dir, "figures")
        if os.path.isdir(output_dir):
            output_path = os.path.join(output_dir, output_png)
            im.save(output_path)
            print("Image saved to", output_path)


def main():
    parser = ArgumentParser("CGRA Router")
    parser.add_argument("-i", "--input", help="Packed netlist file, " +
                                              "e.g. harris.packed",
                        required=True, action="store", dest="packed_filename")
    parser.add_argument("-o", "--output", help="Routing result, " +
                                               "e.g. harris.route",
                        required=True, action="store",
                        dest="route_file")
    parser.add_argument("-c", "--cgra", help="CGRA architecture file",
                        required=True, action="store", dest="arch_filename")
    parser.add_argument("-p", "--placement", help="Placement file",
                        required=True, action="store",
                        dest="placement_filename")
    parser.add_argument("--no-reg-fold", help="If set, the placer will treat " +
                                              "registers as PE tiles",
                        action="store_true",
                        required=False, dest="no_reg_fold", default=False)
    parser.add_argument("--no-vis", help="If set, the router won't show " +
                        "visualization result for routing",
                        action="store_true",
                        required=False, dest="no_vis", default=False)
    args = parser.parse_args()

    arch_filename = args.arch_filename
    packed_filename = args.packed_filename
    route_file = args.route_file

    vis_opt = not args.no_vis
    fold_reg = not args.no_reg_fold

    placement_filename = args.placement_filename
    meta = parse_cgra(arch_filename, fold_reg=fold_reg)["CGRA"]
    r = Router(arch_filename, meta, packed_filename, placement_filename)
    r.route()
    if vis_opt:
        r.vis_routing_resource()
    # r.compute_stats()

    save_routing_result(r.route_result, route_file)


if __name__ == "__main__":
    main()
