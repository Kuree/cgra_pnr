from __future__ import print_function
import sys
from pycyclone import RoutingGraph, SwitchBoxNode, PortNode, SwitchBoxSide
from pycyclone import GlobalRouter, SwitchBoxIO, Switch
from pycyclone.util import gsi, gii, get_disjoint_sb_wires
from pycyclone.io import dump_routing_graph

WIDTH = 1
NUM_TRACK = 2
SIDES = 4
SIZE = 2
SWITCH_ID = 0


def main():
    # constructing the routing graph
    switchbox = Switch(0, 0, NUM_TRACK, WIDTH, SWITCH_ID,
                       get_disjoint_sb_wires(NUM_TRACK))
    # 2 x 2 board with 2 routing tracks
    g = RoutingGraph(SIZE, SIZE, switchbox)
    # each tile has 2 ports, "in" and "out"
    in_port = PortNode("in", 0, 0, WIDTH)
    out_port = PortNode("out", 0, 0, WIDTH)
    # placeholder for sb
    sb = SwitchBoxNode(0, 0, WIDTH, 0, SwitchBoxSide.Bottom,
                       SwitchBoxIO.SB_IN)
    for t_p in g:
        tile = g[t_p]
        in_port.x = tile.x
        in_port.y = tile.y
        out_port.x = tile.x
        out_port.y = tile.y
        for i in range(NUM_TRACK):
            sb.track = i
            sb.x = tile.x
            sb.y = tile.y

            # out can go any sides
            for side in range(SIDES):
                sb.side = gsi(side)
                sb.io = SwitchBoxIO.SB_OUT
                g.add_edge(out_port, sb)

            # only left or right can come in
            for io in range(Switch.IOS):
                sb.io = gii(io)
                sb.side = SwitchBoxSide.Left
                g.add_edge(sb, in_port)
                sb.side = SwitchBoxSide.Right
                g.add_edge(sb, in_port)

    # wire these switch boxes together
    for y in range(SIZE - 1):
        # connect from top to bottom and bottom to top
        for x in range(SIZE):
            for track in range(NUM_TRACK):
                sb_top = SwitchBoxNode(x, y, WIDTH, track,
                                       SwitchBoxSide.Bottom,
                                       SwitchBoxIO.SB_OUT)
                sb_bottom = SwitchBoxNode(x, y + 1, WIDTH, track,
                                          SwitchBoxSide.Top,
                                          SwitchBoxIO.SB_IN)
                g.add_edge(sb_top, sb_bottom)

                sb_bottom.io = SwitchBoxIO.SB_OUT
                sb_top.io = SwitchBoxIO.SB_IN
                g.add_edge(sb_bottom, sb_top)

    for y in range(SIZE):
        # connect from left to right and right to left
        for x in range(SIZE - 1):
            for track in range(NUM_TRACK):
                sb_left = SwitchBoxNode(x, y, WIDTH, track,
                                        SwitchBoxSide.Right,
                                        SwitchBoxIO.SB_OUT)
                sb_right = SwitchBoxNode(x + 1, y, WIDTH, track,
                                         SwitchBoxSide.Left,
                                         SwitchBoxIO.SB_IN)
                g.add_edge(sb_left, sb_right)

                sb_right.io = SwitchBoxIO.SB_OUT
                sb_left.io = SwitchBoxIO.SB_IN
                g.add_edge(sb_right, sb_left)

    # create a global router and do the configuration in order
    r = GlobalRouter(20, g)
    # add placement
    placement = {"p0": (0, 0), "p1": (0, 1), "p2": (1, 0), "p3": (1, 1)}
    for blk_id in placement:
        x, y = placement[blk_id]
        r.add_placement(x, y, blk_id)

    netlist = {"n1": [("p0", "out"), ("p3", "in")],
               "n2": [("p1", "out"), ("p0", "in")],
               "n3": [("p3", "out"), ("p2", "in")],
              }

    for net_id in netlist:
        r.add_net(net_id, netlist[net_id])

    # route !
    r.route()

    result = r.realize()

    for net_id in result:
        print("NET:", net_id)
        segments = result[net_id]
        for seg in segments:
            seg_list = [str(x) for x in seg]
            print(" -> ".join(seg_list))
        print()

    if len(sys.argv) > 1:
        print("dump routing graph to", sys.argv[1])
        dump_routing_graph(g, sys.argv[1])


if __name__ == "__main__":
    main()
