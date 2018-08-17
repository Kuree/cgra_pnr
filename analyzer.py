# -*- coding: utf-8 -*-
from __future__ import print_function, division
import sys
import os
from arch import find_latency_path, compute_routing_usage
from arch import parse_routing_result, find_critical_path_delay
from arch import compute_latency, compute_total_wire
from arch import parse_placement, parse_cgra, compute_area_usage
from arch.cgra_route import parse_routing_resource, build_routing_resource


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
    routing_result = parse_routing_result(route_file)
    placement, _ = parse_placement(placement_file)

    if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
        meta = os.popen('stty size', 'r').read().split()
        cols = int(meta[-1])
        cols = int(cols)
        scale = cols - 15
    else:
        scale = 68
        cols = 80

    # print("Latency:")
    # print("Total:", total_time)
    # latency_info = compute_latency(net_path, routing_result, placement)
    # total_time = sum([latency_info[key] for key in latency_info])
    # for entry in latency_info:
    #     time = latency_info[entry]
    #     percentage = int(time / total_time * 100)
    #     num_bar = int(percentage / (100 / scale))
    #     s = "{0:4s} {1} {2} {3}".format(entry.upper(),
    #                                    num_bar * '█', ' ' * (scale - num_bar),
    #                                     time)
    # print(s)

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

    print("-" * cols)
    (src_name, blk_name, _, _), detailed_delay, total_delay = \
        find_critical_path_delay(netlist, packed_file, routing_result,
                                 placement)
    print("Critical Path:")
    s = "{0} -> {1}".format(src_name, blk_name)
    if len(s) > cols:
        print(src_name)
        print("\t->", blk_name)
    else:
        print(src_name, "->", blk_name)
    clock_speed = 1e6 / total_delay
    total_delay_formatted = "{:.2f} ns".format(total_delay / 1000)
    print("Delay:", total_delay_formatted, "Max Clock Speed:",
          "{0:.2f} MHz".format(clock_speed))
    for entry in detailed_delay:
        percentage = detailed_delay[entry] / total_delay * 100
        num_bar = int(percentage / 100 * scale)
        print("{0:4s} {1} {2} {3:.2f}%".format(entry.upper(),
                                               num_bar * '█',
                                               ' ' * (scale - num_bar - 2),
                                               percentage))

    print("-" * cols)
    r = parse_routing_resource(cgra_file)
    routing_resource = build_routing_resource(r)
    resource_usage = compute_routing_usage(routing_result, routing_resource,
                                           board_meta[0])
    for bus in resource_usage:
        print("BUS:", bus)
        for track in resource_usage[bus]:
            left = 0
            total = 0
            for _, l, t in resource_usage[bus][track]:
                left += l
                total += t
            percentage = (total - left) / total * 100
            num_bar = int(percentage / 100 * scale)
            print("TRACK {0} {1} {2} {3:.2f}%".format(track,
                                                      num_bar * '█',
                                                      ' ' * (scale -
                                                             num_bar - 5),
                                                      percentage))


if __name__ == '__main__':
    main()
