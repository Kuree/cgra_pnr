from __future__ import print_function
import json
import sys


def main():
    if len(sys.argv) != 3:
        print("[Usage]:", sys.argv[0], "<mapped_netlist.json>",
              "<fixed_netlist.json>", file=sys.stderr)
        exit(1)

    input_filename = sys.argv[1]
    output_filename = sys.argv[2]
    with open(input_filename) as f:
        data = json.load(f)
    connections = \
        data["namespaces"]["global"]["modules"]["DesignTop"]["connections"]
    instances = data["namespaces"]["global"]["modules"]["DesignTop"][
        "instances"]
    # first pass to get all the connections
    duplicated_set = find_duplicates(connections)
    print("We have", len(duplicated_set), "consts to fix")

    while len(duplicated_set) > 0:
        const_name, const_conn = duplicated_set.pop()
        count = 0
        connection_to_remove = []
        connection_to_add = set()

        for conn1, conn2 in connections:
            if conn1 == const_conn:
                if count == 0:
                    count += 1
                    continue
                # fix it
                new_name = "{}${}".format(const_name, count)
                new_conn = fix_conn(instances, const_name, conn2, new_name)
                connection_to_add.add(new_conn)
                connection_to_remove.append([conn1, conn2])
                count += 1
            if conn2 == const_conn:
                if count == 0:
                    count += 1
                    continue
                # fix it
                new_name = "{}${}".format(const_name, count)
                new_conn = fix_conn(instances, const_name, conn1, new_name)
                connection_to_add.add(new_conn)
                connection_to_remove.append([conn1, conn2])
                count += 1

        for entry in connection_to_remove:
            connections.remove(entry)
        for entry in connection_to_add:
            connections.append(entry)

    # sanity check
    assert len(find_duplicates(connections)) == 0

    # save to output
    with open(output_filename, "w+") as f:
        print("save result to", output_filename)
        json.dump(data, f)


def fix_conn(instances, const_name, other_conn, new_name):
    print("Change", const_name, "to", new_name)
    instance = instances[const_name]
    instances[new_name] = instance
    return other_conn, new_name + ".out"


def find_duplicates(connections):
    const_set = set()
    duplicated_set = set()
    for conn1, conn2 in connections:
        # we only care about const so last port is fine
        conn1_name = conn1.split(".")[0]
        conn1_port = conn1.split(".")[-1]
        conn2_name = conn2.split(".")[0]
        conn2_port = conn2.split(".")[-1]
        if "const" == conn1_name[:5] and "out" == conn1_port:
            entry = (conn1_name, conn1)
            if entry in const_set:
                duplicated_set.add(entry)
            const_set.add(entry)
        if "const" == conn2_name[:5] and "out" == conn2_port:
            entry = (conn2_name, conn2)
            if entry in const_set:
                duplicated_set.add(entry)
            const_set.add(entry)
    return duplicated_set


if __name__ == '__main__':
    main()
