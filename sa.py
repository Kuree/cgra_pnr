from __future__ import division, print_function
from simanneal import Annealer
from util import compute_hpwl, manhattan_distance, deepcopy
from util import reduce_cluster_graph, compute_centroids
from arch.netlist import group_reg_nets
import numpy as np
import random
import math


# main class to perform simulated annealing within each cluster
class SADetailedPlacer(Annealer):
    def __init__(self, blocks, total_cells, netlists, raw_netlist, board,
                 board_pos, is_legal=None, fold_reg=True, seed=0):
        """Please notice that netlists has to be prepared already, i.e., replace
        the remote partition with a pseudo block.
        Also assumes that available_pos is the same size as blocks. If not,
        you have to shrink it the available_pos.
        The board can be an empty board.
        """
        self.blocks = blocks
        # TODO:
        # switch every thing into dictionary based
        available_pos = total_cells["p"]
        self.total_cells = total_cells
        self.available_pos = available_pos
        self.netlists = netlists
        self.blk_pos = board_pos
        self.board = board
        if fold_reg:
            assert (len(blocks) >= len(available_pos))
        else:
            assert (len(blocks) == len(available_pos))
        if is_legal is None:
            if fold_reg:
                self.is_legal = self.__is_legal_fold
            else:
                self.is_legal = lambda pos, blk_id, s: True
        else:
            self.is_legal = is_legal
        self.fold_reg = fold_reg

        # figure out which position on which regs cannot be on the top

        self.reg_no_pos = {}
        if fold_reg:
            linked_nets, _, _ = group_reg_nets(raw_netlist)
            for net_id in netlists:
                net = netlists[net_id]
                if net_id in linked_nets:
                    for reg_net_id in linked_nets[net_id]:
                        if reg_net_id in netlists:
                            net += netlists[reg_net_id]
                for blk in net:
                    # we only care about the wire it's driving
                    if blk[0] == "r" and blk in self.blocks:
                        if blk not in self.reg_no_pos:
                            self.reg_no_pos[blk] = set()
                        for bb in net:
                            if bb == blk:
                                continue
                            if bb in self.blocks:
                                self.reg_no_pos[blk].add(bb)

        rand = random.Random()
        rand.seed(seed)
        state = self.__init_placement(rand)

        Annealer.__init__(self, initial_state=state, rand=rand)

        # schedule
        self.steps = len(blocks) * 125
        self.num_nets = len(netlists)

        # fast calculation
        self.moves = set()
        self.blk_index = self.__index_netlists(netlists, blocks)

        self.pre_state = deepcopy(state)
        self.pre_energy = self.init_energy()

    @staticmethod
    def __index_netlists(netlists, blocks):
        result = {}
        for net_id in netlists:
            for blk in netlists[net_id]:
                if blk not in blocks:
                    continue
                if blk not in result:
                    result[blk] = set()
                result[blk].add(net_id)
        return result

    def __init_placement(self, rand):
        # filling in PE tiles first
        pos = list(self.available_pos)
        num_pos = len(pos)
        state = {}
        pe_blocks = [b for b in self.blocks if b[0] == "p"]
        pe_blocks.sort(key=lambda x: int(x[1:]))
        reg_blocks = [b for b in self.blocks if b[0] == "r"]
        reg_blocks.sort(key=lambda x: int(x[1:]))
        special_blocks = [b for b in self.blocks if b not in pe_blocks and
                          b not in reg_blocks]
        # make sure there is enough space
        assert (max(len(pe_blocks), len(reg_blocks) < len(pos)))
        total_blocks = pe_blocks + reg_blocks

        board = {}
        pos_index = 0
        index = 0
        while index < len(total_blocks):
            blk_id = total_blocks[index]
            new_pos = pos[pos_index % num_pos]
            pos_index += 1
            if new_pos not in board:
                board[new_pos] = []
            if len(board[new_pos]) > 1:
                continue
            if blk_id[0] == "p":
                if len(board[new_pos]) > 0 and board[new_pos][0][0] == "p":
                    continue
                # make sure we're not putting it in the reg net
                elif len(board[new_pos]) > 0 and board[new_pos][0][0] == "r":
                    reg = board[new_pos][0]
                    if reg in self.reg_no_pos and \
                            blk_id in self.reg_no_pos[reg]:
                        continue
                board[new_pos].append(blk_id)
                state[blk_id] = new_pos
                index += 1
            else:
                if len(board[new_pos]) > 0 and board[new_pos][0][0] == "r":
                    continue
                    # make sure we're not putting it in the reg net
                elif len(board[new_pos]) > 0 and board[new_pos][0][0] == "p":
                    p_block = board[new_pos][0]
                    if blk_id in self.reg_no_pos and \
                            p_block in self.reg_no_pos[blk_id]:
                        continue
                board[new_pos].append(blk_id)
                state[blk_id] = new_pos
                index += 1

        # place special blocks
        special_cells = deepcopy(self.total_cells)
        for blk_type in special_cells:
            blks = [b for b in special_blocks if b[0] == blk_type]
            if len(blks) == 0:
                continue
            # random pick up some blocks
            available_cells = special_cells[blk_type]
            cells = rand.sample(available_cells, len(blks))
            for i in range(len(blks)):
                state[blks[i]] = cells[i]

        return state

    def __reg_net(self, pos, blk, board):
        # the board will always be occupied
        # this one doesn't check if the board if over populated or not
        if blk[0] == "p":
            reg = [x for x in board[pos] if x[0] == "r"]
            assert (len(reg) < 2)
            if len(reg) == 1:
                reg = reg[0]
                if reg in self.reg_no_pos and blk in self.reg_no_pos[reg]:
                    return False
        else:
            pe = [x for x in board[pos] if x[0] == "p"]
            assert (len(pe) < 2)
            if len(pe) == 1:
                pe = pe[0]
                if blk in self.reg_no_pos and pe in self.reg_no_pos[blk]:
                    return False
        return True

    def __is_legal_fold(self, pos, blk, board):
        # reverse index pos -> blk
        assert (pos in board)   # it has to be since we're packing more stuff in
        # we only allow capacity 2
        if len(board[pos]) > 1:
            return False
        if board[pos][0][0] == blk[0]:
            return False
        # disallow the reg net
        return self.__reg_net(pos, blk, board)

    def move(self):
        # reset the move set
        self.moves = set()
        available_ids = list(self.state.keys())
        available_ids.sort(key=lambda x: int(x[1:]))
        available_pos = list(self.available_pos)
        available_pe_ids = [x for x in list(self.state.keys()) if x[0] == "p"]
        available_pe_ids.sort(key=lambda x: int(x[1:]))

        board = {}
        for blk_id in self.state:
            b_pos = self.state[blk_id]
            if b_pos not in board:
                board[b_pos] = []
            board[b_pos].append(blk_id)

        blk = self.random.choice(available_ids)
        blk_pos = self.state[blk]

        # if blk is a special block
        blk_type = blk[0]
        # TODO: fix this
        if blk_type != "p" and blk_type != "r":
            # special blocks
            # pick up a random pos
            next_pos = self.random.sample(self.total_cells[blk_type], 1)[0]
            if next_pos not in board or len(board[next_pos]) == 0:
                # an empty spot
                self.state[blk] = next_pos
                self.moves.add(blk)
            else:
                # swap
                assert len(board[next_pos]) == 1
                next_blk = board[next_pos][0]
                self.state[next_blk] = blk_pos
                self.state[blk] = next_pos
                self.moves.add(blk)
                self.moves.add(next_blk)
            return

        if self.fold_reg:
            pos = self.random.choice(available_pos)
            if pos != blk_pos:
                if self.is_legal(pos, blk, board):
                    self.state[blk] = pos
                    self.moves.add(blk)
                else:
                    # swap
                    blks = board[pos]
                    same_type_blocks = [b for b in blks if b[0] == blk[0]]
                    if len(same_type_blocks) == 1:
                        blk_swap = same_type_blocks[0]
                        if self.__reg_net(pos, blk, board) and \
                           self.__reg_net(blk_pos, blk_swap, board):
                            self.state[blk] = pos
                            self.state[blk_swap] = blk_pos

                            self.moves.add(blk)
                            self.moves.add(blk_swap)

        else:
            b = self.random.choice(available_pe_ids)
            pos_b = self.state[b]
            if self.is_legal(blk_pos, b, self.board) and \
                    self.is_legal(pos_b, blk, self.board):
                # swap
                self.state[blk] = pos_b
                self.state[b] = blk_pos

                self.moves.add(blk)
                self.moves.add(b)

    def init_energy(self):
        """we use HPWL as the cost function"""
        # merge with state + prefixed positions
        board_pos = self.blk_pos.copy()
        for blk_id in self.state:
            pos = self.state[blk_id]
            board_pos[blk_id] = pos
        hpwl = 0
        netlist_hpwl = compute_hpwl(self.netlists, board_pos)
        for key in netlist_hpwl:
            hpwl += netlist_hpwl[key]

        return float(hpwl)

    def energy(self):
        """we use HPWL as the cost function"""
        changed_nets = {}
        change_net_ids = set()
        for blk in self.moves:
            change_net_ids.update(self.blk_index[blk])
        for net_id in change_net_ids:
            changed_nets[net_id] = self.netlists[net_id]

        board_pos = self.blk_pos.copy()
        for blk_id in self.pre_state:
            pos = self.pre_state[blk_id]
            board_pos[blk_id] = pos
        old_netlist_hpwl = compute_hpwl(changed_nets, board_pos)
        old_hpwl = 0
        for key in old_netlist_hpwl:
            old_hpwl += old_netlist_hpwl[key]

        board_pos = self.blk_pos.copy()
        for blk_id in self.pre_state:
            pos = self.state[blk_id]
            board_pos[blk_id] = pos
        new_netlist_hpwl = compute_hpwl(changed_nets, board_pos)
        new_hpwl = 0
        for key in new_netlist_hpwl:
            new_hpwl += new_netlist_hpwl[key]

        final_hpwl = self.pre_energy + (new_hpwl - old_hpwl)

        return float(final_hpwl)


