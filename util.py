import numpy as np
import six


def compute_hpwl(netlists, blk_pos):
    netlist_wirelength = {}
    for netid in netlists:
        min_x = 10000
        max_x = -1
        min_y = 10000
        max_y = -1
        for blk_id in netlists[netid]:
            x, y = blk_pos[blk_id]
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
        hpwl = max_x + max_y - min_x - min_y
        netlist_wirelength[netid] = hpwl
    return netlist_wirelength


def deepcopy(obj_to_copy):
    if isinstance(obj_to_copy, dict):
        d = obj_to_copy.copy()  # shallow dict copy
        for k, v in six.iteritems(d):
            d[k] = deepcopy(v)
    elif isinstance(obj_to_copy, list):
        d = obj_to_copy[:]  # shallow list/tuple copy
        i = len(d)
        while i:
            i -= 1
            d[i] = deepcopy(d[i])
    elif isinstance(obj_to_copy, set):
        d = obj_to_copy.copy()
    else:
        # tuple is fine since we're not modifying tuples
        d = obj_to_copy
    return d


def manhattan_distance(p1, p2):
    return abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])


def euclidean_distance(p1, p2):
    return int(np.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2))


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
    for netid in netlists:
        netlist = set(netlists[netid])
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

            new_netlist[netid] = new_net
    return new_netlist


def compute_centroids(cluster_cells, b_type):
    result = {}
    for cluster_id in cluster_cells:
        cells = set()
        for blk_type in cluster_cells[cluster_id]:
            if b_type != blk_type:
                continue
            cells.update(cluster_cells[cluster_id][blk_type])
        pos = compute_centroid(cells)
        result[cluster_id] = pos
    return result


def compute_centroid(cluster_cells):
    if type(cluster_cells) == list or type(cluster_cells) == set:
        x_sum = 0
        y_sum = 0
        cluster_size = len(cluster_cells)
        for cell in cluster_cells:
            x_sum += cell[0]
            y_sum += cell[1]
        pos_x = int(x_sum / cluster_size)
        pos_y = int(y_sum / cluster_size)
        return pos_x, pos_y
    elif type(cluster_cells) == dict:
        x_sum = 0
        y_sum = 0
        cluster_size = len(cluster_cells)
        for cell_id in cluster_cells:
            cell = cluster_cells[cell_id]
            x_sum += cell[0]
            y_sum += cell[0]
        pos_x = int(x_sum / cluster_size)
        pos_y = int(y_sum / cluster_size)
        return pos_x, pos_y
    else:
        raise Exception("Unknown type: " + str(type(cluster_cells)))
