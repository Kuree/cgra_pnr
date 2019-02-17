from __future__ import print_function
from arch.arch import parse_cgra
from pythunder.io import dump_layout
from argparse import ArgumentParser
import os


def main():
    parser = ArgumentParser("CGRA layout creation")
    parser.add_argument("-i", "--input", help="CGRA info file",
                        required=True, action="store", dest="cgra_filename")
    parser.add_argument("-o", "--output", help="layout file name for "
                                               "thunder placer",
                        required=True, action="store",
                        dest="layout_filename")
    parser.add_argument("-O", "--override", help="Override the existing one "
                                                 "if the output file exists",
                        required=False, default=False, action="store_true",
                        dest="override_layout")

    args = parser.parse_args()
    cgra_filename = args.cgra_filename
    layout_filename = args.layout_filename
    override_layout = args.override_layout
    if os.path.isfile(layout_filename) and not override_layout:
        print("found existing", layout_filename, "skipped")
        exit()
    layout = parse_cgra(cgra_filename)["CGRA"]
    dump_layout(layout, layout_filename)


if __name__ == "__main__":
    main()
