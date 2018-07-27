from __future__ import print_function
from util import make_board, reduce_cluster_graph, save_placement
from parser import parse_netlist, parse_emb
from sa import SAClusterPlacer, SADetailedPlacer
import numpy as np
import os
import sys
import matplotlib.pyplot as plt
from visualize import draw_board, draw_cell, color_palette
from sklearn.cluster import KMeans
from multiprocessing import Pool
import random


def detailed_placement(args):
    clusters, cells, netlist, board, blk_pos = args
    detailed = SADetailedPlacer(clusters, cells, netlist, board, blk_pos,
                                multi_thread=True)
    detailed.anneal()
    return detailed.state


def is_legal(board, pos, blk_id):
    # we don't have the problem in FPGA where each cell may have multiple
    # blocks, i.e., IO pins.
    # hard code everything for now
    x, y = pos
    repeat = len(board[0]) // 4
    if board[y][x] is not None:
        return False
    if blk_id[0] == "i":
        if y == 0 or y == len(board) - 1:
            return x in range(2, len(board[0]) -2)
        elif x == 0 or x == len(board[0]) - 1:
            return y in range(2, len(board[0]) - 2)
        elif pos in [(2, 1), (1, 3), (3, len(board) - 2), (len(board[0]) - 2, 3)]:
            return True
        else:
            return False
    elif blk_id[0] == "m":
        if (x - 1) % 4 != 0:
            return False
        if y < 2 or y > len(board) - 4: # size
            return False
        # size
        return board[y + 1][x] is None and board[y - 1][x] is None
    elif blk_id[0] == "p":
        if x < 2 or y < 2 or x > len(board[0]) - 3 or y > len(board) - 3:
            return False
        return x not in [5 + 4 * i for i in range(repeat)]
    else:
        raise Exception("Unknown type for block", blk_id)


def place_on_board(board, block_id, pos):
    # we may have already placed that one
    if board[pos[1]][pos[0]] == block_id:
        return
    if not is_legal(board, pos, block_id):
        raise Exception("block: " + block_id + " is not legal on " + \
                        str(pos) + ". We have " + str(board[pos[1]][pos[0]]))
    x, y = pos
    board[y][x] = block_id


def place_special_blocks(board, blks, board_pos):
    # place io in the middle of each sides
    io_count = 0
    mem_count = 0
    io_start = len(board[0]) // 2 - 1
    for blk_id in blks:
        if blk_id[0] == "i":
            if io_count % 4 == 0:
                if io_count % 8 == 0:
                    x = io_start - io_count // 8
                else:
                    x = io_start + io_count // 8 + 1
                y = 0
            elif io_count % 4 == 1:
                tap = io_count - 1
                if tap % 8 == 0:
                    x = io_start - tap // 8
                else:
                    x = io_start + tap // 8 + 1
                y = len(board) - 1
            elif io_count % 4 == 2:
                tap = io_count - 2
                if tap % 8 == 0:
                    y = io_start - tap // 8
                else:
                    y = io_start + tap // 8 + 1
                x = 0
            else:
                tap = io_count - 3
                if tap % 8 == 0:
                    y = io_start - tap // 8
                else:
                    y = io_start + tap // 8 + 1
                x = len(board[0]) - 1
            pos = (x, y)
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
            io_count += 1
        elif blk_id[0] == "m":
            # just evenly distributed
            x = 5 + (mem_count % 4) * 4
            y = 4 + (mem_count // 4) * 2
            pos = (x, y)
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
            mem_count += 1
        else:
            raise Exception("Unknown block type", blk_id)


def main():
    if len(sys.argv) != 2:
        print("Usage:", sys.argv[0], "<netlist_file>", file=sys.stderr)
        exit(1)
    # force some internal library random sate

    netlist_filename = sys.argv[1]
    netlist_embedding = netlist_filename.replace(".json", ".emb")
    if not os.path.isfile(netlist_embedding):
        print(netlist_embedding, "not found in the same folder as",
              netlist_filename, file=sys.stderr)
        exit(1)

    num_dim, raw_emb = parse_emb(netlist_embedding, filter_complex=False)
    netlists, g, dont_care, id_to_name = parse_netlist(netlist_filename)
    board = make_board(20, 20)

    # stats
    io_count = 0
    mem_count = 0
    pe_count = 0
    for node in g.nodes():
        if node[0] == "i":
            io_count += 1
        elif node[0] == "m":
            mem_count += 1
        elif node[0] == "p":
            pe_count += 1
    print("PE:", pe_count, "MEM:", mem_count, "IO:", io_count)

    fixed_blk_pos = {}
    emb = {}
    special_blocks = set()
    for blk_id in raw_emb:
        if blk_id[0] != "p":
            special_blocks.add(blk_id)
        else:
            emb[blk_id] = raw_emb[blk_id]
    # place the spacial blocks first
    place_special_blocks(board, special_blocks, fixed_blk_pos)

    data_x = np.zeros((len(emb), num_dim))
    blks = list(emb.keys())
    for i in range(len(blks)):
        data_x[i] = emb[blks[i]]

    # simple heuristics to calculate the clusters
    num_clusters = int(np.ceil(len(emb) / 30)) + 1
    print("num of clusters", num_clusters)
    kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(data_x)
    cluster_ids = kmeans.labels_
    clusters = {}
    for i in range(len(blks)):
        cid = cluster_ids[i]
        if cid not in clusters:
            clusters[cid] = set([blks[i]])
        else:
            clusters[cid].add(blks[i])

    cluster_sizes = [len(clusters[s]) for s in clusters]
    print("cluster average:", np.average(cluster_sizes), "std:",
          np.std(cluster_sizes), "total:", np.sum(cluster_sizes))

    cluster_placer = SAClusterPlacer(clusters, netlists, board, fixed_blk_pos)


    cluster_placer.anneal()

    cluster_cells, centroids = cluster_placer.squeeze()

    # anneal with each cluster
    board_pos = fixed_blk_pos.copy()

    map_args = []

    for c_id in cluster_cells:
        cells = cluster_cells[c_id]
        new_netlist = reduce_cluster_graph(netlists, clusters,
                                           fixed_blk_pos, c_id)
        blk_pos = fixed_blk_pos.copy()
        for i in centroids:
            if i == c_id:
                continue
            node_id = "x" + str(i)
            pos = centroids[i]
            blk_pos[node_id] = pos

        map_args.append((clusters[c_id], cells, new_netlist, board, blk_pos))

    # multi-processing
    pool = Pool(4)
    results = pool.map(detailed_placement, map_args)

    pool.close()
    pool.join()

    for r in results:
        board_pos.update(r)

    color_index = "imop"

    scale = 30
    im, draw = draw_board(20, 20, scale)
    for blk_id in board_pos:
        pos = board_pos[blk_id]
        index = color_index.index(blk_id[0])
        color = color_palette[index]
        draw_cell(draw, pos, color, scale)

    for blk_id in board_pos:
        pos = board_pos[blk_id]
        place_on_board(board, blk_id, pos)

    # save the placement file
    placement_filename = netlist_filename.replace(".json", ".place")
    save_placement(board_pos, id_to_name, placement_filename)
    plt.imshow(im)
    plt.show()


if __name__ == "__main__":
    main()
