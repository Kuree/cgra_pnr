from __future__ import print_function
import sys
from pycyclone import RoutingGraph, SwitchBoxNode, PortNode, SwitchBoxSide
from pycyclone import GlobalRouter, SwitchBoxIO, Switch
from pycyclone.util import gsi, gii, get_uniform_sb_wires
from pycyclone.io import load_routing_graph

WIDTH = 1
NUM_TRACK = 2
SIDES = 4
SIZE = 2
SWITCH_ID = 0


def main():
    # load the graph from command line
    if len(sys.argv) < 1:
        print("Usage:", sys.argv[0], "<routing.graph>", file=sys.stderr)
        exit(1)

    g = load_routing_graph(sys.argv[1])

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


if __name__ == "__main__":
    main()
