from __future__ import print_function
import json
import numpy as np
import sys
import os.path
import networkx as nx

if __name__ == '__main__':
    # handle import
    sys.path.append(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))
    from netlist import is_conn_out
else:
    from ..netlist import is_conn_out


def build_raw_graph(raw_connections):
    g = nx.DiGraph()
    for conn1, conn2 in raw_connections:
        port1 = conn1.split(".")[1:]
        port2 = conn2.split(".")[1:]
        conn1_out = is_conn_out(port1)
        conn2_out = is_conn_out(port2)
        conn1_name = conn1.split(".")[0]
        conn2_name = conn2.split(".")[0]
        if not (conn1_out ^ conn2_out):
            conn1_out, _ = conn_heuristics(conn1, conn2)
        if conn1_out:
            g.add_edge(conn1_name, conn2_name)
        else:
            g.add_edge(conn2_name, conn1_name)
    return g


def conn_heuristics(conn1, conn2):
    conn1_out = False
    conn2_out = False
    if "in" in conn1 or "out" in conn2:
        conn1_out = False
        conn2_out = True
    elif "in" in conn2 or "in" in conn1:
        conn1_out = True
        conn2_out = False
    assert conn1_out ^ conn2_out
    return conn1_out, conn2_out


def cluster_on_embedding(embedding_file):
    if __name__ == "__main__":
        from os import sys, path
        sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
    num_clusters = 5
    from arch.cgra_packer import load_packed_file
    from arch.parser import parse_emb
    packed_file = embedding_file.replace(".emb", ".packed")
    _, folded_blocks, id_to_name = load_packed_file(packed_file)
    num_dim, emb = parse_emb(embedding_file)
    data_x = np.zeros((len(emb), num_dim))
    blks = list(emb.keys())
    for i in range(len(blks)):
        data_x[i] = emb[blks[i]]
    kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(data_x)
    cluster_ids = kmeans.labels_
    clusters = {}
    blk_reverse_index = {}
    for i in range(len(blks)):
        cid = cluster_ids[i]
        if cid not in clusters:
            clusters[cid] = {blks[i]}
        else:
            clusters[cid].add(blks[i])
        blk_reverse_index[blks[i]] = cid

    for blk, port in folded_blocks:
        folded_id = folded_blocks[(blk, port)][0]
        cid = blk_reverse_index[folded_id]
        clusters[cid].add(blk)
        pass

    return clusters, id_to_name


def handle_emb_clustering(filename, raw_names):
    emb_filename = filename.replace(".json", ".emb")
    clusters, id_to_name = cluster_on_embedding(emb_filename)
    raw_connections = get_raw_connections(filename)
    raw_graph = build_raw_graph(raw_connections)
    new_clusters = {}
    for cls_id in clusters:
        new_clusters[cls_id] = set()
        for blk in clusters[cls_id]:
            name = id_to_name[blk]
            has_found = False
            for raw_name in raw_names:
                if name in raw_name:
                    new_clusters[cls_id].add(raw_name)
                    has_found = True
                    break
            if not has_found:
                raise Exception("Cannot find " + name)
    visualize_raw_graph(raw_graph, new_clusters, filename="emb_partition.png")


def get_raw_connections(filename):
    with open(filename) as f:
        design = json.load(f)
    design_connections = design["namespaces"]["global"]["modules"]["DesignTop"]\
            ["connections"]
    return design_connections


def parse_connections(filename):
    design_connections = get_raw_connections(filename)
    connections = set()
    raw_names = set()
    for conn1, conn2 in design_connections:
        # handle raw_names
        raw_names.add(conn1.split(".")[0])
        raw_names.add(conn2.split(".")[0])

        if "$" in conn1 and "const" not in conn1:
            conn1_index = conn1.index("$")
        else:
            conn1_index = conn1.index(".")
        conn1_out = is_conn_out(conn1)
        if "$" in conn2 and "const" not in conn2:
            conn2_index = conn2.index("$")
        else:
            conn2_index = conn2.index(".")
        conn2_out = is_conn_out(conn2)

        if not conn1_out ^ conn2_out:
            print(conn1, conn2, conn1_out, conn2_out)
            print("Apply heuristics")
            conn1_out, conn2_out = conn_heuristics(conn1, conn2)
            assert (conn1_out ^ conn2_out)
        conn1_name = conn1[:conn1_index]
        conn2_name = conn2[:conn2_index]
        if conn1_name == conn2_name:
            continue
        if conn1_out:
            connections.add((conn1_name, conn2_name))
        else:
            connections.add((conn2_name, conn1_name))

    print("raw_connections:", len(design_connections),
          "connections:", len(connections),
          "pins:", len(raw_names))
    return connections, raw_names


def is_lb(name):
    return name[:2] == "lb" and "wen" not in name


def sorted_traverse_clustering(connections, raw_names):
    g, reversed_g, working_set, finished_set, lb_set = prepare_set(connections)
    # sort the graph to obtain lb order
    lbs = list(lb_set.keys())
    sorted_nodes = list(nx.topological_sort(g))
    lbs.sort(key=lambda node: sorted_nodes.index(node))
    parent_node = {}
    for lb in lbs:
        collection = set()
        ws = {lb}
        while len(ws) > 0:
            node = ws.pop()
            if node in lb_set and node != lb:
                collection.remove(node)
                continue
            else:
                for child in g.neighbors(node):
                    collection.add(child)
                    ws.add(child)
                    # override the old ones
                    if child in parent_node:
                        parent = parent_node[child]
                        if child in lb_set[parent]:
                            lb_set[parent].remove(child)
        lb_set[lb] = collection
        finished_set = finished_set.union(collection)
        for node in collection:
            parent_node[node] = lb

    print("Total nodes:", len(working_set), "absorbed:", len(finished_set))
    absorb_set = working_set.difference(finished_set)
    absorb_leaves(absorb_set, g, lb_set, parent_node)

    # expand the names to the actual clusters
    visualize(g, lb_set)

    clusters = {}
    lb_index = {}
    for index, lb in enumerate(lb_set):
        #clusters[index] = {lb}
        clusters[index] = set()
        lb_index[lb] = index

    for name in raw_names:
        # aggressive search
        has_found = False
        for simplified_name in parent_node:
            if simplified_name in name:
                parent = parent_node[simplified_name]
                index = lb_index[parent]
                clusters[index].add(name)
                has_found = True
                break
        if not has_found:
            raise Exception("Cannot find name " + name)
    return clusters


