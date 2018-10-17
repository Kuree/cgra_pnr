from __future__ import print_function
import sys
import json
import os


current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)


def main():
    if len(sys.argv) != 4:
        print("Usage: ", sys.argv[0], "<packed_file>", "<cluster_file>",
              "<new_cluster_file>", file=sys.stderr)
        exit(-1)
    packed_file = sys.argv[1]
    old_cluster_file = sys.argv[2]
    new_cluster_file = sys.argv[3]

    from arch import load_packed_file

    netlists, _, id_to_name, _ = load_packed_file(packed_file)
    with open(old_cluster_file) as f:
        clusters = json.load(f)

    # name to id
    name_to_id = {}
    for blk_id in id_to_name:
        name_to_id[id_to_name[blk_id]] = blk_id

    used_instances = set()
    for net_id in netlists:
        net = netlists[net_id]
        for blk_id, _ in net:
            blk_name = id_to_name[blk_id]
            used_instances.add(blk_name)

    remove_total = 0
    for c_id in clusters:
        remove_set = set()
        for blk_name in clusters[c_id]:
            if blk_name not in used_instances:
                remove_set.add(blk_name)
        for blk_name in remove_set:
            clusters[c_id].remove(blk_name)
        remove_total += len(remove_set)

    print("Removed", remove_total)
    with open(new_cluster_file, "w+") as f:
        for c_id in clusters:
            for blk_name in clusters[c_id]:
                f.write("{} {}\n".format(name_to_id[blk_name], c_id))


if __name__ == "__main__":
    main()