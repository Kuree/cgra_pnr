# -*- coding: utf-8 -*-
from __future__ import print_function, division
import sys
import os
from arch import find_critical_path
from arch import parse_routing_result
from arch import compute_critical_delay, compute_total_wire
from arch import parse_placement, parse_cgra, compute_area_usage


def main():
    if len(sys.argv) != 4:
        print("Usage:", sys.argv[0], "<cgra_info.txt", "<netlist.json>",
              "<netlist.route>",
              file=sys.stderr)
        exit(1)
    cgra_file = sys.argv[1]
    netlist = sys.argv[2]
    route_file = sys.argv[3]
    packed_file = route_file.replace(".route", ".packed")
    placement_file = route_file.replace(".route", ".place")
    board_meta = parse_cgra(cgra_file)["CGRA"]
    net_path = find_critical_path(netlist, packed_file)
    routing_result = parse_routing_result(route_file)
    placement, _ = parse_placement(placement_file)
    timing_info = compute_critical_delay(net_path, routing_result, placement)
    total_time = sum([timing_info[key] for key in timing_info])
    print("Critical Path Timing:")
    print("Total:", total_time)

    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        meta = os.popen('stty size', 'r').read().split()
        cols = int(meta[-1])
        cols = int(cols)
        scale = cols - 15
    else:
        scale = 68
        cols = 80

    for entry in timing_info:
        time = timing_info[entry]
        percentage = int(time / total_time * 100)
        num_bar = int(percentage / (100 / scale))
        s = "{0:4s} {1} {2} {3}".format(entry.upper(),
                                        num_bar * '█', ' ' * (scale - num_bar),
                                        time)

        print(s)

    print("-" * cols)
    print("Area Usage:")
    usage = compute_area_usage(placement, board_meta[0])
    for entry in usage:
        percentage = usage[entry][0] / usage[entry][1] * 100
        num_bar = int(percentage / 100 * scale)
        print("{0:4s} {1} {2} {3:.2f}%".format(entry.upper(),
                                               num_bar * '█',
                                               ' ' * (scale - num_bar - 2),
                                               percentage))

    print("-" * cols)
    net_wire = compute_total_wire(routing_result)
    total_wire = sum([net_wire[x] for x in net_wire])
    print("Total wire:", total_wire)


if __name__ == '__main__':
    main()
