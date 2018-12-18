from __future__ import print_function
from argparse import ArgumentParser
from arch.cgra import generate_bitstream


def main():
    parser = ArgumentParser("CGRA Router")
    parser.add_argument("-n", "--netlist", help="Mapped netlist file, " +
                                                "e.g. harris.json",
                        required=True, action="store", dest="netlist_file")
    parser.add_argument("-i", "--input", help="Packed netlist file, " +
                                              "e.g. harris.packed",
                        required=True, action="store", dest="packed_filename")
    parser.add_argument("-o", "--output",
                        help="Bitstream result in bsb format" +
                        ", e.g. harris.bsb",
                        required=True, action="store",
                        dest="output_filename")
    parser.add_argument("-c", "--cgra", help="CGRA architecture file",
                        required=True, action="store", dest="arch_filename")
    parser.add_argument("-p", "--placement", help="Placement file",
                        required=True, action="store",
                        dest="placement_file")
    parser.add_argument("-r", "--routing", help="Routing file",
                        required=True, action="store",
                        dest="routing_file")
    parser.add_argument("--no-reg-fold", help="If set, the placer will treat " +
                                              "registers as PE tiles",
                        action="store_true",
                        required=False, dest="no_reg_fold", default=False)
    parser.add_argument("--io_json", help="File name for IO json that " +
                                          "specifies IO pads. Default is"
                                          "<output.json>",
                        required=False, action="store", dest="io_json",
                        default="")
    args = parser.parse_args()
    arch_filename = args.arch_filename
    netlist_file = args.netlist_file
    packed_filename = args.packed_filename
    placement_file = args.placement_file
    routing_file = args.routing_file
    output_filename = args.output_filename
    if len(args.io_json) > 0:
        io_json = args.io_json
    else:
        io_json = output_filename + ".json"

    fold_reg = not args.no_reg_fold

    print("INFO:", "arch:", arch_filename)
    print("INFO:", "netlist:", netlist_file)
    print("INFO:", "placement:", placement_file)
    print("INFO:", "route:", routing_file)
    print("INFO:", "fold_reg:", fold_reg)
    print("INFO:", "io_json:", io_json)

    generate_bitstream(arch_filename, netlist_file, packed_filename,
                       placement_file,
                       routing_file,
                       output_filename, io_json)


if __name__ == "__main__":
    main()
