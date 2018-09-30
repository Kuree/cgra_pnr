import numpy as np
import six


def reduce_cluster_graph(netlists, clusters, fixed_blocks,
                         cluster_id=None):
    """NOTE: cluster_blocks holds block IDs, not cell locations"""
    if cluster_id is None:
        cluster_id = 0
        condense_self = True
    else:
        condense_self = False
    current_cluster = clusters[cluster_id]
    new_netlist = {}
    for net_id in netlists:
        netlist = set(netlists[net_id])
        if len(netlist.intersection(current_cluster)) > 0:
            # we need to reduce the net
            new_net = []
            for blk_id in netlist:
                if blk_id in current_cluster:
                    if condense_self:
                        new_node = "x" + str(cluster_id)
                        new_net.append(new_node)
                    else:
                        new_net.append(blk_id)
                elif blk_id in fixed_blocks:
                    new_net.append(blk_id)
                else:
                    # search for all the other netlists
                    # we use "x" for clusters
                    found = False
                    for cid in clusters:
                        if cid == cluster_id:
                            continue
                        if blk_id in clusters[cid]:
                            new_node = "x" + str(cid)
                            new_net.append(new_node)
                            found = True
                            break
                    if not found:
                        raise Exception("not found blk", blk_id)

            new_netlist[net_id] = new_net
    return new_netlist






