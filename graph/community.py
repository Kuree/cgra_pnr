from __future__ import print_function
import leidenalg as la
import igraph as ig


def construct_digraph(nets):
    # we create a mapping from blk_id to int
    blk_to_id = {}
    id_to_blk = {}
    for _, net in nets.items():
        for blk_id in net:
            if blk_id not in blk_to_id:
                node_id = len(blk_to_id)
                blk_to_id[blk_id] = node_id
                id_to_blk[node_id] = blk_id
    g = ig.Graph(len(blk_to_id), directed=True)
    for net_id, net in nets.items():
        src = net[0]
        src_id = blk_to_id[src]
        assert len(net) > 1
        for i in range(1, len(net)):
            dst_id = blk_to_id[net[i]]
            g.add_edge(src_id, dst_id)

    return g, id_to_blk


def get_cluster(graph, id_to_block, num_iter=15, seed=0):
    partition = la.find_partition(graph, la.ModularityVertexPartition,
                                  n_iterations=num_iter,
                                  seed=seed)
    membership = partition.membership
    assert len(membership) == len(id_to_block)
    clusters = {}
    ignored_types = {"i", "I"}
    for node_id, cluster_id in enumerate(membership):
        blk_id = id_to_block[node_id]
        if blk_id[0] in ignored_types:
            continue
        if cluster_id not in clusters:
            clusters[cluster_id] = set()
        clusters[cluster_id].add(blk_id)

    # sort them
    # for cluster_id in clusters:
    #    clusters[cluster_id].sort(key=lambda x: int(x[1:]))
    return clusters


def partition_netlist(netlist):
    g, id_to_block = construct_digraph(netlist)
    clusters = get_cluster(g, id_to_block)
    return clusters

