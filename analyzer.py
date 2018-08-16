from __future__ import print_function, division
import sys
from arch import find_critical_path
from arch import parse_routing_result
from arch import compute_critical_delay
from arch import parse_placement


def main():
    if len(sys.argv) != 3:
        print("Usage:", sys.argv[0], "<netlist.json>", "<netlist.route>",
              file=sys.stderr)
    netlist = sys.argv[1]
    route_file = sys.argv[2]
    packed_file = route_file.replace(".route", ".packed")
    placement_file = route_file.replace(".route", ".place")
    net_path = find_critical_path(netlist, packed_file)
    routing_result = parse_routing_result(route_file)
    placement, _ = parse_placement(placement_file)
    timing_info = compute_critical_delay(net_path, routing_result, placement)
    total_time = sum([timing_info[key] for key in timing_info])
    print("Critical Path Timing:")
    print("Total:", total_time)
    scale = 60
    for entry in timing_info:
        time = timing_info[entry]
        percentage = int(time / total_time * 100)
        num_bar = int(percentage / (100 / scale))
        print("{0:4s}".format(entry.upper()),
              num_bar * '█' + ' ' * (scale - num_bar),
              time)


if __name__ == '__main__':
    main()