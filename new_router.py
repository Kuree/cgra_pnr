from __future__ import print_function
import sys
import os
from argparse import ArgumentParser
import pycyclone
from pycyclone import RoutingGraph, SwitchBoxNode, PortNode, SwitchBoxSide
from pycyclone import Tile, RegisterNode, NodeType
from pycyclone import GlobalRouter, SwitchBoxIO, Switch
from pycyclone.util import get_side_int as gsi, get_uniform_sb_wires, gsv
from pycyclone.util import get_opposite_side as gos
from pycyclone.io import load_placement, load_netlist, setup_router_input

from arch import parse_cgra
from arch.cgra_route import parse_routing_resource, build_routing_resource

REG_DELAY = 10
SWITCHBOX_DELAY = 50
ALU_DELAY = 200


def get_new_coord(x, y, side):
    # this is relative to the (x, y) itself
    if side == 0:
        return x + 1, y
    elif side == 1:
        return x, y + 1
    elif side == 2:
        return x - 1, y
    elif side == 3:
        return x, y - 1
    else:
        raise Exception(str(side) + " is not a valid side")


def is_fu_tile(layout, x, y):
    return layout[y][x] != ' ' and layout[y][x] is not None


def build_routing_graph(routing_resource, layout):
    # FIXME:
    # read the number of track width from the graph
    g_1 = RoutingGraph()
    g_16 = RoutingGraph()

    # just made some assumptions here. since this will
    # go away once fully integrate into garnet
    NUM_TRACK = 5
    SWITCH_ID = 0
    SIZE = len(layout)

    sb_16 = Switch(0, 0, NUM_TRACK, 16, SWITCH_ID,
                   get_uniform_sb_wires(NUM_TRACK))
    sb_1 = Switch(0, 0, NUM_TRACK, 1, SWITCH_ID,
                  get_uniform_sb_wires(NUM_TRACK))
    sb_empty_1 = Switch(0, 0, NUM_TRACK, 1, SWITCH_ID + 1, set())
    sb_empty_16 = Switch(0, 0, NUM_TRACK, 16, SWITCH_ID + 2, set())
    tiles = list(routing_resource.keys())
    for i in range(2):
        tiles.sort(key=lambda x: x[i])
    for x, y in tiles:
        if not is_fu_tile(layout, x, y):
            continue
        if len(routing_resource[(x, y)]["route_resource"]) == 0 and\
            "out" not in routing_resource[(x, y)]["port"]:
            continue
        t1 = Tile(x, y, sb_1)
        t16 = Tile(x, y, sb_16)
        g_1.add_tile(t1)
        g_16.add_tile(t16)

    for y in range(SIZE - 1):
        for x in range(SIZE):
            if (not is_fu_tile(layout, x, y)) or \
                    (not is_fu_tile(layout, x, y + 1)):
                continue
            if not g_16.has_tile(x, y) or not g_16.has_tile(x, y + 1):
                continue
            for width in [1, 16]:
                if width == 1:
                    g = g_1
                else:
                    g = g_16
                for track in range(NUM_TRACK):
                    sb_top = SwitchBoxNode(x, y, width, track,
                                           SwitchBoxSide.Bottom,
                                           SwitchBoxIO.SB_OUT)
                    sb_bottom = SwitchBoxNode(x, y + 1, width, track,
                                              SwitchBoxSide.Top,
                                              SwitchBoxIO.SB_IN)
                    g.add_edge(sb_top, sb_bottom)
                    # also add reg as well
                    if width == 16:
                        reg1 = RegisterNode("reg_" + str(track) + "_"
                                            + str(gsv(SwitchBoxSide.Bottom)),
                                            x, y,
                                            16,
                                            track)
                        g.add_edge(sb_top, reg1)
                        g.add_edge(reg1, sb_bottom)

                    sb_bottom.io = SwitchBoxIO.SB_OUT
                    sb_top.io = SwitchBoxIO.SB_IN
                    g.add_edge(sb_bottom, sb_top)
                    if width == 16:
                        reg2 = RegisterNode("reg_" + str(track) + "_"
                                            + str(gsv(SwitchBoxSide.Top)),
                                            x, y + 1,
                                            16,
                                            track)
                        g.add_edge(sb_bottom, reg2)
                        g.add_edge(reg2, sb_top)

    for y in range(SIZE):
        # connect from left to right and right to left
        for x in range(SIZE - 1):
            if (not is_fu_tile(layout, x, y)) or \
                    (not is_fu_tile(layout, x + 1, y)):
                continue
            if not g_16.has_tile(x, y) or not g_16.has_tile(x + 1, y):
                continue
            for width in [1, 16]:
                if width == 1:
                    g = g_1
                else:
                    g = g_16
                for track in range(NUM_TRACK):
                    sb_left = SwitchBoxNode(x, y, width, track,
                                            SwitchBoxSide.Right,
                                            SwitchBoxIO.SB_OUT)
                    sb_right = SwitchBoxNode(x + 1, y, width, track,
                                             SwitchBoxSide.Left,
                                             SwitchBoxIO.SB_IN)
                    g.add_edge(sb_left, sb_right)
                    # also add reg as well
                    if width == 16:
                        reg1 = RegisterNode("reg_" + str(track) + "_"
                                            + str(gsv(SwitchBoxSide.Right)),
                                            x, y,
                                            16,
                                            track)
                        g.add_edge(sb_left, reg1)
                        g.add_edge(reg1, sb_right)

                    sb_right.io = SwitchBoxIO.SB_OUT
                    sb_left.io = SwitchBoxIO.SB_IN
                    g.add_edge(sb_right, sb_left)
                    # also add reg as well
                    if width == 16:
                        reg2 = RegisterNode("reg_" + str(track) + "_"
                                            + str(gsv(SwitchBoxSide.Left)),
                                            x + 1, y,
                                            16,
                                            track)
                        g.add_edge(sb_right, reg2)
                        g.add_edge(reg2, sb_left)
    for x, y in tiles:
        ports = routing_resource[(x, y)]["port"]
        port_io = routing_resource[(x, y)]["port_io"]

        if not is_fu_tile(layout, x, y):
            for port in ports:
                assert len(ports[port]) == 0
            continue
        if not g_16.has_tile(x, y):
            continue

        # handling ports
        # sort them
        port_names = list(ports.keys())
        port_names.sort()
        for port_name in port_names:
            port = PortNode(port_name, x, y, 0)
            sb = SwitchBoxNode(0, 0, 0, 0, SwitchBoxSide.Bottom,
                               SwitchBoxIO.SB_OUT)
            port_entries = list(ports[port_name])
            # in-place sort
            for i in range(4):
                port_entries.sort(key=lambda x: x[i])
            for width, io, side, track in port_entries:
                if width == 16:
                    g = g_16
                else:
                    g = g_1
                if port.width == 0:
                    port.width = width
                else:
                    assert port.width == width
                sb.width = width
                sb.track = track
                # a lot of complications
                io_dir = port_io[port_name]
                if io_dir == 0:
                    sb.io = SwitchBoxIO.SB_OUT
                    if io == 0:
                        # this is coming in, so we need to recalculate the
                        # coordinates to see where the connection comes from
                        sb.x, sb.y = get_new_coord(x, y, side)
                        if not g.has_tile(sb.x, sb.y):
                            continue
                        new_side = gos(side)
                        sb.side = new_side
                        g.add_edge(sb, port)

                        # we also need to connect the registers
                        if width == 16:
                            reg = RegisterNode("reg_" + str(track) + "_"
                                               + str(gsv(new_side)),
                                               sb.x, sb.y,
                                               16,
                                               track)
                            g.add_edge(reg, port)

                    else:
                        sb.x, sb.y = x, y
                        sb.side = gsi(side)
                        g.add_edge(sb, port)
                else:
                    sb.x, sb.y = x, y
                    sb.side = gsi(side)
                    sb.io = SwitchBoxIO.SB_OUT
                    g.add_edge(port, sb)

    return g_1, g_16


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
    parser.add_argument("--no-vis", help="If set, the router won't show " +
                                         "visualization result for routing",
                        action="store_true",
                        required=False, dest="no_vis", default=False)
    args = parser.parse_args()

    arch_filename = args.arch_filename
    packed_filename = args.packed_filename
    route_file = args.route_file

    print("reading input files and constructing routing graph")
    placement_filename = args.placement_filename
    meta = parse_cgra(arch_filename)["CGRA"]
    layout = meta[0]

    raw_routing_resource = parse_routing_resource(arch_filename)
    routing_resource = build_routing_resource(raw_routing_resource)
    g_1, g_16 = build_routing_graph(routing_resource, layout)
    r_1 = GlobalRouter(40, g_1)
    r_16 = GlobalRouter(40, g_16)

    # a little bit slow, but should be consistent with the C++ results
    setup_router_input(r_1, packed_filename, placement_filename, 1)
    setup_router_input(r_16, packed_filename, placement_filename, 16)

    # parameter settings
    r_1.set_init_pn(10000)
    r_16.set_init_pn(10000)

    # pycyclone.io.dump_routing_graph(g_16, "16bit.graph")

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