# main class to perform simulated annealing within each cluster
class SAMacroPlacer(Annealer):
    def __init__(self, available_pos, netlists, board,
                 board_pos, current_state, is_legal):
        self.available_pos = available_pos
        self.netlists = netlists
        self.board = board
        self.blk_pos = board_pos
        assert (len(current_state) <= len(available_pos))
        self.is_legal = is_legal

        rand = random.Random()
        rand.seed(0)
        state = current_state

        Annealer.__init__(self, initial_state=state, rand=rand)

    def move(self):
        target = self.random.sample(self.state.keys(), 1)[0]
        target_pos = self.state[target]
        dst_pos = self.random.sample(self.available_pos, 1)[0]

        pos_to_block = {}
        for blk_id in self.state:
            pos_to_block[self.state[blk_id]] = blk_id

        if dst_pos in pos_to_block:
            # both of them are actual blocks
            dst_blk = pos_to_block[dst_pos]

            self.state[dst_blk] = target_pos
            self.state[target] = dst_pos
        else:
            # just swap them
            self.state[target] = dst_pos

    def energy(self):
        """we use HPWL as the cost function"""
        # merge with state + prefixed positions
        board_pos = self.blk_pos.copy()
        board_pos.update(self.state)
        hpwl = 0
        netlist_hpwl = compute_hpwl(self.netlists, board_pos)
        for key in netlist_hpwl:
            hpwl += netlist_hpwl[key]
        return float(hpwl)


