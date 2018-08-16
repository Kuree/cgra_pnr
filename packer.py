from __future__ import print_function
from arch.cgra_packer import save_packing_result
from util import parse_args
import sys

if __name__ == "__main__":
    options, argv = parse_args(sys.argv)
    mode = None
    if len(argv) != 2:
        print("Usage:", argv[0], "<netlist_filename>", file=sys.stderr)
        exit(1)
    if "cgra" in options:
        mode = "cgra"
    elif "fpga" in options:
        mode = "fpga"
    else:
        print("Please indicate either -cgra or -fpga", file=sys.stderr)
        exit(1)

    fold_reg = True
    if "no-reg-fold" in options:
        fold_reg = False
    filename = argv[1]
    if mode == "cgra":
        packed = filename.replace(".json", ".packed")
        save_packing_result(filename, packed, fold_reg=fold_reg)
        print("saved to", packed)
