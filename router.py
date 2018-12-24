from __future__ import print_function
import sys
import os
from argparse import ArgumentParser
import pycyclone
from pycyclone import GlobalRouter, SwitchBoxIO, Switch
from pycyclone.io import load_placement, load_netlist, setup_router_input
from pycyclone.io import load_routing_graph

from process_graph import GRAPH_16, GRAPH_1


def main():
    parser = ArgumentParser("CGRA Router")
    parser.add_argument("-i", "--input", help="Packed netlist file, " +
                                              "e.g. harris.packed",
                        required=True, action="store", dest="packed_filename")
    parser.add_argument("-o", "--output", help="Routing result, " +
                                               "e.g. harris.route",
                        required=True, action="store",
                        dest="route_file")
    parser.add_argument("-g", "--graph", help="Routing graph folder",
                        required=True, action="store", dest="graph_dirname")
    parser.add_argument("-p", "--placement", help="Placement file",
                        required=True, action="store",
                        dest="placement_filename")

    args = parser.parse_args()

    packed_filename = args.packed_filename
    route_file = args.route_file
    graph_dirname = args.graph_dirname

    print("reading input files and constructing routing graph")
    placement_filename = args.placement_filename
    g1_filename = os.path.join(graph_dirname, GRAPH_1)
    g16_filename = os.path.join(graph_dirname, GRAPH_16)

    g_1 = load_routing_graph(g1_filename)
    g_16 = load_routing_graph(g16_filename)

    r_1 = GlobalRouter(40, g_1)
    r_16 = GlobalRouter(40, g_16)

    setup_router_input(r_1, packed_filename, placement_filename, 1)
    setup_router_input(r_16, packed_filename, placement_filename, 16)

    # parameter settings
    r_1.set_init_pn(10000)
    r_16.set_init_pn(10000)

    # route these nets
    print("start routing")
    r_1.route()
    r_16.route()

    if os.path.isfile(route_file):
        print("removing existing", route_file)
        os.remove(route_file)
    print("saving result to", route_file)
    pycyclone.io.dump_routing_result(r_1, route_file)
    pycyclone.io.dump_routing_result(r_16, route_file)


if __name__ == "__main__":
    main()