# unused for CGRA
class DeblockAnnealer(Annealer):
    def __init__(self, block_pos, available_pos, netlists, board_pos,
                 is_legal=None, exclude_list=("u", "m", "i")):
        # by default IO will be excluded
        # place note that in this case available_pos includes empty cells
        # as well
        # we need to reverse index the block pos since we are swapping spaces
        state = {}
        self.excluded_blocks = {}
        for blk_id in block_pos:
            b_type = blk_id[0]
            pos = block_pos[blk_id]
            # always exclude the cluster centroid
            if b_type in exclude_list or b_type == "x":
                self.excluded_blocks[blk_id] = pos
            else:
                state[pos] = blk_id
        self.available_pos = available_pos
        assert(len(self.available_pos) >= len(block_pos))
        self.netlists = netlists
        self.board_pos = board_pos

        if is_legal is not None:
            # this one does not check whether the board is occupied or not
            self.is_legal = is_legal
        else:
            self.is_legal = lambda p, block_id: True

        self.exclude_list = exclude_list

        rand = random.Random()
        rand.seed(0)

        Annealer.__init__(self, initial_state=state, rand=rand)

        # reduce the schedule
        # self.Tmax = self.Tmin + 3
        # self.steps /= 10

    def get_block_pos(self):
        block_pos = {}
        for pos in self.state:
            blk_type = self.state[pos]
            block_pos[blk_type] = pos
        ex = self.excluded_blocks.copy()
        block_pos.update(ex)
        return block_pos

    def move(self):
        pos1, pos2 = self.random.sample(self.available_pos, 2)
        if pos1 in self.state and pos2 in self.state:
            # both of them are actual blocks
            blk1, blk2 = self.state[pos1], self.state[pos2]
            if self.is_legal(pos2, blk1) and self.is_legal(pos1, blk2):
                # update the positions
                self.state[pos1] = blk2
                self.state[pos2] = blk1
        elif pos1 in self.state and pos2 not in self.state:
            blk1 = self.state[pos1]
            if self.is_legal(pos2, blk1):
                self.state.pop(pos1, None)
                self.state[pos2] = blk1
        elif pos1 not in self.state and pos2 in self.state:
            blk2 = self.state[pos2]
            if self.is_legal(pos1, blk2):
                self.state.pop(pos2, None)
                self.state[pos1] = blk2

    def energy(self):
        board_pos = self.board_pos.copy()
        board_pos.update(self.excluded_blocks)

        new_pos = self.get_block_pos()
        board_pos.update(new_pos)

        hpwl = 0
        netlist_hpwl = compute_hpwl(self.netlists, board_pos)
        for key in netlist_hpwl:
            hpwl += netlist_hpwl[key]
        return float(hpwl)