def visualize_raw_graph(graph, clusters, filename="kernel_partition.png"):
    from visualize import color_palette

    def to_hex(color):
        return "#{0:02X}{1:02X}{2:02X}".format(color[0], color[1], color[2])
    for cluster_id in clusters:
        for node in clusters[cluster_id]:
            color = color_palette[cluster_id % len(color_palette)]
            graph.nodes[node]["fillcolor"] = to_hex(color)
            graph.nodes[node]["color"] = to_hex(color)
            graph.nodes[node]["style"] = "filled"

    A = nx.nx_agraph.to_agraph(graph)
    A.layout(prog='dot')
    A.draw(filename)


def traverse_clustering(connections, raw_names):
    g, reversed_g, working_set, finished_set, lb_set = prepare_set(connections)

    parent_node = {}
    for lb in lb_set:
        collection = set()
        ws = {lb}
        while len(ws) > 0:
            node = ws.pop()
            if node in lb_set and node != lb:
                collection.remove(node)
                continue
            else:
                for child in g.neighbors(node):
                    collection.add(child)
                    ws.add(child)
        lb_set[lb] = collection
        finished_set = finished_set.union(collection)
        for node in collection:
            parent_node[node] = lb

    print("Total nodes:", len(working_set), "absorbed:", len(finished_set))
    absorb_set = working_set.difference(finished_set)
    absorb_leaves(absorb_set, g, lb_set, parent_node)

    visualize(g, lb_set)


def prepare_set(connections):
    working_set = set()
    finished_set = set()
    lb_set = {}
    # establish working set
    for conn1, conn2 in connections:
        working_set.add(conn1)
        working_set.add(conn2)
    # set up the linebuffer set
    for name in working_set:
        if is_lb(name):
            lb_set[name] = set()
            finished_set.add(name)
    # build a DAG
    g = nx.DiGraph()
    reversed_g = nx.DiGraph()
    for conn1, conn2 in connections:
        g.add_edge(conn1, conn2)
        reversed_g.add_edge(conn2, conn1)
    return g, reversed_g, working_set, finished_set, lb_set


def absorb_leaves(absorb_set, g, lb_set, parent_node):
    while len(absorb_set) != 0:
        node = absorb_set.pop()
        union = {node}
        terminate = False
        parent = None
        while not terminate:
            union_set = union.copy()
            for n in union_set:
                for child in nx.neighbors(g, n):
                    if child in parent_node:
                        terminate = True
                        parent = parent_node[child]
                    else:
                        union.add(child)
        assert parent is not None
        for n in union:
            parent_node[n] = parent
            lb_set[parent].add(n)
            if n in absorb_set:
                absorb_set.remove(n)


def lb_clustering(connections, raw_names):
    g, reversed_g, working_set, finished_set, lb_set = prepare_set(connections)

    sorted_nodes = list(nx.topological_sort(g))

    pruned_nodes = [x for x in sorted_nodes if
                    len(list(nx.neighbors(reversed_g, x))) > 0]
    assert(pruned_nodes[0] in lb_set)

    parent_node = {}
    current_lb = pruned_nodes[0]
    for i in range(1, len(pruned_nodes)):
        node = pruned_nodes[i]
        if node in lb_set:
            current_lb = node
        else:
            lb_set[current_lb].add(node)
            parent_node[node] = current_lb

    absorb_set = set(sorted_nodes).difference(set(pruned_nodes))
    print("Need to absorb", len(absorb_set), "nodes")
    absorb_leaves(absorb_set, g, lb_set, parent_node)

    visualize(g, lb_set)


def visualize(g, lb_set):
    sys.path.append(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))))
    from visualize import color_palette

    def to_hex(color):
        return "#{0:02X}{1:02X}{2:02X}".format(color[0], color[1], color[2])

    for index, lb in enumerate(lb_set):
        color = to_hex(color_palette[index % (len(color_palette))])
        g.node[lb]["color"] = color
        for node in lb_set[lb]:
            g.node[node]["color"] = color
            g.node[node]["fillcolor"] = color
            g.node[node]["style"] = "filled"
    A = nx.nx_agraph.to_agraph(g)
    A.layout(prog='dot')
    A.draw('dag_partition.png')


def main():
    if len(sys.argv) != 3:
        print("Usage:", sys.argv[0], "<netlist.json> <output.png>",
              file=sys.stderr)
        exit(1)

    filename = sys.argv[1]
    output_filename = sys.argv[2]
    connections, raw_names = parse_connections(filename)
    #lb_clustering(connections, raw_names)
    #traverse_clustering(connections, raw_names)
    clusters = sorted_traverse_clustering(connections, raw_names)

    raw_connections = get_raw_connections(filename)
    raw_graph = build_raw_graph(raw_connections)
    visualize_raw_graph(raw_graph, clusters, output_filename)
    # handle_emb_clustering(filename, raw_names)


if __name__ == "__main__":
    main()

