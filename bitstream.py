from __future__ import print_function
import sys
from util import parse_args
from arch.cgra import generate_bitstream


def main():
    options, argv = parse_args(sys.argv)
    if len(argv) != 5:
        print("Usage:", sys.argv[0], "[options]",
              "<arch_file>", "<netlist_file>",
              "<placement>", "<routing>", file=sys.stderr)
        print("[options]:", "-no-reg-fold", file=sys.stderr)
        exit(1)
    arch_file = argv[1]
    netlist_file = argv[2]
    placement_file = argv[3]
    routing_file = argv[4]
    fold_reg = True
    if "no-reg-fold" in options:
        fold_reg = False
    print("INFO:", "arch:", arch_file)
    print("INFO:", "netlist:", netlist_file)
    print("INFO:", "placement:", placement_file)
    print("INFO:", "route:", routing_file)
    print("INFO:", "fold_reg:", fold_reg)

    output_filename = netlist_file.replace(".packed", ".bsb")

    generate_bitstream(arch_file, netlist_file, placement_file, routing_file,
                       output_filename, fold_reg=fold_reg)


if __name__ == "__main__":
    main()
