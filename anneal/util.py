import six


def compute_hpwl(netlists, blk_pos):
    hpwl = 0
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
        hpwl += max_x + max_y - min_x - min_y
    return hpwl


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


def collapse_netlist(clusters, netlist, fixed_position):
    netlist_1 = {}
    intra_cluster_count = {}
    for cluster_id in clusters:
        intra_cluster_count[cluster_id] = 0
    blk_index = {}
    for cluster_id in clusters:
        for blk in clusters[cluster_id]:
            blk_index[blk] = cluster_id

    # first pass
    # remove self connection
    for net_id in netlist:
        net = netlist[net_id]
        same_net = True
        first_blk = net[0]
        for blk in net:
            if blk not in blk_index or \
                    blk_index[blk] != blk_index[first_blk]:
                same_net = False
                break
        if same_net:
            cluster_id = blk_index[first_blk]
            intra_cluster_count[cluster_id] += 1
        else:
            netlist_1[net_id] = net
    # second pass
    # change into x format, as well as remove redundancy
    netlist_2 = {}
    for net_id in netlist_1:
        net = netlist_1[net_id]
        new_net = set()
        for blk in net:
            if blk in blk_index:
                cluster_id = blk_index[blk]
                node_id = "x" + str(cluster_id)
            else:
                assert blk in fixed_position
                node_id = blk
            new_net.add(node_id)
        assert len(new_net) > 1
        netlist_2[net_id] = new_net

    return netlist_2, intra_cluster_count


class ClusterException(Exception):
    def __init__(self, num_clusters):
        self.num_clusters = num_clusters
