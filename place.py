from __future__ import print_function
from util import reduce_cluster_graph, compute_centroid, parse_args
from parser import parse_emb
from sa import SAClusterPlacer, SADetailedPlacer, DeblockAnnealer
from sa import ClusterException, SAMacroPlacer
from arch import make_board, parse_cgra, parse_vpr, generate_place_on_board
from arch import generate_is_cell_legal
import numpy as np
import os
import sys
import matplotlib.pyplot as plt
from visualize import draw_board, draw_cell, color_palette
from sklearn.cluster import KMeans
import random
from multiprocessing import Pool


def detailed_placement(args):
    clusters, cells, netlist, board, blk_pos = args
    detailed = SADetailedPlacer(clusters, cells, netlist, board, blk_pos,
                                multi_thread=True)
    #detailed.steps = 10
    detailed.anneal()
    return detailed.state


def deblock_placement(args):
    clusters, cells, netlist, board, blk_pos = args
    deblock = DeblockAnnealer(clusters, cells, netlist, blk_pos,
                              multi_thread=True)
    #deblock.steps = 100
    deblock.anneal()
    return deblock.get_block_pos()


def macro_placement(board, board_pos, fixed_blk_pos, netlists, is_legal,
                    board_meta):
    layout_board = board_meta[0]
    available_pos = set()
    for y in range(len(layout_board)):
        for x in range(len(layout_board[0])):
            if layout_board[y][x] == "m" or layout_board == "u":
                available_pos.add((x, y))
    current_placement = {}
    for blk_id in fixed_blk_pos:
        if blk_id[0] == "m" or blk_id[0] == "u":
            current_placement[blk_id] = fixed_blk_pos[blk_id]

    macro = SAMacroPlacer(available_pos, netlists, board, board_pos,
                          current_placement, is_legal)
    macro.steps = 30
    macro.anneal()

    return macro.state


def main():
    options, argv = parse_args(sys.argv)
    if len(argv) < 4:
        print("Usage:", sys.argv[0], "[options] <arch_file> <packed_list>",
              "<embedding>", file=sys.stderr)
        print("[options]: -no-vis -cgra -fpga", file=sys.stderr)
        exit(1)
    # force some internal library random sate
    random.seed(0)
    np.random.seed(0)

    arch_filename = argv[1]
    packed_filename = argv[2]
    netlist_embedding = argv[3]

    vis_opt = "no-vis" not in options

    _, ext = os.path.splitext(packed_filename)
    arch_type = ""
    if "cgra" in options:
        arch_type = "cgra"
    elif "fpga" in options:
        arch_type = "fpga"
    if len(arch_type) == 0:
        print("Please indicate either -fpga or -cgra", packed_filename,
              file=sys.stderr)
        exit(1)

    if arch_type == "fpga":
        board_meta = parse_vpr(arch_filename)
    else:
        board_meta = parse_cgra(arch_filename)
    board_name, board_meta = board_meta.popitem()
    print("INFO: Placing for", board_name)
    num_dim, raw_emb = parse_emb(netlist_embedding)
    board = make_board(board_meta)
    place_on_board = generate_place_on_board(board_meta)
    is_cell_legal = generate_is_cell_legal(board_meta)

    fixed_blk_pos = {}
    emb = {}
    # import board specific functions as well as macro placement
    if arch_type == "fpga":
        from arch.fpga import parse_placement, parse_packed, save_placement
        reference_placement = packed_filename.replace(".packed", ".place")
        if not os.path.isfile(reference_placement):
            print("Cannot find reference placement file",
                  reference_placement, file=sys.stderr)
            exit(1)
        _, reference_blk_pos = parse_placement(reference_placement)
        netlists, _ = parse_packed(packed_filename)

        for blk_id in raw_emb:
            if blk_id[0] != "c":
                b_id = int(blk_id[1:])
                fixed_blk_pos[blk_id] = reference_blk_pos[b_id]
            else:
                emb[blk_id] = raw_emb[blk_id]
    else:
        from arch.cgra import place_special_blocks, save_placement, \
            prune_netlist
        from arch.cgra_packer import load_packed_file
        raw_netlist, folded_blocks, id_to_name = \
            load_packed_file(packed_filename)
        netlists = prune_netlist(raw_netlist)
        special_blocks = set()
        for blk_id in raw_emb:
            if blk_id[0] != "p" and blk_id[0] != "r":
                special_blocks.add(blk_id)
            else:
                emb[blk_id] = raw_emb[blk_id]
        # place the spacial blocks first
        place_special_blocks(board, special_blocks, fixed_blk_pos, raw_netlist,
                             place_on_board)

    data_x = np.zeros((len(emb), num_dim))
    blks = list(emb.keys())
    for i in range(len(blks)):
        data_x[i] = emb[blks[i]]

    centroids, cluster_cells, clusters = perform_global_placement(
        blks, data_x, emb, fixed_blk_pos, netlists, board, is_cell_legal,
        board_meta[-1])

    # anneal with each cluster
    board_pos = perform_detailed_placement(board, centroids,
                                           cluster_cells, clusters,
                                           fixed_blk_pos, netlists)

    # do a macro placement
    #macro_result = macro_placement(board, board_pos, fixed_blk_pos, netlists,
    #                               is_cell_legal, board_meta)
    #board_pos.update(macro_result)

    # only use deblock when we have lots of clusters
    if len(clusters) > 2:
        board_pos = perform_deblock_placement(board, board_pos, fixed_blk_pos,
                                              netlists)

    for blk_id in board_pos:
        pos = board_pos[blk_id]
        place_on_board(board, blk_id, pos)

    # save the placement file
    if arch_type == "fpga":
        new_placement_filename = os.path.basename(reference_placement)
        save_placement(reference_placement, new_placement_filename, board,
                       board_pos)
        if vis_opt:
            visualize_placement_fpga(board_pos, clusters)
    else:
        placement_filename = packed_filename.replace(".packed", ".place")
        save_placement(board_pos, id_to_name, folded_blocks, placement_filename)
        basename_file = os.path.basename(placement_filename)
        design_name, _ = os.path.splitext(basename_file)
        if vis_opt:
            visualize_placement_cgra(board_pos, design_name)


