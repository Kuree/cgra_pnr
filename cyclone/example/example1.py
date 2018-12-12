from __future__ import print_function
from pycyclone import RoutingGraph, SwitchBoxNode, PortNode, SwitchBoxSide
from pycyclone import GlobalRouter
from pycyclone.util import get_side_int as gsi

WIDTH = 1
NUM_TRACK = 2
SIDES = 4
SIZE = 2


def main():
    # constructing the routing graph
    sb = SwitchBoxNode(0, 0, WIDTH, 0)
    # 2 x 2 board with 2 routing tracks
    g = RoutingGraph(SIZE, SIZE, NUM_TRACK, sb)

    in_port = PortNode("in", 0, 0, WIDTH)
    out_port = PortNode("out", 0, 0, WIDTH)
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
                g.add_edge(out_port, sb, gsi(side))
            # only left or tight can come in
            g.add_edge(sb, in_port, SwitchBoxSide.Left)
            g.add_edge(sb, in_port, SwitchBoxSide.Right)

    # wire these switch boxes together
    for chan in range(NUM_TRACK):
        sb0 = g[(0, 0)].sbs[chan]
        sb1 = g[(0, 1)].sbs[chan]
        sb2 = g[(1, 0)].sbs[chan]
        sb3 = g[(1, 1)].sbs[chan]

        g.add_edge(sb0, sb1, SwitchBoxSide.Left)
        g.add_edge(sb1, sb0, SwitchBoxSide.Right)

        g.add_edge(sb0, sb2, SwitchBoxSide.Bottom)
        g.add_edge(sb2, sb0, SwitchBoxSide.Top)

        g.add_edge(sb3, sb1, SwitchBoxSide.Top)
        g.add_edge(sb1, sb3, SwitchBoxSide.Bottom)

        g.add_edge(sb3, sb2, SwitchBoxSide.Right)
        g.add_edge(sb2, sb3, SwitchBoxSide.Left)

    # create a global router and do the configuration in order
    r = GlobalRouter(20, g)
    placement = {"p0": (0, 0), "p1": (0, 1), "p2": (1, 0), "p3": (1, 1)}
    for blk_id in placement:
        x, y = placement[blk_id]
        r.add_placement(x, y, blk_id)

    netlist = {"n1": [("p0", "out"), ("p3", "in")],
               "n2": [("p1", "out"), ("p0", "in")],
               "n3": [("p3", "out"), ("p2", "in")],

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


if __name__ == "__main__":
    main()