# main class to perform simulated annealing on each cluster
class SAClusterPlacer(Annealer):
    def __init__(self, clusters, netlists, board, board_pos, board_meta,
                 is_legal=None, is_cell_legal=None, place_factor=6,
                 fold_reg=True,
                 seed=0):
        """Notice that each clusters has to be a condensed node in a networkx graph
        whose edge denotes how many intra-cluster connections.
        """
        self.clusters = clusters
        self.netlists = netlists
        self.board = board
        self.board_pos = board_pos.copy()
        self.square_sizes = {}  # look up table for clusters
        if is_legal is None:
            self.is_legal = self.__is_legal
        else:
            self.is_legal = is_legal
        if is_cell_legal is None:
            self.is_cell_legal = lambda p, cb: True
        else:
            self.is_cell_legal = is_cell_legal
        board_info = board_meta[-1]
        self.board_layout = board_meta[0]
        self.clb_type = board_info["clb_type"]
        self.clb_margin = board_info["margin"]

        rand = random.Random()
        rand.seed(seed)

        self.squeeze_iter = 5
        self.place_factor = place_factor
        self.fold_reg = fold_reg

        self.center_of_board = (len(self.board[0]) // 2, len(self.board) // 2)

        # Keyi:
        # because the way it's designed, we can actually shuffle clusters
        # so that there is a chance it will fit after re-ordering
        # set a limit how much shuffling we are going to do
        cluster_ids = list(clusters.keys())
        # determine loop range
        if len(cluster_ids) < 2:
            loop_range = 1
        elif len(cluster_ids) <= 6:
            loop_range = math.factorial(len(cluster_ids))
        else:
            loop_range = len(cluster_ids) * (len(cluster_ids) - 1)
        state = None
        for i in range(loop_range):
            try:
                state = self.__init_placement(cluster_ids, rand)
                break
            except ClusterException as _:
                state = None
                rand.shuffle(cluster_ids)
        if state is None:
            raise ClusterException(len(cluster_ids))

        Annealer.__init__(self, initial_state=state, rand=rand)

        self.netlists = reduce_cluster_graph(netlists, clusters, board_pos)

        # some scheduling stuff?
        # self.Tmax = 10
        # self.steps = 1000

    def __is_legal(self, pos, cluster_id, state):
        """no more than 1/factor overlapping"""
        if pos[0] < self.clb_margin or pos[1] < self.clb_margin:
            return False
        square_size1 = self.square_sizes[cluster_id]
        bbox1 = self.compute_bbox(pos, square_size1)
        if bbox1 is None:
            return False
        xx = bbox1[0] + pos[0]
        yy = bbox1[1] + pos[1]
        if xx >= len(self.board[0]) - self.clb_margin or \
           xx < self.clb_margin or \
           yy >= len(self.board) - self.clb_margin or \
           yy < self.clb_margin:
            return False
        overlap_size = 0
        for c_id in state:
            if c_id == cluster_id:
                continue
            pos2 = state[c_id]
            square_size2 = self.square_sizes[c_id]
            bbox2 = self.compute_bbox(pos2, square_size2)
            if bbox2 is None:
                raise Exception("Unknown state")
            overlap_size += self.__compute_overlap(pos, bbox1, pos2, bbox2)
        if overlap_size > len(self.clusters[cluster_id]) // self.place_factor:
            return False
        else:
            return True

    @staticmethod
    def __compute_overlap(pos1, bbox1, pos2, bbox2):
        if pos2[0] >= pos1[0]:
            x = pos1[0] + bbox1[0] - pos2[0]
        else:
            x = pos2[0] + bbox2[0] - pos1[0]
        if pos2[1] >= pos1[1]:
            y = pos1[1] + bbox1[1] - pos2[1]
        else:
            y = pos2[1] + bbox2[1] - pos1[1]
        if x <= 0 or y <= 0:
            return 0
        else:
            return x * y

    def get_cluster_size(self, cluster):
        if self.fold_reg:
            p_len = sum([1 for x in cluster if x[0] == "p"])
            r_len = sum([1 for x in cluster if x[0] == "r"])
            return max(p_len, r_len)
        else:
            return len(cluster)

    def __init_placement(self, cluster_ids, rand):
        state = {}
        initial_x = self.clb_margin
        x, y = initial_x, self.clb_margin
        rows = []
        current_rows = []
        col = 0
        for cluster_id in cluster_ids:
            cluster = self.clusters[cluster_id]
            cluster_size = self.get_cluster_size(cluster)
            square_size = int(np.ceil(cluster_size ** 0.5))
            self.square_sizes[cluster_id] = square_size
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
                if self.__is_legal(pos, cluster_id, state):
                    state[cluster_id] = pos
                    x += rand.randrange(square_size, square_size + 3)
                    current_rows.append(square_size + y)
                    col += 1
                    break
                x += 1
        return state

    def compute_bbox(self, pos, square_size):
        """pos is top left corner"""
        width = 0
        search_index = 0
        xx = pos[0]
        y = pos[1]
        while width < square_size:
            x = search_index + xx
            if x >= len(self.board[0]):
                return None
            if not self.is_cell_legal(None, (x, y), self.clb_type):
                search_index += 1
                continue
            width += 1
            search_index += 1
        # search_index is the actual span on the board
        return search_index, square_size

    def compute_center(self):
        result = {}
        for cluster_id in self.state:
            pos = self.state[cluster_id]
            bbox = self.compute_bbox(pos, self.square_sizes[cluster_id])
            if bbox is None:
                raise Exception("Unknown state")
            width = bbox[0]
            height = bbox[1]
            center = (pos[0] + width // 2, pos[1] + height // 2)
            result[cluster_id] = center
        return result

    def random_choice(self, input_list):
        index = input_list[int(self.random.random() * len(input_list))]
        return input_list[index]

    def move(self):
        ids = list(self.clusters.keys())
        ids.sort(key=lambda x: x)
        if len(ids) == 1:   # only one cluster
            direct_move = True
        else:
            direct_move = False
        if not direct_move:
            id1 = self.random_choice(ids)
            id2 = self.random_choice(ids)
            pos1, pos2 = self.state[id1], self.state[id2]
            if self.is_legal(pos2, id1, self.state) and \
                    self.is_legal(pos1, id2, self.state):
                self.state[id1] = pos2
                self.state[id2] = pos1
            else:
                direct_move = True
        if direct_move:
            id1 = self.random_choice(ids)
            pos1 = self.state[id1]
            # try to move cluster a little bit
            dx = self.random.randrange(-2, 3)
            dy = self.random.randrange(-2, 3)
            # only compute for cluster1
            new_pos = pos1[0] + dx, pos1[1] + dy
            if self.is_legal(new_pos, id1, self.state):
                self.state[id1] = new_pos

    def energy(self):
        """we use HPWL as the cost function"""
        blk_pos = self.board_pos

        # using the centroid as new state
        centers = self.compute_center()
        for node_id in centers:
            c_id = "x" + str(node_id)
            blk_pos[c_id] = centers[node_id]
        netlist_hpwl = compute_hpwl(self.netlists, blk_pos)
        hpwl = 0
        for key in netlist_hpwl:
            hpwl += netlist_hpwl[key]
        return float(hpwl)

    def __get_exterior_set(self, cluster_id, cluster_cells, board,
                           max_dist=4, search_all=False):
        """board is a boolean map showing everything been taken, which doesn't
           care about overlap
        """
        current_cells = cluster_cells[cluster_id]
        # put it on the actual board so that we can do a brute-force search
        # so we need to offset with pos
        offset_x, offset_y = self.state[cluster_id]
        square_size = self.square_sizes[cluster_id]
        bbox = self.compute_bbox((offset_x, offset_y), square_size)

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
                        if (p is not None) and \
                                self.is_cell_legal(None, p, self.clb_type):
                            result.add(p)
        for p in result:
            if board[p[1]][p[0]]:
                raise Exception("unknown error" + str(p))
        return result

    def squeeze(self):
        # the idea is to pull every cell positions to the center of the board

        def zigzag(width, height, c_index):
            # https://rosettacode.org/wiki/Zig-zag_matrix#Python
            # modified by Keyi
            corner_entries = [(0, 0), (width - 1, 0), (width - 1, height - 1),
                              (0, height - 1)]
            corner = corner_entries[c_index]
            index_order = sorted(
                ((x, y) for x in range(width) for y in range(height)),
                key=lambda p: (manhattan_distance(p, corner)))
            result = {}
            for n, index in enumerate(index_order):
                result[n] = index
            return result

        cluster_pos = self.state
        cluster_cells = {}
        used_special_blocks_pos = set()
        special_cells = {}
        # make each position sets
        for cluster_id in cluster_pos:
            pos = cluster_pos[cluster_id]
            cluster_size = self.get_cluster_size(self.clusters[cluster_id])
            square_size = self.square_sizes[cluster_id]
            bbox = self.compute_bbox(pos, square_size)
            # find four corners and compare which one is closer
            corners = [
                pos,
                [pos[0] + bbox[0], pos[1]],
                [pos[0] + bbox[0], pos[1] + bbox[1]],
                [pos[0], pos[1] + bbox[1]]]
            dists = [manhattan_distance(p, self.center_of_board)
                     for p in corners]
            corner_index = np.argmin(dists)
            # we need to create a zig-zag index to maximize packing cells given
            # the bounding box
            matrix = zigzag(bbox[0], bbox[1], corner_index)
            # put into positions
            cells = set()
            count = 0
            search_count = 0
            while count < cluster_size:
                cell_pos = matrix[search_count]
                cell_pos = (pos[0] + cell_pos[0], pos[1] + cell_pos[1])
                if self.is_cell_legal(None, cell_pos, self.clb_type):
                    cells.add(cell_pos)
                    count += 1
                search_count += 1
            cluster_cells[cluster_id] = cells

            extra_cells = self.assign_special_blocks(
                self.clusters[cluster_id], cluster_pos[cluster_id], bbox,
                self.board_layout, used_special_blocks_pos)
            special_cells[cluster_id] = extra_cells

        # now the fun part, lets squeeze more!
        # algorithm
        # in each iteration, each cluster selects top N manhattan distance cells
        # and then move to its exterior.
        # this avoids "mixture" boundary between two clusters in
        # first step: remove overlaps

        # several tweaks:
        # because the middle ones have limited spaces. we de-overlap the middle
        # ones first
        cluster_ids = list(cluster_pos.keys())
        cluster_ids.sort(key=lambda cid: manhattan_distance(cluster_pos[cid],
                                                            self.center_of_board
                                                            ))
        special_working_set = set()
        for cluster_id1 in cluster_ids:
            overlap_set = set()
            for cluster_id2 in cluster_cells:
                if cluster_id1 == cluster_id2:
                    continue
                overlap = cluster_cells[cluster_id1].intersection(
                    cluster_cells[cluster_id2])
                overlap_set = overlap_set.union(overlap)

            assert (len(cluster_cells[cluster_id1]) ==
                    self.get_cluster_size(self.clusters[cluster_id1]))
            # boolean board
            bboard = self.__get_bboard(cluster_cells, False)
            self.deoverlap(cluster_cells, cluster_id1, overlap_set)
            if overlap_set:
                print("Failed to de-overlap cluster ID:", cluster_id1,
                      "Heuristics will be used to put them together")
                special_working_set.add(cluster_id1)
                extra_cells = self.find_space(bboard, len(overlap_set))
                for cell in extra_cells:
                    old_cell = overlap_set.pop()
                    cluster_cells[cluster_id1].remove(old_cell)
                    cluster_cells[cluster_id1].add(cell)
                    assert(not bboard[cell[1]][cell[0]])
            assert (len(cluster_cells[cluster_id1]) ==
                    self.get_cluster_size(self.clusters[cluster_id1]))

        for i in self.clusters:
            assert(len(cluster_cells[i]) ==
                   self.get_cluster_size(self.clusters[i]))
        # check no overlap
        self.__get_bboard(cluster_cells)

        # squeeze them to the center
        for it in range(self.squeeze_iter):
            # print("iter:", it)
            for cluster_id in cluster_cells:
                self.squeeze_cluster(cluster_cells, cluster_id)

        for cluster_id in special_working_set:
            while True:
                num_moves = self.squeeze_cluster(cluster_cells, cluster_id)
                if num_moves <= 5:
                    break

        # merge them into per blk_type
        result_cells = {}
        for cluster_id in cluster_cells:
            result_cells[cluster_id] = {"p": cluster_cells[cluster_id]}

        # add special cells to the final position
        for cluster_id in special_cells:
            result_cells[cluster_id].update(special_cells[cluster_id])

        # return centroids as well
        centroids = compute_centroids(result_cells)

        return result_cells, centroids

    @staticmethod
    def assign_special_blocks(cluster, cluster_pos, bbox, board_layout,
                              used_spots):
        special_blks = {}
        cells = {}
        for blk_id in cluster:
            blk_type = blk_id[0]
            if blk_type != "p" and blk_type != "r" and blk_type != "i":
                if blk_type not in special_blks:
                    special_blks[blk_type] = 0
                special_blks[blk_type] += 1

        pos_x, pos_y = cluster_pos
        width, height = bbox
        centroid = pos_x + width // 2, pos_y + height / 2
        for x in range(pos_x, pos_x + width):
            for y in range(pos_y, pos_y + width):
                blk_type = board_layout[y][x]
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
        for y in range(len(board_layout)):
            for x in range(len(board_layout[y])):
                pos = (x, y)
                blk_type = board_layout[y][x]
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

    @staticmethod
    def __get_bboard(cluster_cells, check=True):
        bboard = np.zeros((60, 60), dtype=np.bool)
        for cluster_id in cluster_cells:
            for x, y in cluster_cells[cluster_id]:
                if check:
                    assert(not bboard[y][x])
                bboard[y][x] = True
        return bboard

    def squeeze_cluster(self, cluster_cells, cluster_id, max_moves=15):
        bboard = np.zeros((60, 60), dtype=np.bool)
        for cluster_id1 in cluster_cells:
            for x, y in cluster_cells[cluster_id1]:
                if bboard[y][x]:
                    raise Exception("overlap")
                bboard[y][x] = True
        ext_set = self.__get_exterior_set(cluster_id, cluster_cells,
                                          bboard,
                                          max_dist=1, search_all=True)
        ext_set = list(ext_set)
        ext_set.sort(key=lambda pos: manhattan_distance(pos,
                                                        self.center_of_board
                                                        ))
        own_cells = list(cluster_cells[cluster_id])
        own_cells.sort(key=lambda pos:
                       manhattan_distance(pos, self.center_of_board),
                       reverse=True)
        num_moves = 0
        while len(ext_set) > 0 and len(own_cells) > 0:
            if num_moves > max_moves:
                break
            num_moves += 1
            new_cell = ext_set.pop(0)
            assert (not bboard[new_cell[1]][new_cell[0]])
            old_cell = own_cells.pop(0)
            if manhattan_distance(new_cell, self.center_of_board) > \
                    manhattan_distance(old_cell, self.center_of_board):
                # no need to proceed
                break
            cluster_cells[cluster_id].remove(old_cell)
            cluster_cells[cluster_id].add(new_cell)
        return num_moves

    def find_space(self, bboard, num_cells):
        # trying to fnd a continuous space on the board that can fit `num_cells`
        # because we put cells from left -> right, top->bottom
        # we search from the bottom left corner, even though it might not be
        # true after the SA process
        square_size = int(np.ceil(num_cells ** 0.5))
        for i in range(len(bboard) - square_size - 1, -1, -1):
            for j in range(len(bboard[0]) - square_size - 1, -1, -1):
                pos = (j, i)
                bbox = self.compute_bbox(pos, square_size)
                if bbox is None:
                    continue
                cells = []
                for y in range(bbox[1]):
                    for x in range(bbox[0]):
                        new_cell = (x + j, y + i)
                        if (not bboard[new_cell[1]][new_cell[0]]) and \
                                (self.is_cell_legal(None, new_cell,
                                                    self.clb_type)):
                            cells.append(new_cell)
                if len(cells) > num_cells:
                    # we are good
                    return set(cells[:num_cells])
        # failed to find any space
        # brute force to fill in any space available
        result = set()
        for i in range(len(bboard)):
            for j in range(len(bboard[0])):
                pos = (j, i)
                if self.is_cell_legal(None, pos, self.clb_type):
                    result.add(pos)
                if len(result) == num_cells:
                    return result
        raise Exception("No empty space left on the board")

    def deoverlap(self, cluster_cells, cluster_id, overlap_set):
        effort_count = 0
        old_overlap_set = len(overlap_set)
        while len(overlap_set) > 0 and effort_count < 5:
            # boolean board
            bboard = self.__get_bboard(cluster_cells, False)
            ext = self.__get_exterior_set(cluster_id, cluster_cells, bboard)
            ext_list = list(ext)
            ext_list.sort(key=lambda p:
                          manhattan_distance(p, self.center_of_board))
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
        assert (len(cluster_cells[cluster_id]) == self.get_cluster_size(
            self.clusters[cluster_id]))


class ClusterException(Exception):
    def __init__(self, num_clusters):
        self.num_clusters = num_clusters
