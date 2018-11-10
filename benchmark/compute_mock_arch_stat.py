from __future__ import print_function

import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)


def main():
    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "<board_size>", file=sys.stderr)
        exit(1)
    mock_size = int(sys.argv[1])
    from arch import mock_board_meta
    board_meta = mock_board_meta(mock_size)["CGRA"]

    num_pe = 0
    num_mem = 0

    board_layout = board_meta[0]
    for i in range(len(board_layout)):
        for j in range(len(board_layout[i])):
            blk_type = board_layout[i][j]
            if blk_type == "p":
                num_pe += 1
            elif blk_type == "m":
                num_mem += 1
    print("PE:", num_pe, "MEM:", num_mem)


if __name__ == "__main__":
    main()
