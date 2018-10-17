from __future__ import print_function
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)


def compute_hpwl(netlists, blk_pos):
    hpwl = 0
    for net_id in netlists:
        min_x = 10000
        max_x = -1
        min_y = 10000
        max_y = -1
        for blk_id, _ in netlists[net_id]:
            x, y = blk_pos[blk_id]
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
        hpwl += max_x + max_y - min_x - min_y
    return hpwl


def check_placement(placement):
    used_site = set()
    for blk_id in placement:
        pos = placement[blk_id]
        assert pos not in used_site
        used_site.add(pos)


def main():
    from arch import parse_placement
    from arch import load_packed_file
    from arch.bookshelf import parse_pl
    if len(sys.argv) != 3:
        print("Usage:", sys.argv[0], "<packed>", "<placement>", file=sys.stderr)
        exit(1)
    packed_file = sys.argv[1]
    placement_file = sys.argv[2]
    netlist = load_packed_file(packed_file)[0]
    _, ext = os.path.splitext(placement_file)
    if ext == ".place":
        placement = parse_placement(placement_file)[0]
    elif ext == ".pl":
        placement = parse_pl(placement_file)
    else:
        raise Exception("Unrecognized file extension " + ext)

    hpwl = compute_hpwl(netlist, placement)

    print("HPWL:", hpwl)


if __name__ == "__main__":
    main()
