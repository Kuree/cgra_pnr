from __future__ import print_function
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)


def main():
    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "<packed>", file=sys.stderr)
        exit(-1)

    from arch import load_packed_file
    packed_filename = sys.argv[1]
    netlists, _, id_to_name, _ = \
        load_packed_file(packed_filename)

    pes = set()
    ios = set()
    mems = set()
    regs = set()

    for net_id in netlists:
        net = netlists[net_id]
        for blk_id, _ in net:
            if blk_id[0] == "p":
                pes.add(blk_id)
            elif blk_id[0] == "i":
                ios.add(blk_id)
            elif blk_id[0] == "m":
                mems.add(blk_id)
            elif blk_id[0] == "r":
                regs.add(blk_id)
    print("PE:", len(pes), "IO:", len(ios), "MEM:", len(mems), "REG:",
          len(regs), "Netlist:", len(netlists))


if __name__ == "__main__":
    main()
