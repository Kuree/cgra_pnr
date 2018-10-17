"""This is just used to estimate how fast NtuPlace can run"""
from __future__ import print_function

import os
import sys


current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)


def main():
    from arch import mock_board_meta, load_packed_file, save_placement
    if len(sys.argv) != 4:
        print("Usage:", sys.argv[0], "<board_size>", "<design.packed>",
              "<design.placement>", file=sys.stderr)
        exit(1)

    board_size = int(sys.argv[1])
    packed_filename = sys.argv[2]
    placement_filename = sys.argv[3]

    board_layout, _, _, _ = mock_board_meta(board_size)["CGRA"]
    netlists, _, id_to_name, _ = load_packed_file(packed_filename)

    m_pos = set()
    i_pos = set()
    p_pos = set()

    for y in range(len(board_layout)):
        for x in range(len(board_layout[y])):
            if board_layout[y][x] == "m":
                m_pos.add((x, y))
            elif board_layout[y][x] == "i":
                i_pos.add((x, y))
            else:
                p_pos.add((x, y))

    placement = {}
    for net_id in netlists:
        for blk, _ in netlists[net_id]:
            if blk in placement:
                continue
            blk_type = blk[0]
            if blk_type == "i":
                pos = i_pos.pop()
            elif blk_type == "m":
                pos = m_pos.pop()
            else:
                pos = p_pos.pop()
            placement[blk] = pos

    save_placement(placement, id_to_name, _, placement_filename)


if __name__ == "__main__":
    main()