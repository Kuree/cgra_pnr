from __future__ import print_function
import sys
from arch.cgra import generate_bitstream


def main():
    if len(sys.argv) != 5:
        print("Usage:", sys.argv[0], "<arch_file>", "<netlist_file>",
              "<placement>", "<routing>", file=sys.stderr)
        exit(1)
    arch_file = sys.argv[1]
    netlist_file = sys.argv[2]
    placement_file = sys.argv[3]
    routing_file = sys.argv[4]
    print("INFO:", "arch:", arch_file)
    print("INFO:", "netlist:", netlist_file)
    print("INFO:", "placement:", placement_file)
    print("INFO:", "route:", routing_file)
    generate_bitstream(arch_file, netlist_file, placement_file, routing_file)


if __name__ == "__main__":
    main()
