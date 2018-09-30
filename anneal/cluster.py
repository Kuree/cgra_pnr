from __future__ import division, print_function
import random
import math
import numpy as np

from anneal import Annealer
from .util import compute_centroids, collapse_netlist,\
    ClusterException, compute_hpwl


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
                 fold_reg=True, seed=0, debug=True):
        """Notice that each clusters has to be a condensed node in a networkx graph
        whose edge denotes how many intra-cluster connections.
        """
        self.clusters = clusters
        self.netlists = netlists
        self.board = board
        self.fixed_pos = fixed_pos.copy()

        board_info = board_meta[-1]
        self.board_layout = board_meta[0]
        self.clb_type = board_info["clb_type"]
        self.clb_margin = board_info["margin"]
        self.height = board_info["height"]
        self.width = board_info["width"]

        self.debug = debug

        self.overlap_factor = 1.0 / 4
        # energy control
        self.overlap_energy = 30 / 2
        self.legal_penalty = {"m": 30, "d": 100}

        rand = random.Random()
        rand.seed(seed)
        self.cluster_index = self.__build_box_netlist_index()

        self.fold_reg = fold_reg

        self.center_of_board = (len(self.board[0]) // 2, len(self.board) // 2)
        self.block_lanes = self.analyze_lanes(self.board_layout)
        self.boxes = {}
        for cluster_id in clusters:
            self.boxes[cluster_id] = Box()

        self.complex_block_cost = 200

        placement = self.__init_placement(rand)
        energy = self.__init_energy(placement)
        state = {"placement": placement, "energy": energy}

        Annealer.__init__(self, initial_state=state, rand=rand)

        self.netlists, self.intra_cluster_count = \
            collapse_netlist(clusters, netlists, fixed_pos)

        self.moves = set()

        # some scheduling stuff?
        # self.Tmax = 10
        # self.steps = 1000

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

    def __update_box(self, box):
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
            elif self.block_lanes[x + width] == self.clb_type:
                width += 1
        box.xmax = current_x

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
                if x >= len(self.board[0]):
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
    def compute_center(state):
        result = {}
        for cluster_id in state:
            box = state[cluster_id]
            x = (box.xmax + box.xmin) // 2
            y = (box.ymax + box.ymin) // 2
            result[cluster_id] = (x, y)
        return result

    def move(self):
        self.moves = set()
        placement = self.state["placement"]
        # we have three options here
        # first, move
        # second, swap
        # third, change shape
        if self.random.random() < 1 / 2.0:
            box = self.random.choice(placement, 1)[0]
            dx = self.random.randrange(-3, 3 + 1)
            dy = self.random.randrange(-3, 3 + 1)
            new_box = Box()
            new_box.xmin = box.xmin + dx
            new_box.ymin = box.ymin + dy
            new_box.xmax = box.xmax + dx
            new_box.ymax = box.ymax + dy
            new_box.total_clb_size = box.total_clb_size
            new_box.c_id = box.c_id
            # to see if it's legal
            if self.__is_legal(new_box, placement):
                self.moves.add(new_box)
                return
        if self.random.random() < 1 / 3.0:
            box1, box2 = self.random.choice(placement, 2)
            # swap their location
            new_box1 = Box.copy_box(box1)
            new_box2 = Box.copy_box(box2)

            new_box1.xmin = box2.xmin
            new_box1.ymin = box2.ymin
            # compute the new end (x/y)
            new_box1.xmax = box2.xmin + (box1.xmax - box1.xmin)
            new_box1.ymax = box2.ymin + (box1.ymax - box1.ymin)

            new_box2.xmin = box1.xmin
            new_box2.ymin = box1.ymin
            # compute the new end (x/y)
            new_box2.xmax = box1.xmin + (box2.xmax - box2.xmin)
            new_box2.ymax = box1.ymin + (box2.ymax - box2.ymin)

            if self.__is_legal(new_box1, placement, box2.c_id) and \
               self.__is_legal(new_box2, placement, box1.c_id):
                self.moves.add(new_box1)
                self.moves.add(new_box2)
                return
        else:
            # this is to reduce the penalty of overlapping
            box = self.random.choice(placement, 1)[0]
            old_height = box.xmax - box.xmin
            new_height = old_height + self.random.randrange(-2, 2 + 1)
            new_box = Box.copy_box(box)
            new_width = int(math.ceil(box.total_clb_size / float(new_height)))
            new_box.xmax = new_box.xmin + new_width
            new_box.ymax = new_box.ymin + new_height

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
        blk_pos = self.fixed_pos

        centers = self.compute_center(placement)
        for node_id in centers:
            c_id = "x" + str(node_id)
            blk_pos[c_id] = centers[node_id]
        hpwl = compute_hpwl(self.netlists, blk_pos)

        # add overlap
        overlap_area = 0
        for c_id in placement:
            box1 = placement[c_id]
            for c_id_next in placement:
                if c_id == c_id_next:
                    continue
                box2 = placement[c_id_next]
                overlap_area += self.__compute_overlap(box1, box2)

        hpwl += overlap_area * self.overlap_energy

        # add legalize energy
        legalize_energy = 0
        for c_id in placement:
            box = placement[c_id]
            blk_count = self.__compute_special_blocks(box)
            for blk_type in blk_count:
                remaining = blk_count[blk_type] - box.special_blocks[blk_type]
                if remaining < 0:
                    legalize_energy += abs(remaining) * \
                                       self.legal_penalty[blk_type]
        hpwl += legalize_energy

        return hpwl

    def energy(self):
        """we use HPWL as the cost function"""
        if len(self.moves) == 0:
            return self.state["energy"]
        placement = self.state["placement"]
        energy = self.state["energy"]
        changed_nets = {}

        # first, compute the new HWPL
        for new_box in self.moves:
            c_id = new_box.c_id
            changed_net_id = self.cluster_index[c_id]
            for net_id in changed_net_id:
                changed_nets[net_id] = self.netlists[net_id]

        blk_pos = self.fixed_pos.copy()
        for c_id in placement:
            box = placement[c_id]
            pos_x = (box.xmin + box.xmax) / 2.0
            pos_y = (box.ymin + box.ymax) / 2.0
            blk_pos[c_id] = (pos_x, pos_y)

        old_hpwl = compute_hpwl(changed_nets, blk_pos)
        # new one
        for new_box in self.moves:
            c_id = new_box.c_id
            new_x = (new_box.xmin + new_box.xmax) // 2
            new_y = (new_box.ymin + new_box.ymax) // 2
            # override the old location
            blk_pos[c_id] = (new_x, new_y)
        new_hpwl = compute_hpwl(changed_nets, blk_pos)

        energy += (new_hpwl - old_hpwl)

        # compute the overlap and legalization
        # some implementation details:
        # 1. we temporarily override the placement and then restore it
        # 2. only compute the old/new energy for changed boxes
        old_overlap = 0
        for box1 in self.moves:
            c_id = box1.c_id
            for c_id_next in placement:
                if c_id == c_id_next:
                    continue
                box2 = placement[c_id_next]
                old_overlap += self.__compute_overlap(box1, box2)
        old_legalize_energy = 0
        for box in self.moves:
            blk_count = self.__compute_special_blocks(box)
            for blk_type in blk_count:
                remaining = blk_count[blk_type] - box.special_blocks[blk_type]
                if remaining < 0:
                    old_legalize_energy += abs(remaining) * \
                                           self.legal_penalty[blk_type]

        changed_boxes = {}
        for box in self.moves:
            changed_boxes[box.c_id] = placement[box.c_id]
            placement[box.c_id] = box

        new_overlap = 0
        for box1 in self.moves:
            c_id = box1.c_id
            for c_id_next in placement:
                if c_id == c_id_next:
                    continue
                box2 = placement[c_id_next]
                new_overlap += self.__compute_overlap(box1, box2)
        new_legalize_energy = 0
        for box in self.moves:
            blk_count = self.__compute_special_blocks(box)
            for blk_type in blk_count:
                remaining = blk_count[blk_type] - box.special_blocks[blk_type]
                if remaining < 0:
                    new_legalize_energy += abs(remaining) * \
                                           self.legal_penalty[blk_type]
        # restore
        for c_id in changed_boxes:
            placement[c_id] = changed_boxes[c_id]

        energy += (new_overlap - old_overlap) * self.overlap_energy
        energy += new_legalize_energy - old_legalize_energy

        return energy

    def commit_changes(self):
        for box in self.moves:
            self.state["placement"][box.c_id] = box

        self.moves = set()

    def __get_exterior_set(self, cluster_id, cluster_cells, board,
                           max_dist=4, search_all=False):
        """board is a boolean map showing everything been taken, which doesn't
           care about overlap
        """
        current_cells = cluster_cells[cluster_id]
        # put it on the actual board so that we can do a brute-force search
        # so we need to offset with pos
        box = self.state[cluster_id]

        # leave 1 for each side
        # TODO: be more careful about the boundaries
        result = set()
        if search_all:
            x_min, x_max = self.clb_margin, len(board[0]) - self.clb_margin
            y_min, y_max = self.clb_margin, len(board) - self.clb_margin
        else:
            x_min, x_max = offset_x - 1, offset_x + bbox[0] + 1
            y_min, y_max = offset_y - 1, offset_y + bbox[1] + 1
        for y in range(y_min, y_max):
            for x in range(x_min, x_max):
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
                        if not self.is_cell_legal(None, (x + j, y + i),
                                                  self.clb_type):
                            continue
                        if (not board[y + i][x + j]) and board[y][x]:
                            p = (x + j, y + i)
                        if (p is not None) and self.is_cell_legal(None, p,
                                                                  self.clb_type):
                            result.add(p)
        for p in result:
            if board[p[1]][p[0]]:
                raise Exception("unknown error" + str(p))
        return result

    def realize(self):
        # the idea is to pull every cell positions to the center of the board



        # return centroids as well
        centroids = compute_centroids(cluster_cells)

        return cluster_cells, centroids

    def __get_bboard(self, cluster_cells, check=True):
        bboard = np.zeros((self.height, self.width), dtype=np.bool)
        for cluster_id in cluster_cells:
            for x, y in cluster_cells[cluster_id]:
                if check:
                    assert(not bboard[y][x])
                bboard[y][x] = True
        return bboard

    def deoverlap(self, cluster_cells, cluster_id, overlap_set):
        effort_count = 0
        old_overlap_set = len(overlap_set)
        while len(overlap_set) > 0 and effort_count < 5:
            # boolean board
            bboard = self.__get_bboard(cluster_cells, False)
            ext = self.__get_exterior_set(cluster_id, cluster_cells, bboard)
            ext_list = list(ext)
            ext_list.sort(key=lambda p: manhattan_distance(p,
                                                            self.center_of_board
                                                            ))
            for ex in ext_list:
                if len(overlap_set) == 0:
                    break
                cell = overlap_set.pop()
                cluster_cells[cluster_id].remove(cell)
                cluster_cells[cluster_id].add(ex)
            if len(overlap_set) == old_overlap_set:
                effort_count += 1
            else:
                effort_count = 0
            old_overlap_set = len(overlap_set)
        assert (len(cluster_cells[cluster_id]) == len(
            self.clusters[cluster_id]))
