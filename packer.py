from __future__ import print_function
from arch.cgra_packer import save_packing_result
from argparse import ArgumentParser

if __name__ == "__main__":
    parser = ArgumentParser("CGRA Packing tool")
    parser.add_argument("-n", "--netlist", help="Mapped netlist file, " +
                                                "e.g. harris.json",
                        required=True, action="store", dest="input")
    parser.add_argument("-o", "--output", help="Packed netlist file, " +
                                               "e.g. harris.packed",
                        required=True, action="store", dest="output")
    parser.add_argument("--no-reg-fold", help="If set, the packer will turn " +
                        "registers into PE tiles", action="store_true",
                        required=False, dest="no_reg_fold", default=False)
    args = parser.parse_args()
    filename = args.input
    packed = args.output
    fold_reg = not args.no_reg_fold
    save_packing_result(filename, packed, fold_reg=fold_reg)
