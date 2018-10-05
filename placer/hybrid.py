from __future__ import print_function
import random
import math
import numpy as np
import scipy.spatial


from .util import analyze_lanes, Box, collapse_netlist, compute_connections


class HypridPlacer:
    """Analytical placer with two stages"""
    def __init__(self, clusters, netlists, fixed_pos, board_meta,
                 fold_reg=True, seed=0):
        self.clusters = clusters
        self.fixed_pos = fixed_pos.copy()

        board_info = board_meta[-1]
        self.board_layout = board_meta[0]
        self.clb_type = board_info["clb_type"]
        self.clb_margin = board_info["margin"]
        self.height = board_info["height"]
        self.width = board_info["width"]

        self.board_type = board_info["arch_type"]

        if fold_reg:
            self.legal_ignore = {"r"}
        else:
            self.legal_ignore = set()
        self.fold_reg = fold_reg

        self.random = random.Random()
        self.random.seed(seed)

        self.block_lanes = analyze_lanes(self.clb_margin,
                                         self.board_layout)

        self.netlists, self.intra_cluster_count = \
            collapse_netlist(clusters, netlists, fixed_pos)

        self.cluster_ids = list(clusters.keys())
        self.cluster_ids.sort(key=lambda x: int(x[1:]))

        fixed_ids = list(fixed_pos.keys())
        fixed_ids.sort(key=lambda x: int(x[1:]))
        self.blocks = self.cluster_ids + fixed_ids

        self.cluster_connection, self.block_index =\
            compute_connections(self.blocks, self.netlists)

        self.overlap_spring = 100
        self.connection_spring = 1  # this is proportional to the distance
        self.iterations = 20

    def anneal(self):
        """Just to keep the interface but doesn't do anything """
        return

    def __init_placement(self):
        # randomly placed on the center
        # notice that it has lots of overlaps
        center_x = self.width // 2
        center_y = self.height // 2
        placement = {}
        for cluster_id in self.cluster_ids:
            cluster = self.clusters[cluster_id]
            box = Box()
            box.total_clb_size = len([c for c in cluster if c[0] ==
                                      self.clb_type])
            height = int(math.ceil(box.total_clb_size ** 2))
            x = self.random.randrange(-3, 3 + 1) + center_x
            y = self.random.randrange(-3, 3 + 1) + center_y - height // 2
            box.xmin = x
            box.ymin = y
            box.ymax = y + height
            self.__update_box(box)
            placement[cluster_id] = cluster_id
        return placement

    def realize(self):
        # first stage do a force solver with distance based.
        # then de-overlap and refine the blocks
        pass

    def __block_solve(self, init_placement):
        placement = init_placement.copy()
        fixed_boxes = {}
        # create box for fixed positions
        for blk_id in self.fixed_pos:
            box = Box()
            x, y = self.fixed_pos[blk_id]
            box.xmin = x
            box.xmax = x + 1
            box.ymin = y
            box.ymax = y + 1
            box.special_blocks = {blk_id[0]: 1}
            fixed_boxes[blk_id] = box
        placement.update(fixed_boxes)

        pos_matrix = np.zeros((len(self.blocks), 2))
        num_clusters = len(self.cluster_ids)

        for blk_id in placement:
            index = self.block_index[blk_id]
            box = placement[blk_id]
            x = (box.xmin + box.xmax) // 2
            y = (box.ymin + box.ymax) // 2
            pos_matrix[index] = (x, y)

        for it in range(self.iterations):
            dist = scipy.spatial.distance.cdist(pos_matrix, pos_matrix,
                                                metric="cityblock")
            cos_d = scipy.spatial.distance.cdist(pos_matrix, pos_matrix,
                                                 metric="cosine")

    def __update_box(self, box, compute_special=True):
        # notice that this one doesn't check the legality
        x = box.xmin
        height = box.ymax - box.ymin
        required_width = int(math.ceil(box.total_clb_size / height))
        width = 0
        current_x = x
        while width < required_width:
            current_x += 1
            if current_x >= len(self.block_lanes):
                width += 1
            elif self.block_lanes[current_x] == self.clb_type:
                width += 1
        box.xmax = current_x
        if compute_special:
            # compute how many special blocks the cluster needed
            cluster = self.clusters[box.c_id]
            special_blocks = {}
            for blk_id in cluster:
                blk_type = blk_id[0]
                if blk_type != self.clb_type:
                    if blk_type not in special_blocks:
                        special_blocks[blk_type] = 0
                    special_blocks[blk_type] += 1
            box.special_blocks = special_blocks