def visualize_placement_fpga(board_pos, clusters):
    # draw the board
    im, draw = draw_board()
    for cluster_id in clusters:
        cells = clusters[cluster_id]
        for blk_id in cells:
            pos = board_pos[blk_id]
            color = color_palette[cluster_id]
            draw_cell(draw, pos, color)
    plt.imshow(im)
    plt.show()


def visualize_placement_cgra(board_pos, design_name):
    color_index = "imopr"
    scale = 30
    im, draw = draw_board(20, 20, scale)
    for blk_id in board_pos:
        pos = board_pos[blk_id]
        index = color_index.index(blk_id[0])
        color = color_palette[index]
        draw_cell(draw, pos, color, scale)
    plt.imshow(im)
    plt.show()

    file_dir = os.path.dirname(os.path.realpath(__file__))
    output_png = design_name + "_place.png"
    output_path = os.path.join(file_dir, "figures", output_png)
    im.save(output_path)
    print("Image saved to", output_path)


def perform_deblock_placement(board, board_pos, fixed_blk_pos, netlists):
    # apply deblock "filter" to further improve the quality
    num_x = 2
    num_y = 2  # these values are determined by the board size
    box_x = len(board[0]) // num_x
    box_y = len(board) // num_y
    boxes = []
    for j in range(num_y):
        pos_x = 0
        pos_y = box_y * j
        for i in range(num_x):
            corner_x = pos_x + box_x
            corner_y = pos_y + box_y
            box = set()
            # avoid over the board
            corner_x = min(corner_x, len(board[0]))
            corner_y = min(corner_y, len(board))
            for xx in range(pos_x, corner_x):
                for yy in range(pos_y, corner_y):
                    box.add((xx, yy))
            boxes.append(box)
            pos_x += box_x
    deblock_args = []
    assigned_boxes = {}
    box_centroids = {}
    for index, box in enumerate(boxes):
        # box is available
        assigned = {}
        for blk_id in board_pos:
            pos = board_pos[blk_id]
            if pos in box:
                assigned[blk_id] = pos
        if len(assigned) == 0:
            continue  # they are empty so don't need them any more
        assigned_boxes[index] = assigned
        box_centroids[index] = compute_centroid(assigned)
    # boxes is the new clusters here
    for c_id in range(len(boxes)):
        if c_id not in box_centroids:
            continue
        blk_pos = fixed_blk_pos.copy()
        for i in range(len(boxes)):
            if i == c_id or i not in box_centroids:
                continue
            node_id = "x" + str(i)
            pos = box_centroids[i]
            blk_pos[node_id] = pos
        new_netlist = reduce_cluster_graph(netlists, assigned_boxes,
                                           fixed_blk_pos, c_id)
        deblock_args.append((assigned_boxes[c_id], boxes[c_id], new_netlist,
                             board, blk_pos))
    pool = Pool(4)
    results = pool.map(deblock_placement, deblock_args)
    pool.close()
    pool.join()
    board_pos = fixed_blk_pos.copy()
    for r in results:
        board_pos.update(r)
    return board_pos


def perform_global_placement(blks, data_x, emb, fixed_blk_pos, netlists, board,
                             is_cell_legal, board_info):
    # simple heuristics to calculate the clusters
    if board_info["arch_type"] == "cgra":
        num_clusters = int(np.ceil(len(emb) / 40)) + 1
    else:
        num_clusters = int(np.ceil(len(emb) / 120)) + 1
    factor = 6
    while True:     # this just enforce we can actually place it
        if num_clusters == 0:
            raise Exception("Cannot fit into the board")
        print("Trying: num of clusters", num_clusters)
        kmeans = KMeans(n_clusters=num_clusters, random_state=0).fit(data_x)
        cluster_ids = kmeans.labels_
        clusters = {}
        for i in range(len(blks)):
            cid = cluster_ids[i]
            if cid not in clusters:
                clusters[cid] = {blks[i]}
            else:
                clusters[cid].add(blks[i])
        cluster_sizes = [len(clusters[s]) for s in clusters]
        print("cluster average:", np.average(cluster_sizes), "std:",
              np.std(cluster_sizes), "total:", np.sum(cluster_sizes))
        try:
            cluster_placer = SAClusterPlacer(clusters, netlists, board,
                                             fixed_blk_pos, place_factor=factor,
                                             is_cell_legal=is_cell_legal,
                                             board_info=board_info)
            break
        except ClusterException as ex:
            num_clusters -= 1
            factor = 4

    #cluster_placer.steps = 10
    cluster_placer.anneal()
    cluster_cells, centroids = cluster_placer.squeeze()
    return centroids, cluster_cells, clusters


def perform_detailed_placement(board, centroids, cluster_cells, clusters,
                               fixed_blk_pos, netlists):
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
    pool = Pool(4)
    results = pool.map(detailed_placement, map_args)
    pool.close()
    pool.join()
    for r in results:
        board_pos.update(r)
    return board_pos


if __name__ == "__main__":
    main()
