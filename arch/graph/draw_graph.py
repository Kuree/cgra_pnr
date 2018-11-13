from __future__ import print_function
import sys
import networkx as nx
import json


def get_raw_connections(filename):
    with open(filename) as f:
        design = json.load(f)
    design_connections = design["namespaces"]["global"]["modules"]["DesignTop"]\
            ["connections"]
    return design_connections


def parse_connections(filename):
    design_connections = get_raw_connections(filename)
    connections = set()
    for conn1, conn2 in design_connections:
        # handle raw_names
        conn1_name = conn1.split(".")[0]
        conn2_name = conn2.split(".")[0]

        ports1 = conn1.replace(conn1_name, "")
        ports2 = conn2.replace(conn2_name, "")
        if "out" in ports1:
            is_out = True
            assert "out" not in ports2
        else:
            is_out = False
            assert "out" in ports2
        if is_out:
            connections.add((conn1_name, conn2_name))
        else:
            connections.add((conn2_name, conn1_name))
    return connections


def build_graph(connections):
    g = nx.DiGraph()
    for conn1, conn2 in connections:
        g.add_edge(conn1, conn2)
    return g


def main():
    if len(sys.argv) != 3:
        print("Usage:", sys.argv[0], "<input.json>", "<output_file", file=sys.stderr)
        exit(1)
    input_filename = sys.argv[1]
    output_filename = sys.argv[2]

    connections = parse_connections(input_filename)

    g = build_graph(connections)

    for node in g.nodes:
        g.nodes[node]["label"] = ""

    A = nx.nx_agraph.to_agraph(g)
    A.layout(prog='dot')
    A.draw(output_filename)

if __name__ == "__main__":
    main()
