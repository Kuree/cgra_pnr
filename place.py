from __future__ import print_function, division

from util import reduce_cluster_graph, compute_centroids
from util import SetEncoder, choose_resource
import os
import pythunder
import json
import threading


def detailed_placement_thunder(args, context=None):
    blks = list(args["clusters"])
    cells = args["cells"]
    netlist = args["new_netlist"]
    blk_pos = args["blk_pos"]
    fold_reg = args["fold_reg"]
    seed = args["seed"]
    clb_type = args["clb_type"]
    fixed_pos = {}
    for blk_id in blk_pos:
        fixed_pos[blk_id] = list(blk_pos[blk_id])
    placer = pythunder.DetailedPlacer(blks, netlist, cells,
                                      fixed_pos, clb_type,
                                      fold_reg)
    placer.set_seed(seed)
    placer.anneal()
    placer.refine(1000, 0.01, False)
    placement = placer.realize()
    keys_to_remove = set()
    for blk_id in placement:
        if blk_id[0] == "x":
            keys_to_remove.add(blk_id)
    for blk_id in keys_to_remove:
        placement.pop(blk_id, None)
    if context is None:
        return placement
    else:
        return {'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': placement
                }


def estimate_placement_time(args):
    blks = list(args["clusters"])
    cells = args["cells"]
    netlist = args["new_netlist"]
    blk_pos = args["blk_pos"]
    fold_reg = args["fold_reg"]
    clb_type = args["clb_type"]
    fixed_pos = {}
    for blk_id in blk_pos:
        fixed_pos[blk_id] = list(blk_pos[blk_id])
    new_cells = {}
    for blk_type in cells:
        new_cells[blk_type] = list(cells[blk_type])
    placer = pythunder.DetailedPlacer(blks, netlist, new_cells,
                                      fixed_pos, clb_type,
                                      fold_reg)
    t = placer.estimate(10000)
    return t


def get_lambda_arn(map_args, aws_config):
    from six.moves import queue
    threads = []
    que = queue.Queue()
    for i in range(len(map_args)):
        t = threading.Thread(target=lambda q, arg, index: q.put(
            (index, estimate_placement_time(arg))), args=(que, map_args[i], i))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    estimates = [-1] * len(map_args)
    while not que.empty():
        index, estimate = que.get()
        estimates[index] = estimate

    for t in estimates:
        assert t != -1
    return choose_resource(estimates, aws_config)


def refine_global_thunder(layout, pre_placement, netlists, fixed_pos,
                          fold_reg):
    clb_type = layout.get_clb_type()
    available_pos = layout.produce_available_pos()
    global_refine = pythunder.DetailedPlacer(pre_placement,
                                             netlists,
                                             available_pos,
                                             fixed_pos,
                                             clb_type,
                                             fold_reg)

    global_refine.refine(int(100 * (len(pre_placement) ** 1.33)),
                         0.001, True)

    return global_refine.realize()


def place_on_board(board, blk_id, pos):
    x, y = pos
    board[y][x].append(blk_id)


def make_board(layout):
    width = layout.width()
    height = layout.height()
    board = [[[] for _ in range(width)] for _ in range(height)]
    return board


