from __future__ import print_function, division
import random
import math
import numpy as np
from .util import analyze_lanes, Box, collapse_netlist, compute_connections


class GlobalPlacer:
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
        self.cluster_ids.sort()

        fixed_ids = list(fixed_pos.keys())
        fixed_ids.sort(key=lambda x: int(x[1:]))
        self.blocks = self.cluster_ids + fixed_ids

        self.cluster_connection, self.block_index =\
            compute_connections(self.blocks, self.netlists)

        self.overlap_spring = 15.0 / (self.height * self.width)
        self.connection_spring = 1.0 / len(self.netlists)
        self.fixed_spring = self.connection_spring * 5
        # percentage of nets that have DSP connections
        self.dsp_ratio = 0.01
        self.dsp_spring = self.connection_spring / self.dsp_ratio

    def anneal(self):
        """Just to keep the interface but doesn't do anything """
        return

    def __init_placement(self):
        # randomly placed on the center
        # notice that it has lots of overlaps
        center_x = self.width // 2 + self.clb_margin
        center_y = self.height // 2 + self.clb_margin
        placement = {}
        for cluster_id in self.cluster_ids:
            cluster = self.clusters[cluster_id]
            box = Box()
            box.total_clb_size = len([c for c in cluster if c[0] ==
                                      self.clb_type])
            height = int(math.ceil(box.total_clb_size ** 0.5))
            x = (self.random.random() - 0.5) * 3 + center_x
            y = (self.random.random() - 0.5) * 3 + center_y - height // 2
            box.xmin = x
            box.ymin = y
            box.ymax = y + height
            box.xmax = x + height
            self.__compute_special_blocks(box)
            placement[cluster_id] = box
        return placement

    def place(self):
        # first stage do a force solver with distance based.
        # then de-overlap and refine the blocks
        init_placement = self.__init_placement()
        placement = self.__block_solve(init_placement)
        return placement

    def __block_solve(self, init_placement):
        placement = [Box() for _ in range(len(self.block_index))]
        for blk_id in init_placement:
            placement[self.block_index[blk_id]] = init_placement[blk_id]

        # create box for fixed positions
        for blk_id in self.fixed_pos:
            box = Box()
            x, y = self.fixed_pos[blk_id]
            box.xmin = x
            box.xmax = x + 1
            box.ymin = y
            box.ymax = y + 1
            box.special_blocks = {blk_id[0]: 1}
            index = self.block_index[blk_id]
            placement[index] = box

        # index DSPs
        dsp_loc = {}
        dsp_list = {}
        for blk_type in self.block_lanes:
            if blk_type in dsp_list or blk_type is None:
                continue
            index = []
            for i, b_t in enumerate(self.block_lanes):
                if b_t == blk_type:
                    index.append(i)
            index_array = np.array(index)
            dsp_list[blk_type] = index_array

        for blk_type in self.block_lanes:
            if blk_type in dsp_loc or blk_type is None:
                continue
            dsp_matrix = np.zeros((self.height, self.width), dtype=bool)
            for i in range(self.height):
                for j in range(self.width):
                    if self.board_layout[i][j] == blk_type:
                        dsp_matrix[i, j] = True
            dsp_loc[blk_type] = dsp_matrix

        pos_matrix = np.zeros((len(self.blocks), 2))
        num_clusters = len(self.cluster_ids)
        num_blocks = len(self.blocks)

        for index, box in enumerate(placement):
            x = (box.xmin + box.xmax) / 2
            y = (box.ymin + box.ymax) / 2
            pos_matrix[index] = (x, y)

        it = 0
        while True:
            net_force = np.zeros((num_blocks, num_blocks, 2), dtype=float)
            overlap_force = np.zeros((num_blocks, num_blocks, 2), dtype=float)
            dsp_force = np.zeros((num_blocks, 2), dtype=float)

            for i in range(num_clusters):
                p1 = pos_matrix[i]
                box1 = placement[i]
                for j in range(i + 1, num_blocks):
                    p2 = pos_matrix[j]
                    box2 = placement[j]
                    diff = p2 - p1
                    dist = np.linalg.norm(diff)
                    if p1[0] == p2[0] and p1[1] == p2[1]:
                        norm = np.array((self.random.random(),
                                         self.random.random())) / 2
                    else:
                        norm = diff / dist
                    if j < num_clusters:
                        f1 = norm * self.connection_spring * \
                            self.cluster_connection[i, j] * (dist ** 2)
                    else:
                        f1 = norm * self.fixed_spring * \
                             self.cluster_connection[i, j] * (dist ** 2)
                    net_force[(i, j)] = f1
                    net_force[(j, i)] = -f1

                    # compute overlap
                    # we need to revert the force direction
                    dx = min(box1.xmax, box2.xmax) - max(box1.xmin, box2.xmin)
                    dy = min(box1.ymax, box2.ymax) - max(box1.ymin, box2.ymin)
                    overlap = dy * dy if (dx > 0 and dy > 0) else 0
                    f2 = -norm * (overlap ** 2) * self.overlap_spring  # revert
                    overlap_force[i, j] = f2
                    overlap_force[j, i] = -f2

                # compute DSP forces
                for blk_type in box1.special_blocks:
                    if blk_type in self.legal_ignore:
                        continue
                    needed = box1.special_blocks[blk_type]
                    have = np.sum(dsp_loc[blk_type][int(box1.xmin):
                                                    int(box1.xmax),
                                  int(box1.ymin):int(box1.ymax)])
                    if have < needed:
                        # find the nearest dsp column
                        left = int(box1.xmin) - 1
                        while left >= self.clb_margin:
                            if self.block_lanes[left] == blk_type:
                                break
                            left -= 1
                        right = int(box1.xmax) + 1
                        while right <= self.width - self.clb_margin:
                            if self.block_lanes[right] == blk_type:
                                break
                            right += 1
                        if left >= self.clb_margin and \
                           right <= self.width - self.clb_margin:
                            if box1.xmin - left < right - box1.xmax:
                                dist = box1.xmin - left
                                direction = np.array([-1, 0])
                            else:
                                dist = right - box1.xmax
                                direction = np.array([1, 0])
                        else:
                            dist = 0
                            direction = np.array([0, 0])
                        dsp_force[i] = direction * (dist ** 2) * \
                            (needed - have) * self.dsp_spring

            # net and overlap have different schedule
            total_force = net_force / ((it + 1) ** 0.8) + \
                overlap_force / ((it + 0.5) ** 0.4)
            total_force = total_force.sum(axis=1)
            # DSP have different schedule
            total_force += dsp_force / ((it + 1) ** 0.5)
            displacement = np.round(total_force)

            # if more than 80% of the stuff are zero
            # then we quit since it reaches equilibrium.
            total_disp = np.sum(np.abs(displacement))
            if total_disp < 0.9 * num_clusters / 2:
                break

            for i in range(num_clusters):
                box = placement[i]
                dx, dy = displacement[i]
                new_x = box.xmin + dx
                new_y = box.ymin + dy
                height = box.ymax - box.ymin
                if new_x < self.clb_margin:
                    new_x = self.clb_margin
                if new_y < self.clb_margin:
                    new_y = self.clb_margin
                new_x = int(new_x)
                new_y = int(new_y)
                box.xmin = new_x
                box.ymin = new_y
                box.ymax = new_y + height
                self.__update_box(box, False)
                if box.xmax > self.width - self.clb_margin:
                    box.xmax = self.width
                    box.xmin = int(self.width - self.clb_margin - height)
                    while box.xmax > self.width - self.clb_margin:
                        box.xmin -= 1
                        self.__update_box(box, False)
                if box.ymax > self.height - self.clb_margin:
                    # fix box again
                    box.ymax = self.height - self.clb_margin
                    box.ymin = box.ymax - height

                # update position matrix
                x = (box.xmin + box.xmax) / 2
                y = (box.ymin + box.ymax) / 2
                pos_matrix[i] = (x, y)
            it += 1
        # change it back to the placement blk_id -> box
        result_placement = {}
        for blk_id in init_placement:
            result_placement[blk_id] = placement[self.block_index[blk_id]]
        return result_placement

    def __compute_special_blocks(self, box):
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
            self.__compute_special_blocks(box)
