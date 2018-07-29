import numpy as np


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


def make_board(width=20, height=20):
    board = []
    for i in range(height):
        board.append([])
        for j in range(width):
            board[i].append(None)
    return board


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


def compute_centroid(cluster_cells):
    result = {}
    for cluster_id in cluster_cells:
        cells = cluster_cells[cluster_id]
        cluster_size = len(cells)
        x_sum = 0
        y_sum = 0
        for cell in cells:
            x_sum += cell[0]
            y_sum += cell[1]
        pos_x = int(x_sum / cluster_size)
        pos_y = int(y_sum / cluster_size)
        result[cluster_id] = (pos_x, pos_y)
    return result


def save_placement(board_pos, id_to_name, dont_care, place_file):
    blk_keys = list(board_pos.keys())
    blk_keys.sort(key=lambda x:int(x[1:]))
    with open(place_file, "w+") as f:
        header = "{0}\t\t\t{1}\t{2}\t\t#{3}\n".format("Block Name",
                                                      "X",
                                                      "Y",
                                                      "Block ID")
        f.write(header)
        f.write("-" * len(header) + "\n")
        name_to_id = {}
        for blk_id in blk_keys:
            x, y = board_pos[blk_id]
            f.write("{0}\t\t{1}\t{2}\t\t#{3}\n".format(id_to_name[blk_id],
                                                          x,
                                                          y,
                                                          blk_id))
        # reverse the index
        for blk_id in id_to_name:
            name_to_id[id_to_name[blk_id]] = blk_id

        # write out absorbed components
        for blk_name in dont_care:
            connected_name = dont_care[blk_name]
            assert(connected_name is not None)
            connected_id = name_to_id[connected_name]
            x, y = board_pos[connected_id]
            blk_id = name_to_id[blk_name]
            f.write("{0}\t\t{1}\t{2}\t\t#{3}\n".format(blk_name,
                                                       x,
                                                       y,
                                                       blk_id))


def save_routing():
    pass
