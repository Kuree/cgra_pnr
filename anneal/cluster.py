from __future__ import division, print_function
import random
import math
import numpy as np

from anneal import Annealer
from .util import compute_centroids, collapse_netlist,\
    ClusterException, compute_hpwl, manhattan_distance


class Box:
    xmin = 10000
    xmax = -1
    ymin = 10000
    ymax = -1

    total_clb_size = 0
    c_id = 0

    special_blocks = {}

    @staticmethod
    def copy_box(box):
        new_box = Box()
        new_box.xmin = box.xmin
        new_box.ymin = box.ymin
        new_box.xmax = box.xmax
        new_box.ymax = box.ymax

        new_box.total_clb_size = box.total_clb_size
        new_box.c_id = box.c_id
        # no need to copy since this will never change
        new_box.special_blocks = box.special_blocks

        return new_box


class SAClusterPlacer(Annealer):
    def __init__(self, clusters, netlists, board, fixed_pos, board_meta,
                 fold_reg=True, seed=0, debug=False):
        """Notice that each clusters has to be a condensed node in a networkx graph
        whose edge denotes how many intra-cluster connections.
        """
        self.clusters = clusters
        self.board = board
        self.fixed_pos = fixed_pos.copy()

        board_info = board_meta[-1]
        self.board_layout = board_meta[0]
        self.clb_type = board_info["clb_type"]
        self.clb_margin = board_info["margin"]
        self.height = board_info["height"]
        self.width = board_info["width"]

        self.debug = debug

        self.overlap_factor = 1.0 / 8
        # energy control
        self.overlap_energy = 10
        self.legal_penalty = {"m": 30, "d": 100}

        rand = random.Random()
        rand.seed(seed)

        self.fold_reg = fold_reg

        self.center_of_board = (len(self.board[0]) // 2, len(self.board) // 2)
        self.block_lanes = self.analyze_lanes(self.board_layout)
        self.boxes = {}
        for cluster_id in clusters:
            self.boxes[cluster_id] = Box()

        placement = self.__init_placement(rand)
        # we don't want to recompute this, if init placement fails
        self.netlists, self.intra_cluster_count = \
            collapse_netlist(clusters, netlists, fixed_pos)

        energy = self.__init_energy(placement)
        state = {"placement": placement, "energy": energy}
        print("Initial Energy", energy)

        Annealer.__init__(self, initial_state=state, rand=rand)

        self.changes = 0
        self.has_changed = False

        # speed up move
        self.cluster_boxes = []
        for c_id in placement:
            self.cluster_boxes.append(placement[c_id])
        self.cluster_boxes.sort(key=lambda x: x.c_id)

        self.cluster_index = self.__build_box_netlist_index()
        self.moves = set()

        # some scheduling stuff?
        # self.Tmax = 10
        self.steps *= 30

    def __build_box_netlist_index(self):
        index = {}
        for net_id in self.netlists:
            for cluster_id in self.netlists[net_id]:
                c_id = int(cluster_id[1:])
                if c_id not in index:
                    index[c_id] = set()
                index[c_id].add(net_id)
        return index

    @staticmethod
    def analyze_lanes(board):
        height = len(board)
        width = len(board[0])
        lane_type = [None for _ in range(width)]
        for x in range(width):
            for y in range(height):
                blk_type = board[y][x]
                if blk_type is None:
                    continue
                if lane_type[x] is None:
                    lane_type[x] = blk_type
                else:
                    # for CGRA
                    if lane_type[x] != "i":
                        assert lane_type[x] == blk_type
        return lane_type

    @staticmethod
    def __compute_overlap(a, b):
        dx = min(a.xmax, b.xmax) - max(a.xmin, b.xmin)
        dy = min(a.ymax, b.ymax) - max(a.ymin, b.ymin)
        if (dx >= 0) and (dy >= 0):
            return dx * dy
        else:
            return 0

    def __is_legal(self, box, state, ignore_c_id=None):
        # check two things
        # first, it's within the boundaries
        if box.xmin < self.clb_margin:
            return False
        if box.ymin < self.clb_margin:
            return False
        if box.xmax >= self.width - self.clb_margin:
            return False
        if box.ymax >= self.height - self.clb_margin:
            return False

        # second, overlapping area is under threshold
        total_overlap = 0
        for c_id in state:
            if c_id == box.c_id or c_id == ignore_c_id:
                continue
            total_overlap += self.__compute_overlap(box, state[c_id])
        return float(total_overlap) / box.total_clb_size < self.overlap_factor

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

    def __init_placement(self, rand):
        state = {}
        initial_x = self.clb_margin
        x, y = initial_x, self.clb_margin
        rows = []
        current_rows = []
        col = 0
        for cluster_id in self.clusters:
            box = self.boxes[cluster_id]
            cluster = self.clusters[cluster_id]
            box.total_clb_size = len([x for x in cluster if x[0] ==
                                      self.clb_type])
            height = int(math.ceil(box.total_clb_size ** 0.5))
            # put it on the board. notice that most of the blocks will span
            # the complex lanes. hence we need to be extra careful

            # aggressively packed them into the board
            # NOTE some of the info here are board specific
            # this avoids infinite loop, as well as allow searching for the
            # entire board
            visited = set()
            while True:
                if x >= self.width:
                    x = initial_x
                    rows = current_rows
                    current_rows = []
                    col = 0
                if len(rows) > 0:
                    if col < len(rows):
                        y = rows[col]
                    else:
                        y = rows[-1]
                else:
                    y = self.clb_margin

                pos = (x, y)
                if pos in visited:
                    raise ClusterException(cluster_id)
                else:
                    visited.add(pos)
                box.xmin = x
                box.ymin = y
                box.ymax = y + height
                box.c_id = cluster_id
                self.__update_box(box)
                if self.__is_legal(box, state):
                    state[cluster_id] = box
                    x += rand.randrange(height, height + 3)
                    current_rows.append(height + y)
                    col += 1
                    break
                x += 1
        return state

    @staticmethod
    def compute_center(placement):
        result = {}
        for cluster_id in placement:
            box = placement[cluster_id]
            x = (box.xmax + box.xmin) / 2.0
            y = (box.ymax + box.ymin) / 2.0
            result[cluster_id] = (x, y)
        return result

    def move(self):
        self.moves = set()
        placement = self.state["placement"]

        if self.debug and self.has_changed:
            reference_energy = self.__init_energy(placement)
            assert reference_energy == self.state["energy"]

        # we have three options here
        # first, move
        # second, swap
        # third, change shape
        box = self.random.sample(self.cluster_boxes, 1)[0]
        dx = self.random.randrange(-3, 3 + 1)
        dy = self.random.randrange(-3, 3 + 1)
        new_box = Box()
        new_box.xmin = box.xmin + dx
        new_box.ymin = box.ymin + dy
        new_box.ymax = box.ymax + dy
        new_box.total_clb_size = box.total_clb_size
        new_box.c_id = box.c_id
        self.__update_box(new_box, compute_special=False)
        # to see if it's legal
        if self.__is_legal(new_box, placement):
            self.moves.add(new_box)
            return
        box1, box2 = self.random.sample(self.cluster_boxes, 2)
        # swap their location
        new_box1 = Box.copy_box(box1)
        new_box2 = Box.copy_box(box2)

        new_box1.xmin = box2.xmin
        new_box1.ymin = box2.ymin
        # compute the new end y
        new_box1.ymax = box2.ymin + (box1.ymax - box1.ymin)

        new_box2.xmin = box1.xmin
        new_box2.ymin = box1.ymin
        # compute the new end y
        new_box2.ymax = box1.ymin + (box2.ymax - box2.ymin)
        # recompute the x
        self.__update_box(new_box1, compute_special=False)
        self.__update_box(new_box2, compute_special=False)
        if self.__is_legal(new_box1, placement, box2.c_id) and \
           self.__is_legal(new_box2, placement, box1.c_id):
            self.moves.add(new_box1)
            self.moves.add(new_box2)
            return
        # this is to reduce the penalty of overlapping
        box = self.random.sample(self.cluster_boxes, 1)[0]
        old_height = box.xmax - box.xmin
        new_height = old_height + self.random.randrange(-2, 2 + 1)
        new_box = Box.copy_box(box)
        new_box.ymax = new_box.ymin + new_height
        self.__update_box(new_box, compute_special=False)
        if self.__is_legal(new_box, placement):
            self.moves.add(new_box)

    def __compute_special_blocks(self, box):
        result = {}
        for blk_type in box.special_blocks:
            result[blk_type] = 0
            xmin = box.xmin
            xmax = box.xmax
            # lanes to compute
            lanes = set()
            for x in range(xmin, xmax + 1):
                if self.block_lanes[x] == blk_type:
                    lanes.add(x)
            # compute how many blocks are there
            for x in lanes:
                for y in range(box.ymin, box.ymax + 1):
                    if self.board_layout[y][x] == blk_type:
                        result[blk_type] += 1
        return result

    def __init_energy(self, placement):
        blk_pos = self.fixed_pos.copy()

        centers = self.compute_center(placement)
        for node_id in centers:
            c_id = "x" + str(node_id)
            blk_pos[c_id] = centers[node_id]
        hpwl = compute_hpwl(self.netlists, blk_pos)

        # add overlap
        overlap_area = self.__compute_total_overlap(placement)

        overlap_energy = overlap_area * self.overlap_energy
        hpwl += overlap_energy

        # add legalize energy
        legalize_energy = self.__compute_legal_energy(placement)
        hpwl += legalize_energy

        return hpwl

    def __compute_total_overlap(self, placement):
        overlap_area = 0
        for c_id in placement:
            box1 = placement[c_id]
            for c_id_next in placement:
                if c_id == c_id_next:
                    continue
                box2 = placement[c_id_next]
                overlap_area += self.__compute_overlap(box1, box2)
        return overlap_area

    def __compute_legal_energy(self, placement):
        legalize_energy = 0
        for c_id in placement:
            box = placement[c_id]
            blk_count = self.__compute_special_blocks(box)
            for blk_type in blk_count:
                remaining = blk_count[blk_type] - box.special_blocks[blk_type]
                if remaining < 0:
                    legalize_energy += abs(remaining) * \
                                       self.legal_penalty[blk_type]
        return legalize_energy

    def energy(self):
        """we use HPWL as the cost function"""
        if len(self.moves) == 0:
            return self.state["energy"]
        placement = self.state["placement"]
        energy = self.state["energy"]
        changed_nets = {}
        changed_boxes = {}
        for box in self.moves:
            changed_boxes[box.c_id] = placement[box.c_id]

        # first, compute the new HWPL
        changed_net_id = set()
        for new_box in self.moves:
            c_id = new_box.c_id
            changed_net_id.update(self.cluster_index[c_id])

        for net_id in changed_net_id:
            changed_nets[net_id] = self.netlists[net_id]

        blk_pos = self.fixed_pos.copy()
        centers = self.compute_center(placement)
        for node_id in centers:
            c_id = "x" + str(node_id)
            blk_pos[c_id] = centers[node_id]
        old_hpwl = compute_hpwl(changed_nets, blk_pos)

        if len(self.moves) == 1:
            old_overlap = 0
            for c_id in changed_boxes:
                box1 = changed_boxes[c_id]
                for c_id_next in placement:
                    if c_id == c_id_next:
                        continue
                    box2 = placement[c_id_next]
                    old_overlap += self.__compute_overlap(box1, box2)
            for c_id in placement:
                box1 = placement[c_id]
                for next_c_id in changed_boxes:
                    if c_id == next_c_id:
                        continue
                    box2 = changed_boxes[next_c_id]
                    old_overlap += self.__compute_overlap(box1, box2)
        else:
            assert len(self.moves) == 2
            old_overlap = self.__compute_total_overlap(placement)

        old_legalize_energy = self.__compute_legal_energy(changed_boxes)

        # compute the new energy
        # some implementation details:
        # 1. we temporarily override the placement and then restore it
        # 2. only compute the old/new energy for changed boxes

        new_placement = {}
        for box in self.moves:
            placement[box.c_id] = box
            new_placement[box.c_id] = box

        centers = self.compute_center(new_placement)
        for box in self.moves:
            node_id = box.c_id
            c_id = "x" + str(node_id)
            blk_pos[c_id] = centers[node_id]
        new_hpwl = compute_hpwl(changed_nets, blk_pos)
        # new_hpwl = compute_hpwl(self.netlists, blk_pos)

        if len(self.moves) == 1:
            new_overlap = 0
            for box1 in self.moves:
                c_id = box1.c_id
                for c_id_next in placement:
                    if c_id == c_id_next:
                        continue
                    box2 = placement[c_id_next]
                    new_overlap += self.__compute_overlap(box1, box2)
            for c_id in placement:
                box1 = placement[c_id]
                for box2 in self.moves:
                    if c_id == box2.c_id:
                        continue
                    new_overlap += self.__compute_overlap(box1, box2)
        else:
            new_overlap = self.__compute_total_overlap(placement)

        new_legalize_energy = 0
        for box in self.moves:
            blk_count = self.__compute_special_blocks(box)
            for blk_type in blk_count:
                remaining = blk_count[blk_type] - box.special_blocks[blk_type]
                if remaining < 0:
                    new_legalize_energy += abs(remaining) * \
                                           self.legal_penalty[blk_type]
        # new_legalize_energy = self.__compute_legal_energy(placement)
        # restore
        for c_id in changed_boxes:
            placement[c_id] = changed_boxes[c_id]

        hpwl_diff = new_hpwl - old_hpwl
        energy += hpwl_diff
        energy += (new_overlap - old_overlap) * self.overlap_energy
        energy += new_legalize_energy - old_legalize_energy

        return energy

    def commit_changes(self):
        for box in self.moves:
            self.state["placement"][box.c_id] = box
        if len(self.moves) > 0:
            self.changes += 1
            self.has_changed = True
        else:
            self.has_changed = False
        self.moves = set()

    def __is_cell_legal(self, pos, blk_type):
        x, y = pos
        if x < self.clb_margin or y < self.clb_margin:
            return False
        if x > self.width - self.clb_margin or \
           y > self.height - self.clb_margin:
            return False
        return self.board_layout[y][x] == blk_type

    def __get_exterior_set(self, cluster_id, current_cells, board,
                           max_dist=4, search_all=False):
        """board is a boolean map showing everything been taken, which doesn't
           care about overlap
        """
        # put it on the actual board so that we can do a brute-force search
        # so we need to offset with pos
        box = self.state["placement"][cluster_id]

        result = set()
        if search_all:
            x_min, x_max = self.clb_margin, len(board[0]) - self.clb_margin
            y_min, y_max = self.clb_margin, len(board) - self.clb_margin
        else:
            x_min, x_max = box.xmin - 1, box.xmax + 1
            y_min, y_max = box.ymin - 1, box.ymax + 1
        for y in range(y_min, y_max + 1):
            for x in range(x_min, x_max + 1):
                if (x, y) not in current_cells:
                    # make sure it's its own exterior
                    continue
                p = None
                # allow two manhattan distance jump
                # TODO: optimize this
                for i in range(-max_dist - 1, max_dist + 1):
                    for j in range(-max_dist - 1, max_dist + 1):
                        if abs(i) + abs(j) > max_dist:
                            continue
                        if not self.__is_cell_legal((x + j, y + i),
                                                    self.clb_type):
                            continue
                        if (not board[y + i][x + j]) and board[y][x]:
                            p = (x + j, y + i)
                        if (p is not None) and \
                                self.__is_cell_legal(p, self.clb_type):
                            result.add(p)
        for p in result:
            if board[p[1]][p[0]]:
                raise Exception("unknown error" + str(p))
        return result

    def __get_bboard(self, cluster_cells, check=True):
        bboard = np.zeros((self.height, self.width), dtype=np.bool)
        for cluster_id in cluster_cells:
            for blk_type in cluster_cells[cluster_id]:
                for x, y in cluster_cells[cluster_id][blk_type]:
                    if check:
                        assert(not bboard[y][x])
                    bboard[y][x] = True
        return bboard

    @staticmethod
    def __compute_overlap_cells(a, b):
        dx = min(a.xmax, b.xmax) - max(a.xmin, b.xmin)
        dy = min(a.ymax, b.ymax) - max(a.ymin, b.ymin)
        if (dx >= 0) and (dy >= 0):
            # brute force compute the overlaps
            a_pos, b_pos = set(), set()
            for y in range(a.ymin, a.ymax + 1):
                for x in range(a.xmin, a.xmax + 1):
                    a_pos.add((x, y))
            for y in range(b.ymin, b.ymax + 1):
                for x in range(b.xmin, b.xmax + 1):
                    b_pos.add((x, y))
            result = a_pos.intersection(b_pos)
            return result
        else:
            return set()

    def realize(self):
        # the idea is to pull every cell positions to the center of the board
        used_special_blocks_pos = set()
        cluster_cells = {}
        placement = self.state["placement"]
        # first assign special blocks
        for c_id in self.clusters:
            cluster = self.clusters[c_id]
            box = placement[c_id]
            cluster_special_blocks = \
                self.assign_special_blocks(cluster, box,
                                           used_special_blocks_pos)
            cluster_cells[c_id] = cluster_special_blocks

        overlaps = {}
        bboard = self.__get_bboard(cluster_cells, False)
        for cluster_id1 in cluster_cells:
            box1 = placement[cluster_id1]
            overlaps[cluster_id1] = set()
            for cluster_id2 in cluster_cells:
                if cluster_id1 == cluster_id2:
                    continue
                box2 = placement[cluster_id2]
                overlaps[cluster_id1].update(self.__compute_overlap_cells(box1,
                                                                          box2))

        # resolve overlapping from the most overlapped region
        cluster_ids = list(overlaps.keys())
        cluster_ids.sort(key=lambda entry: len(overlaps[entry]) /
                         float(placement[entry].total_clb_size),
                         reverse=True)

        for c_id in cluster_ids:
            # assign non-overlap cells
            box = placement[c_id]
            cluster_overlap_cells = overlaps[c_id]
            cluster_cells[c_id][self.clb_type] = set()
            for y in range(box.ymin, box.ymax + 1):
                for x in range(box.xmin, box.xmax + 1):
                    pos = (x, y)
                    if pos in cluster_overlap_cells:
                        continue
                    cluster_cells[c_id][self.clb_type].add(pos)
            self.de_overlap(cluster_cells[c_id][self.clb_type],
                            bboard, c_id,
                            cluster_overlap_cells)

        # return centroids as well
        centroids = compute_centroids(cluster_cells, b_type=self.clb_type)

        return cluster_cells, centroids

    def assign_special_blocks(self, cluster, box, used_spots):
        special_blks = {}
        cells = {}
        for blk_id in cluster:
            blk_type = blk_id[0]
            if blk_type != self.clb_type and blk_type != "r" and \
                    blk_type != "i":
                if blk_type not in special_blks:
                    special_blks[blk_type] = 0
                special_blks[blk_type] += 1

        pos_x, pos_y = box.xmin, box.ymin
        width, height = box.xmax - box.xmin, box.ymax - box.ymin
        centroid = pos_x + width / 2.0, pos_y + height / 2.0
        for x in range(pos_x, pos_x + width):
            for y in range(pos_y, pos_y + width):
                blk_type = self.board_layout[y][x]
                pos = (x, y)
                if blk_type in special_blks and pos not in used_spots:
                    # we found one
                    if blk_type not in cells:
                        cells[blk_type] = set()
                    cells[blk_type].add(pos)
                    used_spots.add(pos)
                    if special_blks[blk_type] > 0:
                        special_blks[blk_type] -= 1

        # here is the difficult part. if we still have blocks left to assign,
        # we need to do an brute force search
        available_pos = {}
        for blk_type in special_blks:
            available_pos[blk_type] = []
        for y in range(len(self.board_layout)):
            for x in range(len(self.board_layout[y])):
                pos = (x, y)
                blk_type = self.board_layout[y][x]
                if pos not in used_spots and blk_type in special_blks:
                    available_pos[blk_type].append(pos)
        for blk_type in special_blks:
            num_blocks = special_blks[blk_type]
            pos_list = available_pos[blk_type]
            if len(pos_list) < num_blocks:
                raise Exception("Not enough blocks left for type: " + blk_type)
            pos_list.sort(key=lambda p: manhattan_distance(p, centroid))
            for i in range(num_blocks):
                if blk_type not in cells:
                    cells[blk_type] = set()
                cells[blk_type].add(pos_list[i])
                used_spots.add(pos_list[i])

        return cells

    def de_overlap(self, current_cell, bboard, cluster_id, overlap_set):
        effort_count = 0
        old_overlap_set = len(overlap_set)
        needed = len([x for x in self.clusters[cluster_id]
                      if x[0] == self.clb_type])
        cells_have = 0
        for x, y in current_cell:
            if self.board_layout[y][x] == self.clb_type:
                cells_have += 1
        while cells_have < needed and effort_count < 5:
            # boolean board
            ext = self.__get_exterior_set(cluster_id, current_cell, bboard,
                                          max_dist=2)
            ext_list = list(ext)
            ext_list.sort(key=lambda p: manhattan_distance(p,
                                                           self.center_of_board
                                                           ))
            for ex in ext_list:
                if len(overlap_set) == 0:
                    break
                overlap_set.pop()
                current_cell.add(ex)
                x, y = ex
                assert not bboard[y][x]
                bboard[y][x] = True
                cells_have += 1
            if len(overlap_set) == old_overlap_set:
                effort_count += 1
            else:
                effort_count = 0
            old_overlap_set = len(overlap_set)
        assert (cells_have >= len(
            [x for x in self.clusters[cluster_id] if x[0] == self.clb_type]))
