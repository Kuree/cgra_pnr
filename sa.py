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
        available_pos = total_cells["p"]
        self.total_cells = total_cells
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
        pos = list(self.total_cells["p"])
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
        assert (pos in board)  # it has to be since we're packing more stuff in
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
        available_pos = list(self.total_cells["p"])

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
        if blk_type != "r":
            # special blocks
            # pick up a random pos
            next_pos = self.random.sample(self.total_cells[blk_type], 1)[0]
            if next_pos not in board or len([b for b in board[next_pos] if
                                             b[0] == blk_type]) == 0:
                # an empty spot
                self.state[blk] = next_pos
                self.moves.add(blk)
            else:
                # swap
                assert len([b for b in board[next_pos] if
                            b[0] == blk_type]) == 1
                next_blk = [b for b in board[next_pos] if
                            b[0] == blk_type][0]
                # make sure that you can swap it
                if (not self.fold_reg) or \
                        (self.__reg_net(next_pos, blk, board) and
                         self.__reg_net(blk_pos, next_blk, board)):
                    self.state[next_blk] = blk_pos
                    self.state[blk] = next_pos
                    self.moves.add(blk)
                    self.moves.add(next_blk)
            return

        if self.fold_reg:
            pos = self.random.choice(available_pos)
            blks = board[pos]
            same_type_blocks = [b for b in blks if b[0] == blk[0]]
            if len(same_type_blocks) == 1:
                # swap
                blk_swap = same_type_blocks[0]
                if self.__reg_net(pos, blk, board) and \
                        self.__reg_net(blk_pos, blk_swap, board):
                    self.state[blk] = pos
                    self.state[blk_swap] = blk_pos

                    self.moves.add(blk)
                    self.moves.add(blk_swap)
            elif len(same_type_blocks) == 0:
                # just move there
                if self.__reg_net(pos, blk, board):
                    # update the move
                    self.state[blk] = pos
                    self.moves.add(blk)

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
        assert (len(self.available_pos) >= len(block_pos))
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
                 is_cell_legal=None, fold_reg=True, seed=0):
        """Notice that each clusters has to be a condensed node in a networkx graph
        whose edge denotes how many intra-cluster connections.
        """
        self.clusters = clusters
        self.netlists = netlists
        self.board = board
        self.board_pos = board_pos.copy()

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

        self.fold_reg = fold_reg

        self.center_of_board = (len(self.board[0]) // 2, len(self.board) // 2)

        cluster_ids = list(clusters.keys())
        self.m_partitions = self.partition_board(self.board_layout, board_info)

        state = self.__init_placement(cluster_ids)

        Annealer.__init__(self, initial_state=state, rand=rand)

        self.netlists = reduce_cluster_graph(netlists, clusters, board_pos)

        # some scheduling stuff?
        # self.Tmax = 10
        # self.steps = 1000

    def get_cluster_size(self, cluster):
        if self.fold_reg:
            p_len = sum([1 for x in cluster if x[0] == "p"])
            r_len = sum([1 for x in cluster if x[0] == "r"])
            return max(p_len, r_len)
        else:
            return len(cluster)

    @staticmethod
    def partition_board(board_layout, board_info):
        width = board_info["width"]
        height = board_info["height"]
        margin = board_info["margin"]

        board_width = width
        board_height = height
        width -= 2 * margin
        height -= 2 * margin

        # we'll try to do a 4x4 macroblock with 2x2 sub-macroblock
        macroblock_size = 4
        assert width % macroblock_size == 0
        assert height % macroblock_size == 0

        m_partitions = {}
        num_x = width // macroblock_size
        if width % macroblock_size != 0:
            num_x += 1
        num_y = height // macroblock_size
        if height % macroblock_size != 0:
            num_y += 1
        m_id = 0
        for y in range(num_y):
            for x in range(num_x):
                sub_blocks = {}
                m_partitions[m_id] = sub_blocks
                m_id += 1
                for i in range(4):
                    sub_blocks[i] = {}
                blk_entry = {}
                for yy in range(macroblock_size):
                    for xx in range(macroblock_size):
                        sub_id = 0
                        if yy >= macroblock_size // 2:
                            sub_id += 2
                        if xx >= macroblock_size // 2:
                            sub_id += 1
                        pos_x = x * macroblock_size + xx + margin
                        pos_y = y * macroblock_size + yy + margin
                        if pos_x >= board_width or pos_y >= board_height:
                            continue
                        blk_type = board_layout[pos_y][pos_x]
                        if blk_type is None:
                            continue
                        if blk_type not in sub_blocks[sub_id]:
                            sub_blocks[sub_id][blk_type] = set()
                        sub_blocks[sub_id][blk_type].add((pos_x, pos_y))

                        # flattened version
                        if blk_type not in blk_entry:
                            blk_entry[blk_type] = 0
                        blk_entry[blk_type] += 1
                sub_blocks.update(blk_entry)

        return m_partitions

    def __init_placement(self, cluster_ids):
        state = {}
        partitions = deepcopy(self.m_partitions)
        for cluster_id in cluster_ids:
            cluster = self.clusters[cluster_id]
            blk_entries = {}
            for blk_id in cluster:
                blk_type = blk_id[0]
                # FIXME: this is a special one and cannot be used anywhere else
                if blk_type == "r":
                    continue
                if blk_type not in blk_entries:
                    blk_entries[blk_type] = 0
                blk_entries[blk_type] += 1
            # we want to maintain fully legal placement
            # fill in non-clb and clb at the same time. however, non-clb
            # has higher priority
            placement = {}
            blk_keys = list(blk_entries.keys())
            blk_keys.sort(key=lambda x: 0 if x != self.clb_type else 1)
            for blk_type in blk_keys:
                terminate = False
                for m_id in partitions:
                    if terminate:
                        break
                    num_blocks = partitions[m_id][blk_type]
                    if num_blocks <= 0:
                        continue
                    # trying to fill in that one
                    sub_block_remove = set()
                    for sub_m_id in partitions[m_id]:
                        if isinstance(sub_m_id, int):
                            # assign to that one
                            for b_type in partitions[m_id][sub_m_id]:
                                if b_type not in blk_entries:
                                    continue
                                if blk_entries[b_type] > 0:
                                    blk_entries[b_type] -=\
                                        len(partitions[m_id][sub_m_id][b_type])
                                    if m_id not in placement:
                                        placement[m_id] = set()
                                    # add sub-macroblock to the placement
                                    placement[m_id].add(sub_m_id)
                                    # remove it from partitions
                                    sub_block_remove.add(sub_m_id)
                    for sub_m_id in sub_block_remove:
                        # decrease the count
                        for b_type in partitions[m_id][sub_m_id]:
                            blks = partitions[m_id][sub_m_id][b_type]
                            partitions[m_id][b_type] -= len(blks)
                        partitions[m_id].pop(sub_m_id, None)

                    # early termination if we've filled up every entries
                    terminate = True
                    for b_type in blk_entries:
                        if blk_entries[b_type] > 0:
                            terminate = False
                            break
            # making sure that we fit inside the board
            for blk_type in blk_entries:
                if blk_entries[blk_type] > 0:
                    raise ClusterException(4)
            state[cluster_id] = placement

        return state

    def move(self):
        pass

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

    def squeeze(self):


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
                    assert (not bboard[y][x])
                bboard[y][x] = True
        return bboard



class ClusterException(Exception):
    def __init__(self, macroblock_size):
        self.macroblock_size = macroblock_size
