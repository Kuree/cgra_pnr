from __future__ import print_function, division
import json
import sys
import networkx as nx


def is_conn_out(conn):
    port = conn.split(".")[-1]
    if port.isdigit():
        port = conn.split(".")[-2]
    if port.isdigit():
        assert conn.split(".")[0] == "self"
        if conn.split(".")[1] == "in":
            return True
        else:
            return False
    return port in ["out", "rdata"]


def fill_neighbor(node, g, finished_set):
    assert node not in finished_set
    for next_node in nx.neighbors(g, node):
        if next_node in finished_set:
            lb = finished_set[next_node]
            assert "$" not in lb
            finished_set[node] = lb
            break
    if node in finished_set:
        return finished_set[node]
    else:
        for next_node in nx.neighbors(g, node):
            lb = fill_neighbor(next_node, g, finished_set)
            finished_set[node] = lb
            assert "$" not in lb
            return lb


def digraph_down(g, node):
    working_set = [node]
    visited = set()
    while len(working_set) > 0:
        current_node = working_set.pop(0)
        visited.add(current_node)
        neighbor = list(g.successors(current_node))
        for n in neighbor:
            if n not in visited:
                working_set.append(n)
    visited.remove(node)
    return visited


def going_down(g, finished_set, node):
    nodes = digraph_down(g, node)
    for next_node in nodes:
        if next_node in finished_set:
            return finished_set[next_node]
    return ""


def cluster_kernels(flatten_file):
    with open(flatten_file) as f:
        data = json.load(f)
    design = data["namespaces"]["global"]["modules"]["DesignTop"]
    instances = design["instances"]
    connections = design["connections"]

    finished_set = {}

    g = nx.DiGraph()
    for conn1, conn2 in connections:
        conn1_out = is_conn_out(conn1)
        conn2_out = is_conn_out(conn2)
        if not conn1_out ^ conn2_out:
            print(conn1, conn2, conn1_out, conn2_out)
        assert conn1_out ^ conn2_out
        conn1_name = conn1.split(".")[0]
        conn2_name = conn2.split(".")[0]
        if "self" in conn1_name:
            conn1_name = conn1
        if "self" in conn2_name:
            conn2_name = conn2
        if conn1_out:
            g.add_edge(conn1_name, conn2_name)
        else:
            g.add_edge(conn2_name, conn1_name)

    nodes = list(g.nodes())

    # reversed_graph
    reversed_g = nx.reverse(g)

    # first pass to get LB names
    lb_set = set()
    lb_index = {}
    reverse_lb_index = {}
    for node in nodes:
        if "lb" == node[:2]:
            lb_name = node.split("$")[0]
            if "genref" not in instances[node]:
                continue
            if instances[node]["genref"] == "coreir.mem" and "wen" not in node:
                lb_name = lb_name.replace("_update_stream", "")
                lb_name = lb_name.replace("_stream", "")
                lb_name = lb_name.replace("lb", "")
                lb_set.add(lb_name)
                if lb_name not in lb_index:
                    lb_index[lb_name] = []
                lb_index[lb_name].append(node)
                reverse_lb_index[node] = lb_name

    # fill in info
    # since the registers are expanded through lb
    # we can use its name to make decisions
    for lb in lb_set:
        for node in g.nodes():
            if node in finished_set:
                continue
            if lb in node:
                assert "$" not in lb
                finished_set[node] = lb

    lb_set = list(lb_set)
    # brute-force reordering
    lb_score = {}
    for lb in lb_set:
        lb_score[lb] = set()
        for node in lb_index[lb]:
            down_nodes = digraph_down(g, node)
            for current_node in down_nodes:
                if current_node in reverse_lb_index:
                    lb_name = reverse_lb_index[current_node]
                    if lb_name == lb:
                        continue
                    lb_score[lb].add(lb_name)
    lb_order = ["" for _ in range(len(lb_set))]
    for lb in lb_score:
        lb_order[len(lb_score[lb])] = lb

    for lb in lb_order:
        if len(lb) == 0:
            print("WARN: no ordering detected", file=sys.stderr)
            lb_order = lb_set
            lb_order.reverse()
            break

    # go through every node connected to the kernel
    # brute-force approach
    # reverse lb_set
    for lb in lb_order:
        for lb_node in lb_index[lb]:
            nodes = digraph_down(g, lb_node)
            for node in nodes:
                if node in finished_set:
                    continue
                finished_set[node] = lb

    # connect the self input to kernels
    io_nodes = set()
    for node in g.nodes():
        if "self.in" in node:
            assert node not in finished_set
            down_nodes = digraph_down(g, node)
            for next_node in down_nodes:
                if next_node in finished_set:
                    finished_set[node] = finished_set[next_node]
                    io_nodes.add(node)
                    break

    for node in io_nodes:
        down_nodes = digraph_down(g, node)
        for next_node in down_nodes:
            if next_node not in finished_set:
                fill_neighbor(next_node, g, finished_set)

    # leaf nodes
    total_nodes = set(g.nodes())
    should_finish = False
    while not should_finish:
        no_found = False
        for node in total_nodes:
            if node not in finished_set:
                lb = going_down(reversed_g, finished_set, node)
                if len(lb) == 0:
                    lb = going_down(g, finished_set, node)
                if len(lb) == 0:
                    no_found = True
                    continue
                finished_set[node] = lb
        if not no_found:
            should_finish = True

    # build clusters
    clusters = {}
    for instance_name in finished_set:
        lb_name = finished_set[instance_name]
        if lb_name not in clusters:
            clusters[lb_name] = set()
        clusters[lb_name].add(instance_name)

    # sanity check
    for instance_name in instances:
        assert instance_name in total_nodes
        kernel_name = finished_set[instance_name]
        if instance_name not in clusters[kernel_name]:
            print(instance_name, kernel_name)
            print(clusters.keys())
        assert instance_name in clusters[kernel_name]

    # rename the kernel name with index
    result = {}
    kernel_index = list(clusters.keys())
    for kernel_name in clusters:
        result[kernel_index.index(kernel_name)] = list(clusters[kernel_name])

    print("Num of kernels:", len(kernel_index))
    for kernel_name in kernel_index:
        print("  " + kernel_name + ":", len(clusters[kernel_name]))

    inter_count = eval_clustering(finished_set, connections)
    print("Inter-cluster connections:", inter_count)
    print("Connection reduction:", (len(connections) - inter_count)
          / len(connections))

    return result


