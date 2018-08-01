from __future__ import print_function, division
from arch.cgra import parse_connection, parse_placement, save_routing_result
from arch import parse_cgra
import sys
import numpy as np
from visualize import draw_board, draw_cell
import matplotlib.pyplot as plt


class Router:
    def __init__(self, board_meta, netlist_filename, placement_filename,
                 avoid_congestion=True):
        self.board_meta = board_meta
        connections, id_to_name, netlists = parse_connection(netlist_filename)
        self.connections = connections
        self.id_to_name = id_to_name
        self.netlists = netlists

        placement, _ = parse_placement(placement_filename)
        self.placement = placement

        board_info = board_meta[-1]

        # NOTE: it's width x height
        self.board_size = (board_info["width"], board_info["height"])
        # TODO: fix this after parsing routing info from the arch
        self.channel_width = 5

        # result
        self.route_result = {}

        margin = board_info["margin"]
        # 4 directions
        self.routing_resource = np.zeros((self.board_size[1],
                                          self.board_size[0],
                                          4,
                                          self.channel_width), dtype=np.bool)
        for i in range(margin, self.board_size[0] - margin):
            for j in range(margin, self.board_size[1] - margin):
                for k in range(4):
                    for l in range(self.channel_width):
                        self.routing_resource[i][j][k][l] = True

        # disable routing resource among IO files
        height = board_info["height"]
        width = board_info["width"]
        layout_board = board_meta[0]
        for i in range(height):
            for j in range(width):
                if layout_board[i][j] == "i":
                    self.routing_resource[i][j][:, :] = True

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
                extra = 10 / route_resource
            dist += extra
        return dist

    @staticmethod
    def compute_direction(src, dst):
        """ right -> 0 bottom -> 1 left -> 2 top -> 3 """
        assert (src != dst)
        x1, y1 = src
        x2, y2 = dst
        assert ((abs(x1 - x2) == 0 and abs(y1 - y2) == 1) or (abs(x1 - x2) == 1
                                                              and abs(y1 - y2)
                                                              == 0))

        if x1 == x2:
            if y2 > y1:
                return 2
            else:
                return 0
        if y1 == y2:
            if x2 > x1:
                return 1
            else:
                return 3
        raise Exception("direction error " + "{}->{}".format(src, dst))

    def get_neighbors(self, chan, pos):
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
            direction = Router.compute_direction(pos, new_pos)
            if self.routing_resource[y][x][direction][chan]:
                results.append(new_pos)
        return results

    def route(self):
        print("INFO: Performing greedy BFS/A* routing")
        for net_id in self.netlists:
            net = self.netlists[net_id]

            src = net[0][0]
            # avoid going back
            net.sort(key=lambda pos:self.manhattan_dist(self.placement[src],
                                                        self.placement[pos[0]]))

            dst_set_cpy = net[1:]
            route_path = {}
            # TODO: change how to present failure
            failed_route = [None] * 200
            for chan in range(self.channel_width):
                final_path = []
                dst_set = dst_set_cpy[:]
                src_pos = self.placement[src]
                while len(dst_set) > 0:
                    dst = dst_set.pop(0)[0]
                    dst_pos = self.placement[dst]

                    # self loop prevention
                    # this will happen if two operands share the same input
                    if dst_pos == src_pos:
                        # skip over the loop
                        src_pos = dst_pos
                        continue
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
                        points = self.get_neighbors(chan, point)
                        for p in points:
                            if p in finished_set or p in working_set or \
                                    p in final_path:
                                # we have already explored this position
                                continue
                            if p in final_path:
                                pass
                            link[p] = point  # point backwards
                            depth[p] = depth[point] + 1
                            if p == dst_pos:
                                # we have found it!
                                terminate = True
                                break
                            else:
                                working_set.append(p)
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
            # find the minimum route path
            min_chan = 0
            for i in range(1, self.channel_width):
                if len(route_path[i]) < len(route_path[min_chan]):
                    min_chan = i
            if len(route_path[min_chan]) == len(failed_route):
                raise Exception("Failed to route for net " + net_id)
            # add the final path to the design
            self.route_result[net_id] = (min_chan, route_path[min_chan])
            # update routing resource
            path = route_path[min_chan]
            for index in range(0, len(path) - 1):
                path_src = path[index]
                path_dst = path[index + 1]
                direction = Router.compute_direction(path_src, path_dst)
                path_src_x, path_src_y = path_src
                path_dst_x, path_dst_y = path_dst
                self.routing_resource[path_src_y][path_src_x] \
                    [direction][min_chan] = False
                direction = Router.compute_direction(path_dst, path_src)
                self.routing_resource[path_dst_y][path_dst_x] \
                    [direction][min_chan] = False

    def vis_routing_resource(self):
        scale = 30
        margin = self.board_meta[-1]["margin"]
        height = self.board_meta[-1]["height"]
        width = self.board_meta[-1]["width"]
        im, draw = draw_board(self.board_size[0], self.board_size[1], scale)
        for i in range(self.board_size[0]):
            for j in range(self.board_size[1]):
                if self.board_meta[0][i][j] is None and \
                        (i in range(0, margin) or j in range(0, margin) or
                         i in range(height - margin, height) or
                         j in range(width - margin, width)):    # IO is special:
                    color = 255
                else:
                    route_r = self.routing_resource[i][j]
                    r = np.sum(route_r)
                    color = int(255 * r / 4 / self.channel_width)
                draw_cell(draw, (j, i), color=(255 - color, 0, color),
                          scale=scale)
        plt.imshow(im)
        plt.show()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage:", sys.argv[0], "<arch_file> <netlist.json>",
              "<netlist.place>", file=sys.stderr)

        exit(1)
    arch_file = sys.argv[1]
    meta = parse_cgra(arch_file)["CGRA"]
    r = Router(meta, sys.argv[2], sys.argv[3])
    r.route()
    r.vis_routing_resource()

    route_file = sys.argv[3].replace(".place", ".route")
    save_routing_result(r.route_result, route_file)

