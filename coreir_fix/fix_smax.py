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
        f.seek(0, 0)
        raw_lines = f.readlines()
    connections = \
        data["namespaces"]["global"]["modules"]["DesignTop"]["connections"]
    instances = data["namespaces"]["global"]["modules"]["DesignTop"][
        "instances"]
    # first pass to find all the mux instances
    smax_set = find_smax(instances)
    print("We have", len(smax_set), "smaxes to fix:")
    for smax in smax_set:
        print(smax)

    # save to output
    count = 0
    with open(output_filename, "w+") as f:
        for i in range(len(raw_lines)):
            line = raw_lines[i]
            if "\"alu_op_debug\":[\"String\",\"max\"]" in line:
                count += 1
                line = line.replace("\"alu_op_debug\":[\"String\",\"max\"]",
                                    "\"alu_op_debug\":[\"String\",\"smax\"]")
            f.write(line)
        print("result saved to", output_filename)
    assert count == len(smax_set)


def find_smax(instances):
    smax_set = set()
    for instance_name in instances:
        instance = instances[instance_name]
        if "modargs" in instance:
            if "alu_op_debug" in instance["modargs"] and \
                    instance["modargs"]["alu_op_debug"][-1] == "max":
                smax_set.add(instance_name)
    return smax_set


if __name__ == '__main__':
    main()