def assign_clusters(premapped_cluster_file, id_to_name):
    name_to_id = {}
    for blk in id_to_name:
        name_to_id[id_to_name[blk]] = blk

    with open(premapped_cluster_file) as f:
        clusters = json.load(f)

    result = {}
    for c_id in clusters:
        cluster = set()
        for blk_name in clusters[c_id]:
            blk_id = name_to_id[blk_name]
            cluster.add(blk_id)
        result[c_id] = cluster
    return result


def eval_clustering(finished_set, connections):
    inter_count = 0
    for conn1, conn2 in connections:
        conn1_name = conn1.split(".")[0]
        conn2_name = conn2.split(".")[0]

        if "self" in conn1_name:
            inter_count += 1
            continue
        if "self" in conn2_name:
            inter_count += 1
            continue

        lb1 = finished_set[conn1_name]
        lb2 = finished_set[conn2_name]

        if lb1 != lb2:
            inter_count += 1

    return inter_count


def write_cls_file(filename, clusters):
    with open(filename, "w+") as f:
        for c_id in clusters:
            for instance_name in clusters[c_id]:
                f.write("{} {}\n".format(instance_name, c_id))


def main():
    if len(sys.argv) != 3:
        print("Usage:", sys.argv[0], "<premapped_netlist>",
              "<cluster_output>", file=sys.stderr)
        exit(1)
    netlist_file = sys.argv[1]
    output_file = sys.argv[2]
    clusters = cluster_kernels(netlist_file)
    write_cls_file(output_file, clusters)


if __name__ == "__main__":
    main()