def main():
    # only the main thread needs it
    # this is to avoid loading unnecessary crop while calling from aws lambda
    from argparse import ArgumentParser
    from arch import parse_cgra, parse_fpga
    from arch.cgra import place_special_blocks, save_placement, prune_netlist
    from arch.cgra_packer import load_packed_file
    from arch.fpga import load_packed_fpga_netlist
    from arch import mock_board_meta
    from visualize import visualize_placement_cgra

    parser = ArgumentParser("CGRA Placer")
    parser.add_argument("-i", "--input", help="Packed netlist file, " +
                                              "e.g. harris.packed",
                        required=True, action="store", dest="packed_filename")
    parser.add_argument("-o", "--output", help="Placement result, " +
                                               "e.g. harris.place",
                        required=True, action="store",
                        dest="placement_filename")
    parser.add_argument("-c", "--cgra", help="CGRA architecture file",
                        action="store", dest="cgra_arch", default="")
    parser.add_argument("--no-reg-fold", help="If set, the placer will treat " +
                                              "registers as PE tiles",
                        action="store_true",
                        required=False, dest="no_reg_fold", default=False)
    parser.add_argument("--no-vis", help="If set, the placer won't show " +
                                         "visualization result for placement",
                        action="store_true",
                        required=False, dest="no_vis", default=False)
    parser.add_argument("-s", "--seed", help="Seed for placement. " +
                                             "default is 0", type=int,
                        default=0,
                        required=False, action="store", dest="seed")

    parser.add_argument("-a", "--aws", help="Serverless configuration for " +
                        "detailed placement. If set, will try to connect to "
                        "that arn",
                        dest="aws_config", type=str, required=False,
                        action="store", default="")
    parser.add_argument("-f", "--fpga", action="store", dest="fpga_arch",
                        default="", help="ISPD FPGA architecture file")
    parser.add_argument("-l", "--layout", action="store", dest="cgra_layout",
                        default="", help="CGRA layout file")
    parser.add_argument("--mock", action="store", dest="mock_size",
                        default=0, type=int, help="Mock CGRA board with "
                                                  "provided size")
    args = parser.parse_args()

    cgra_arch = args.cgra_arch
    fpga_arch = args.fpga_arch
    cgra_layout = args.cgra_layout
    mock_size = args.mock_size

    if sum([len(cgra_arch) != 0,
            len(fpga_arch) != 0,
            len(cgra_layout) != 0]) != 1 and \
            mock_size == 0:
        parser.error("Must provide wither --fpga, --cgra, or --layout")

    packed_filename = args.packed_filename
    placement_filename = args.placement_filename
    aws_config = args.aws_config
    fpga_place = len(fpga_arch) > 0

    seed = args.seed
    print("Using seed", seed, "for placement")

    vis_opt = not args.no_vis
    fold_reg = not args.no_reg_fold
    # FPGA params override
    if mock_size > 0:
        fold_reg = False
        board_meta = mock_board_meta(mock_size)
    elif fpga_place:
        fold_reg = False
        board_meta = parse_fpga(fpga_arch)
    else:
        if len(cgra_arch) > 0:
            board_meta = parse_cgra(cgra_arch)
        else:
            board_meta = {"cgra": pythunder.io.load_layout(cgra_layout)}
    # Common routine
    board_name, layout = board_meta.popitem()
    print("INFO: Placing for", board_name)
    board = make_board(layout)

    pythunder.io.dump_layout(layout, "cgra.layout")

    fixed_blk_pos = {}
    special_blocks = set()

    # FPGA
    if fpga_place:
        netlists, fixed_blk_pos, _ = load_packed_fpga_netlist(packed_filename)
        id_to_name = {}
        # place fixed IO locations
        for blk_id in fixed_blk_pos:
            pos = fixed_blk_pos[blk_id]
            place_on_board(board, blk_id, pos)

        folded_blocks = {}
        changed_pe = {}

    else:
        # CGRA
        raw_netlist, folded_blocks, id_to_name, changed_pe = \
            load_packed_file(packed_filename)
        netlists = prune_netlist(raw_netlist)
        for blk in id_to_name:
            if blk[0] == "i" or blk[0] == "I":
                special_blocks.add(blk)

        # place the spacial blocks first
        place_special_blocks(board, special_blocks, fixed_blk_pos, raw_netlist,
                             place_on_board,
                             layout)

    # common routine
    # produce layout structure
    centroids, cluster_cells, clusters = perform_global_placement(
        fixed_blk_pos, netlists, layout, seed=seed, vis=vis_opt)

    # placer with each cluster
    board_pos = perform_detailed_placement(centroids,
                                           cluster_cells, clusters,
                                           fixed_blk_pos, netlists,
                                           fold_reg, seed,
                                           layout,
                                           aws_config)
    # refinement
    board_pos = refine_global_thunder(layout, board_pos, netlists,
                                      fixed_blk_pos, fold_reg)

    for blk_id in board_pos:
        pos = board_pos[blk_id]
        place_on_board(board, blk_id, pos)

    # save the placement file
    save_placement(board_pos, id_to_name, folded_blocks, placement_filename)
    basename_file = os.path.basename(placement_filename)
    design_name, _ = os.path.splitext(basename_file)
    if vis_opt:
        visualize_placement_cgra(layout, board_pos, design_name, changed_pe)


