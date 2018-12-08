from __future__ import print_function
import sys
import os
from argparse import ArgumentParser
from pycyclone import RoutingGraph, SwitchBoxNode, PortNode, SwitchBoxSide
from pycyclone import Tile, RegisterNode, NodeType
from pycyclone import GlobalRouter
from pycyclone.util import get_side_int as gsi
from pycyclone.util import get_opposite_side as gos

from arch import parse_cgra, load_packed_file, parse_placement
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


def build_routing_graph(routing_resource):
    # FIXME:
    # read the number of track width from the graph
    g_1 = RoutingGraph()
    g_16 = RoutingGraph()
    for x, y in routing_resource:
        t = Tile()
        t.x = x
        t.y = y
        g_1.add_tile(t)
        g_16.add_tile(t)

    for x, y in routing_resource:
        res = routing_resource[(x, y)]["route_resource"]
        ports = routing_resource[(x, y)]["port"]
        # adding switch boxes
        sb = SwitchBoxNode(x, y, 0, 0)
        sb1 = SwitchBoxNode(0, 0, 0, 0)
        sb2 = SwitchBoxNode(0, 0, 0, 0)
        reg_count = 0
        for conn1, conn2 in res:
            width1, io1, side1, track1 = conn1
            width2, io2, side2, track2 = conn2

            assert io1 ^ io2 == 1  # always one in one out
            assert width1 == width2
            sb.width = width1
            sb1.width = width1
            sb2.width = width2

            sb.track = track1
            sb1.track = track1
            sb2.track = track2

            if width1 == 16:
                g = g_16
            else:
                g = g_1

            # FIXME
            # change this once a new interconnect is designed
            sb1.x, sb1.y = get_new_coord(x, y, side1)
            sb2.x, sb2.y = get_new_coord(x, y, side2)

            # side_1 = gos(side1)
            # side_2 = gsi(side1)
            # side_3 = gsi(side2)
            # side_4 = gos(side2)

            g.add_edge(sb1, sb, gos(side1), gsi(side1))
            g.add_edge(sb, sb2, gsi(side2), gos(side2))

        current_tile = g_16[(x, y)]
        for sb in current_tile.sbs:
            reg = RegisterNode("", x, y, sb.width,
                               sb.track)
            neighbors = list(sb)
            for node in neighbors:
                # FIXME
                # hack to get registers in
                # insert reg connection here
                if node.type != NodeType.SwitchBox:
                    continue
                reg.name = "reg" + str(reg_count)
                reg_count += 1
                side = sb.get_side(node)
                g_16.add_edge(sb, reg, side)
                # node.add_side_info(reg, gos(side))
                g_16.add_edge(reg, node, gos(side))

        # handling ports
        for port_name in ports:
            port = PortNode(port_name, x, y, 0)
            sb = SwitchBoxNode(0, 0, 0, 0)
            for width, io, side, track in ports[port_name]:
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
                if io == 0:
                    # this is coming in, so we need to recalculate the
                    # coordinates to see where the connection comes from
                    sb.x, sb.y = get_new_coord(x, y, side)
                    new_side = gos(side)
                    g.add_edge(sb, port, new_side)
                else:
                    sb.x, sb.y = x, y
                    g.add_edge(sb, port, gsi(side))

    return g_1, g_16


def assign_placement_nets(routers, placement, netlists, track_mode):
    for width in routers:
        r = routers[width]
        for blk_id in placement:
            x, y = placement[blk_id]
            r.add_placement(x, y, blk_id)
    for net_id in netlists:
        width = track_mode[net_id]
        r = routers[width]
        net = netlists[net_id]
        r.add_net(net_id, net)


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

    placement_filename = args.placement_filename
    meta = parse_cgra(arch_filename)["CGRA"]

    netlists, _, id_to_name, _, track_mode = load_packed_file(
        packed_filename, load_track_mode=True)

    placement, _ = parse_placement(placement_filename)
    raw_routing_resource = parse_routing_resource(arch_filename)
    routing_resource = build_routing_resource(raw_routing_resource)
    g_1, g_16 = build_routing_graph(routing_resource)
    r_1 = GlobalRouter(40, g_1)
    r_16 = GlobalRouter(40, g_16)
    assign_placement_nets({1: r_1, 16: r_16}, placement, netlists, track_mode)

    # route these nets
    r_1.route()
    r_16.route()


if __name__ == "__main__":
    main()