def perform_global_placement(fixed_blk_pos, netlists,
                             layout, seed, vis=True, partition_threshold=10):
    from visualize import visualize_clustering_cgra
    # simple heuristics to calculate the clusters
    # if we have less than 10 blocks. no need to partition it
    blk_set = set()
    for net_id, blks in netlists.items():
        for blk in blks:
            if blk not in fixed_blk_pos:
                blk_set.add(blk)
    if len(blk_set) <= partition_threshold:
        clusters = {0: blk_set}
    else:
        clusters = pythunder.graph.partition_netlist(netlists)
        clusters = pythunder.util.filter_clusters(clusters, fixed_blk_pos)

    # prepare for the input
    new_clusters = {}
    for c_id in clusters:
        new_id = "x" + str(c_id)
        new_clusters[new_id] = set()
        for blk in clusters[c_id]:
            # make sure that fixed blocks are not in the clusters
            if blk not in fixed_blk_pos:
                new_clusters[new_id].add(blk)
    gp = pythunder.GlobalPlacer(new_clusters, netlists, fixed_blk_pos,
                                layout)
    gp.set_seed(seed)
    # compute the anneal parameter here
    total_blocks = layout.get_layer(layout.get_clb_type()).produce_available_pos()
    fill_ratio = min(0.99, len(blk_set) / len(total_blocks))
    base_factor = 1.0
    if fill_ratio > 0.8:
        base_factor = 1.2
    gp.anneal_param_factor = base_factor / (1 - fill_ratio)
    print("use anneal param factor:", gp.anneal_param_factor)
    gp.solve()
    gp.anneal()
    cluster_cells_ = gp.realize()

    cluster_cells = {}
    for c_id in cluster_cells_:
        cells = cluster_cells_[c_id]
        c_id = int(c_id[1:])
        cluster_cells[c_id] = cells
    clb_type = layout.get_clb_type()
    centroids = compute_centroids(cluster_cells, b_type=clb_type)

    if vis:
        visualize_clustering_cgra(layout, cluster_cells)
    assert (cluster_cells is not None and centroids is not None)
    return centroids, cluster_cells, clusters


def detailed_placement_thunder_wrapper(args):
    clusters = {}
    cells = {}
    netlists = {}
    fixed_blocks = {}
    clb_type = args[0]["clb_type"]
    fold_reg = args[0]["fold_reg"]
    seed = args[0]["seed"]
    for i in range(len(args)):
        c_id = "x" + str(i)
        arg = args[i]
        clusters[c_id] = arg["clusters"]
        cells[c_id] = arg["cells"]
        netlists[c_id] = arg["new_netlist"]
        fixed_blocks[c_id] = arg["blk_pos"]
    return pythunder.detailed_placement(clusters, cells, netlists, fixed_blocks,
                                        clb_type,
                                        fold_reg,
                                        seed)


def perform_detailed_placement(centroids, cluster_cells, clusters,
                               fixed_blk_pos, netlists,
                               fold_reg, seed, layout,
                               aws_config=""):
    from six.moves import queue
    import boto3
    board_pos = fixed_blk_pos.copy()
    map_args = []

    clb_type = layout.get_clb_type()

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
        args = {"clusters": clusters[c_id], "cells": cells,
                "new_netlist": new_netlist,
                "blk_pos": blk_pos, "fold_reg": fold_reg,
                "seed": seed, "clb_type": clb_type}
        map_args.append(args)
    if not aws_config:
        return detailed_placement_thunder_wrapper(map_args)
    else:
        # user need to specify a region in the environment
        client = boto3.client("lambda")
        import time
        threads = []
        lambda_arns = get_lambda_arn(map_args, aws_config)
        que = queue.Queue()
        lambda_res = {}
        start = time.time()
        for i in range(len(map_args)):
            t = threading.Thread(target=lambda q, arg, arn:
            q.put(client.invoke(
                **{"FunctionName": arn,
                   "InvocationType": "RequestResponse",
                   "Payload":
                       bytes(json.dumps(arg, cls=SetEncoder))})
                  ["Payload"].read()),
                                 args=(que, map_args[i], lambda_arns[i][1]))
            threads.append(t)
            lambda_res[i] = lambda_arns[i][0]
        # sort the threads so that the ones needs most resources runs first
        # this gives us some spaces for mis-calculated runtime approximation
        index_list = list(range(len(map_args)))
        index_list.sort(key=lambda x: lambda_res[x], reverse=True)
        # start
        for i in index_list:
            t = threads[i]
            t.start()
        # skip join, use blocking while loop to aggressively waiting threads
        # to finish
        job_count = 0
        # merge
        while job_count < len(map_args):
            if not que.empty():
                res = json.loads(que.get())
                r = res["body"]
                board_pos.update(r)
                job_count += 1
        end = time.time()
        print("Lambda takes", end - start, "seconds")
        return board_pos


if __name__ == "__main__":
    main()
