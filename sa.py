from __future__ import division, print_function
from simanneal import Annealer
from util import compute_hpwl, deepcopy
from util import reduce_cluster_graph, compute_centroids
from arch.netlist import group_reg_nets
import random


# main class to perform simulated annealing within each cluster
class SADetailedPlacer(Annealer):
    def __init__(self, blocks, total_cells, netlists, raw_netlist, board,
                 board_pos, is_legal=None, fold_reg=True, seed=0, debug=True):
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

        p_blocks = [b for b in blocks if b[0] == "p"]
        assert (len(p_blocks) <= len(available_pos))

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
        placement = self.__init_placement(rand)
        current_energy = self.init_energy(placement)
        board = self.__create_board(placement)
        state = {"placement": placement,
                 "energy": current_energy,
                 "board": board}

        Annealer.__init__(self, initial_state=state, rand=rand)

        # schedule
        self.steps = len(blocks) * 500
        self.num_nets = len(netlists)

        # fast calculation
        self.moves = set()
        self.blk_index = self.__index_netlists(netlists, blocks)

        self.debug = debug

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
        placement = {}
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
                placement[blk_id] = new_pos
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
                placement[blk_id] = new_pos
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
                placement[blks[i]] = cells[i]

        return placement

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

    @staticmethod
    def __update_board(board, blk, pos, next_pos):
        if next_pos not in board:
            board[next_pos] = []
        board[next_pos].append(blk)

        board[pos].remove(blk)
        if len(board[pos]) == 0:
            board.pop(pos, None)

    def move(self):
        # reset the move set
        self.moves = set()
        placement = self.state["placement"]
        board = self.state["board"]
        available_ids = list(placement.keys())
        available_ids.sort(key=lambda x: int(x[1:]))
        available_pos = list(self.total_cells["p"])

        # use this code to check implementation correctness
        if self.debug:
            self.__check_board_correctness(board, placement)

        blk = self.random.choice(available_ids)
        blk_pos = placement[blk]

        # if blk is a special block
        blk_type = blk[0]
        if blk_type != "r":
            # special blocks
            # pick up a random pos
            next_pos = self.random.sample(self.total_cells[blk_type], 1)[0]
            if next_pos not in board or len([b for b in board[next_pos] if
                                             b[0] == blk_type]) == 0:
                # reg net
                if self.fold_reg and next_pos in board and \
                        not self.__reg_net(next_pos, blk, board):
                    return
                # an empty spot
                placement[blk] = next_pos
                self.moves.add(blk)
                self.__update_board(board, blk, blk_pos, next_pos)
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
                    placement[next_blk] = blk_pos
                    placement[blk] = next_pos
                    self.moves.add(blk)
                    self.moves.add(next_blk)

                    # update board
                    board[blk] = next_pos
                    self.__update_board(board, blk, blk_pos, next_pos)
                    self.__update_board(board, next_blk, next_pos, blk_pos)
            return

        if self.fold_reg:
            next_pos = self.random.choice(available_pos)
            if next_pos in board:
                blks = board[next_pos]
                same_type_blocks = [b for b in blks if b[0] == blk[0]]
                if len(same_type_blocks) == 1:
                    # swap
                    blk_swap = same_type_blocks[0]
                    if self.__reg_net(next_pos, blk, board) and \
                            self.__reg_net(blk_pos, blk_swap, board):
                        placement[blk] = next_pos
                        placement[blk_swap] = blk_pos

                        self.moves.add(blk)
                        self.moves.add(blk_swap)

                        # update board
                        self.__update_board(board, blk, blk_pos, next_pos)
                        self.__update_board(board, blk_swap, next_pos, blk_pos)

                elif len(same_type_blocks) == 0:
                    # just move there
                    if self.__reg_net(next_pos, blk, board):
                        # update the move
                        placement[blk] = next_pos
                        self.moves.add(blk)

                        # update board
                        self.__update_board(board, blk, blk_pos, next_pos)
            else:
                # it's an empty spot
                placement[blk] = next_pos
                self.moves.add(blk)

                # update board
                self.__update_board(board, blk, blk_pos, next_pos)

    def __check_board_correctness(self, board, placement):
        current_board = self.__create_board(placement)
        for b_pos in current_board:
            assert len(current_board[b_pos]) == len(board[b_pos])
            for blk in current_board[b_pos]:
                assert blk in board[b_pos]

    @staticmethod
    def __create_board(placement):
        board = {}
        for blk_id in placement:
            b_pos = placement[blk_id]
            if b_pos not in board:
                board[b_pos] = []
            board[b_pos].append(blk_id)
        return board

    def init_energy(self, placement):
        """we use HPWL as the cost function"""
        # merge with state + prefixed positions
        board_pos = self.blk_pos.copy()
        for blk_id in placement:
            pos = placement[blk_id]
            board_pos[blk_id] = pos
        hpwl = 0
        netlist_hpwl = compute_hpwl(self.netlists, board_pos)
        for key in netlist_hpwl:
            hpwl += netlist_hpwl[key]

        return hpwl

    def energy(self):
        """we use HPWL as the cost function"""
        changed_nets = {}
        change_net_ids = set()
        pre_energy = self.pre_state["energy"]
        placement = self.state["placement"]
        pre_placement = self.pre_state["placement"]

        for blk in self.moves:
            change_net_ids.update(self.blk_index[blk])
        for net_id in change_net_ids:
            changed_nets[net_id] = self.netlists[net_id]

        board_pos = self.blk_pos.copy()
        for blk_id in pre_placement:
            pos = pre_placement[blk_id]
            board_pos[blk_id] = pos
        old_netlist_hpwl = compute_hpwl(changed_nets, board_pos)
        old_hpwl = 0
        for key in old_netlist_hpwl:
            old_hpwl += old_netlist_hpwl[key]

        board_pos = self.blk_pos.copy()
        for blk_id in placement:
            pos = placement[blk_id]
            board_pos[blk_id] = pos
        new_netlist_hpwl = compute_hpwl(changed_nets, board_pos)
        new_hpwl = 0
        for key in new_netlist_hpwl:
            new_hpwl += new_netlist_hpwl[key]

        final_hpwl = pre_energy + (new_hpwl - old_hpwl)

        # use the following code to check correctness
        reference_hpwl = self.init_energy(placement)
        assert final_hpwl == reference_hpwl

        self.state["energy"] = final_hpwl

        return final_hpwl

    def realize(self):
        return self.state["placement"]


# main class to perform simulated annealing on each cluster
class SAClusterPlacer(Annealer):
    def __init__(self, clusters, netlists, board, board_pos, board_meta,
                 is_cell_legal=None, fold_reg=True, seed=0,
                 num_sub_mb=4, debug=True):
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

        self.num_sub_mb = num_sub_mb
        self.sub_mb_side = int(num_sub_mb ** 0.5)
        assert self.sub_mb_side ** 2 == num_sub_mb

        cluster_ids = list(clusters.keys())
        self.m_partitions, self.centroid_index, type_table, index_table \
            = self.partition_board(self.board_layout, board_info,
                                   num_sm_side=self.sub_mb_side)

        # obtain index and table information
        self.mb_table = type_table["mb"]
        self.smb_table = type_table["smb"]
        self.mb_index = index_table["mb"]
        self.sub_mb_index = index_table["smb"]

        state = self.__init_placement(cluster_ids)
        state_index = self.__build_state_index(state)
        state["state_index"] = state_index

        Annealer.__init__(self, initial_state=state, rand=rand)

        self.netlists = reduce_cluster_graph(netlists, clusters, board_pos)

        # some scheduling stuff?
        # self.Tmax = 10
        self.steps = 15000

        self.debug = debug

    @staticmethod
    def partition_board(board_layout, board_info, total_mb_size=16,
                        num_sm_side=2):
        width = board_info["width"]
        height = board_info["height"]
        margin = board_info["margin"]

        width -= 2 * margin
        height -= 2 * margin

        x_max = width + margin
        y_max = height + margin

        # used to fat look up
        centroid_index = {}
        # the name of mb_type may be random
        # it's mean for internal usage
        sub_mb_table = {}

        mb_width = int(total_mb_size ** 0.5)
        sub_mb_size = (mb_width // num_sm_side) ** 2
        sub_mb_width = int(sub_mb_size ** 0.5)
        num_sub_mb = total_mb_size // sub_mb_size
        assert sub_mb_width ** 2 == sub_mb_size
        assert mb_width ** 2 == total_mb_size
        assert mb_width % num_sm_side == 0
        assert num_sm_side ** 2 == num_sub_mb

        m_partitions = {}
        num_x = width // mb_width
        if width % mb_width != 0:
            num_x += 1
        num_y = height // mb_width
        if height % mb_width != 0:
            num_y += 1
        m_id = 0
        for y in range(num_y):
            for x in range(num_x):
                sub_blocks = {}
                m_partitions[m_id] = sub_blocks
                m_id += 1
                for i in range(num_sub_mb):
                    sub_blocks[i] = {}
                blk_entry = {}
                for yy in range(mb_width):
                    for xx in range(mb_width):
                        sub_y = yy // sub_mb_width
                        sub_x = xx // sub_mb_width
                        sub_id = sub_y * num_sm_side + sub_x
                        pos_x = x * mb_width + xx + margin
                        pos_y = y * mb_width + yy + margin
                        if pos_x >= x_max or pos_y >= y_max:
                            continue
                        blk_type = board_layout[pos_y][pos_x]
                        if blk_type is None:
                            continue
                        if blk_type not in sub_blocks[sub_id]:
                            sub_blocks[sub_id][blk_type] = set()
                        sub_blocks[sub_id][blk_type].add((pos_x, pos_y))

                        # the information below are pre-computed to speed up
                        # computation later on
                        # flattened version
                        if blk_type not in blk_entry:
                            blk_entry[blk_type] = 0
                        blk_entry[blk_type] += 1
                # clean up block entry if it's empty ?

                sub_blocks.update(blk_entry)
        for m_id in m_partitions:
            for sub_m_id in m_partitions[m_id]:
                if not isinstance(sub_m_id, int):
                    continue
                positions = m_partitions[m_id][sub_m_id]
                xx = 0
                yy = 0
                count = 0
                for blk_type in positions:
                    for x, y in positions[blk_type]:
                        xx += x
                        yy += y
                        count += 1
                center_x = xx // count
                center_y = yy // count
                centroid_index[(m_id, sub_m_id)] = (center_x, center_y)

        # add sub mb_type info
        # not all sub macroblocks are created equal
        sub_mb_index = {}
        for m_id in m_partitions:
            for sub_m_id in m_partitions[m_id]:
                if not isinstance(sub_m_id, int):
                    continue
                entry = {}
                for blk_type in m_partitions[m_id][sub_m_id]:
                    entry[blk_type] = \
                        len(m_partitions[m_id][sub_m_id][blk_type])
                # search for a match in the table
                # brute force is fine since we only need to generate
                # once
                found = False
                for mb_type in sub_mb_table:
                    table_entry = sub_mb_table[mb_type]
                    found = True
                    for blk_type in table_entry:
                        if blk_type not in entry:
                            found = False
                            break
                        if entry[blk_type] != table_entry[blk_type]:
                            found = False
                            break
                    if found:
                        sub_mb_index[(m_id, sub_m_id)] = mb_type
                        break
                if not found:
                    mb_type = "smb" + str(len(sub_mb_table))
                    sub_mb_index[(m_id, sub_m_id)] = mb_type
                    sub_mb_table[mb_type] = entry

        # add mb type info
        # NOTE: this can be improved further if clock/power down is used
        mb_index = {}
        mb_smb_table = {}
        for m_id in m_partitions:
            entry = {}
            # get the flatten version
            for mb_id, sub_mb_id in sub_mb_index:
                if m_id != mb_id:
                    continue
                smb_type = sub_mb_index[(mb_id, sub_mb_id)]
                if smb_type not in entry:
                    entry[smb_type] = 0
                entry[smb_type] += 1

            found = False
            for mb_type in mb_smb_table:
                table_entry = mb_smb_table[mb_type]
                found = True
                for smb_type in table_entry:
                    if smb_type not in entry:
                        found = False
                        break
                    if entry[smb_type] != table_entry[smb_type]:
                        found = False
                        break
                if found:
                    mb_index[m_id] = mb_type
                    break
            if not found:
                mb_type = "mb" + str(len(mb_smb_table))
                # rebuild the table entry with block counters

                mb_smb_table[mb_type] = entry
                mb_index[m_id] = mb_type

        # FIXME: check the location of the smb as well
        mb_table = {}
        for mb_type in mb_smb_table:
            entry = mb_smb_table[mb_type]
            table_entry = {}
            for smb_type in entry:
                smb_count = entry[smb_type]
                smb_entry = sub_mb_table[smb_type]
                for blk_type in smb_entry:
                    if blk_type not in table_entry:
                        table_entry[blk_type] = 0
                    table_entry[blk_type] += smb_count * smb_entry[blk_type]
            mb_table[mb_type] = table_entry
        # check the table built for mb and smb is correct
        for mb_id in mb_index:
            mb_entry = mb_table[mb_index[mb_id]]
            for blk_type in m_partitions[mb_id]:
                if isinstance(blk_type, int):
                    continue
                assert mb_entry[blk_type] == m_partitions[mb_id][blk_type]
        for m_id, smb_m_id in sub_mb_index:
            smb_entry = sub_mb_table[sub_mb_index[(m_id, smb_m_id)]]
            for blk_type in m_partitions[m_id][smb_m_id]:
                assert smb_entry[blk_type] == \
                       len(m_partitions[m_id][smb_m_id][blk_type])

        type_table = {"mb": mb_table, "smb": sub_mb_table}
        index_table = {"mb": mb_index, "smb": sub_mb_index}
        return m_partitions, centroid_index, type_table, index_table

    def __init_placement(self, cluster_ids):
        init_placement = {}
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
            init_placement[cluster_id] = placement

        # sanity check
        cluster_mb_count =\
            self.__check_placement(init_placement, self.clusters,
                                   self.m_partitions)
        state = {"placement": init_placement,
                 "cluster_mb_count": cluster_mb_count}
        return state

    @staticmethod
    def __check_placement(state, clusters, partitions):
        result = {}
        for cluster_id in clusters:
            needed = {}
            for blk in clusters[cluster_id]:
                blk_type = blk[0]
                if blk_type == "r":
                    continue
                if blk_type not in needed:
                    needed[blk_type] = 0
                needed[blk_type] += 1
            # check state if it has enough
            for m_id in state[cluster_id]:
                for sub_m_id in state[cluster_id][m_id]:
                    blocks = partitions[m_id][sub_m_id]
                    for blk_type in blocks:
                        num = len(blocks[blk_type])
                        if blk_type in needed:
                            needed[blk_type] -= num
            for blk_type in needed:
                assert needed[blk_type] <= 0
            result[cluster_id] = needed
        return result

    @staticmethod
    def __build_state_index(state):
        placement = state["placement"]
        index = {}
        for cluster_id in placement:
            for m_id in placement[cluster_id]:
                for sub_m_id in placement[cluster_id][m_id]:
                    index[(m_id, sub_m_id)] = cluster_id
        return index

    def __initial_energy(self):
        # TO BE IMPLEMENTED
        pass

    def move(self):
        # optimizations for checking sub-macroblocks
        # 1. check their type. if the type is the same then
        # automatically allow the swap for that particular
        # sub-macroblocks
        placement = self.state["placement"]
        cluster_mb_count = self.state["cluster_mb_count"]
        state_index = self.state["state_index"]

        moves = set()

        # first we randomly pickup a sub-macroblock
        (m_id, sub_m_id), cluster_id = \
            self.random.choice(list(state_index.items()))
        if len(placement[cluster_id][m_id]) == self.num_sub_mb:
            # it's an entire macroblock
            # just find another macroblock and swap with it
            next_m_id = self.random.choice(list(self.m_partitions.keys()))
            if next_m_id in placement[cluster_id]:
                # early exit
                return
            # mb count check A -> B
            # if B doesn't have enough blocks for A, don't allow
            current_mb_type = self.mb_index[m_id]
            current_mb_entry = self.mb_table[current_mb_type]
            next_mb_type = self.mb_index[next_m_id]
            next_mb_entry = self.mb_table[next_mb_type]

            # count control variables
            a_count = None
            b_count_dict = None

            # if they are the same, by pass the count check
            bypass_count = False
            if current_mb_type == next_mb_type:
                bypass_count = True
            if not bypass_count:
                should_swap = True
                a_count = cluster_mb_count[cluster_id].copy()
                b_count_dict = None
                # remove the current block
                for blk_type in current_mb_entry:
                    if blk_type not in a_count:
                        continue
                    a_count[blk_type] += current_mb_entry[blk_type]
                # add them from the next block
                for blk_type in next_mb_entry:
                    if blk_type not in a_count:
                        continue
                    a_count[blk_type] -= next_mb_entry[blk_type]
                    if a_count[blk_type] > 0:
                        should_swap = False
                        break
                if not should_swap:
                    # early exit
                    return

            # see if there is any blocks occupied there
            next_clusters = {}
            for i in range(self.num_sub_mb):
                if (next_m_id, i) in state_index:
                    next_cluster_id = state_index[(next_m_id, i)]
                    if next_cluster_id not in next_clusters:
                        next_clusters[next_cluster_id] = []
                    next_clusters[next_cluster_id].append(i)
            if len(next_clusters) == 0:
                # it's an empty macroblock
                # we are good to go
                # generate all move assignments
                for smb in placement[cluster_id][m_id]:
                    moves.add((cluster_id, m_id, next_m_id, smb, smb))
            else:
                # we have some clusters there
                # check if we can move. this time it's B -> A
                # we just need to make sure that for each cluster's got moved
                # there is enough blocks.
                # NOTE: we count all the sub-macroblock that belongs to a
                # cluster together
                if not bypass_count:
                    b_count_dict = {}
                    should_swap = True
                    for next_cluster_id in next_clusters:
                        if not should_swap:
                            # early exit
                            break
                        sub_mbs = next_clusters[next_cluster_id]
                        count = cluster_mb_count[next_cluster_id].copy()

                        # remove from the current mb
                        for sub_mb in sub_mbs:
                            sb_entry = \
                                self.smb_table[self.sub_mb_index[(next_m_id,
                                                                  sub_mb)]]
                            next_sb_entry = \
                                self.smb_table[self.sub_mb_index[(m_id,
                                                                  sub_mb)]]
                            for blk_type in sb_entry:
                                if blk_type not in count:
                                    continue
                                count[blk_type] += sb_entry[blk_type]
                            for blk_type in next_sb_entry:
                                if blk_type not in count:
                                    continue
                                count[blk_type] -= next_sb_entry[blk_type]
                        for blk_type in count:
                            if count[blk_type] > 0:
                                should_swap = False
                                break
                        b_count_dict[next_cluster_id] = count
                    if not should_swap:
                        # not enough block left
                        # early exit
                        return

                # move them all the way to the old macroblock
                for next_cluster_id in next_clusters:
                    for smb in next_clusters[next_cluster_id]:
                        moves.add((next_cluster_id, next_m_id, m_id, smb, smb))
                # move over
                for smb in placement[cluster_id][m_id]:
                    moves.add((cluster_id, m_id, next_m_id, smb, smb))

                self.__update_state_mb(moves)

            if not bypass_count:
                # notice that we have already re-compute the count
                # just need to update the count
                assert a_count is not None
                cluster_mb_count[cluster_id] = a_count
                if b_count_dict is not None:
                    for next_cluster_id in b_count_dict:
                        cluster_mb_count[next_cluster_id] = \
                            b_count_dict[next_cluster_id]

        else:
            # we have two choice
            # either shuffle, or move around
            # actually local shuffle is possible to be achieved by moving
            # around, where the destination is the same macroblock

            # try to change elements with other half-filled macroblocks
            # TODO: add a state element to keep track of all half-filled
            # macroblocks
            blocks = set()
            for block_id in self.m_partitions:
                different_owner = False
                owner = None
                filled = 0
                for i in range(self.num_sub_mb):
                    if (block_id, i) in state_index:
                        if owner is None:
                            owner = state_index[(block_id, i)]
                        if state_index[(block_id, i)] != owner:
                            different_owner = True
                            break
                        else:
                            filled += 1
                if different_owner or (filled != self.num_sub_mb and filled > 0):
                    for i in range(self.num_sub_mb):
                        blocks.add((block_id, i))

            assert (m_id, sub_m_id) in blocks
            blocks.remove((m_id, sub_m_id))
            if not blocks:
                # very rare, but we can't do anything if it's unique
                return
            next_block, next_sm = self.random.sample(blocks, 1)[0]

            # if it's point to the same cluster, no need to swap
            if (next_block, next_sm) in state_index:
                # has assigned
                next_cluster_id = state_index[(next_block, next_sm)]
                if next_cluster_id == cluster_id:
                    return
            else:
                next_cluster_id = None

            # check if it's legal to swap
            # first, check A -> B
            a_count = cluster_mb_count[cluster_id].copy()
            current_smb_entry = self.smb_table[self.sub_mb_index[(m_id,
                                                                  sub_m_id)]]
            next_smb_entry = self.smb_table[self.sub_mb_index[(next_block,
                                                               next_sm)]]
            should_swap = self.update_blk_count(a_count, current_smb_entry,
                                                next_smb_entry)
            if not should_swap:
                # early exit
                return

            # then B -> A
            if next_cluster_id is not None:
                b_count = cluster_mb_count[next_cluster_id].copy()
                should_swap = self.update_blk_count(b_count, next_smb_entry,
                                                    current_smb_entry)
                if not should_swap:
                    # early exit
                    return
            else:
                b_count = None

            # update the count
            cluster_mb_count[cluster_id] = a_count
            if b_count is not None:
                cluster_mb_count[next_cluster_id] = b_count

            # update the state
            moves.add((cluster_id, m_id, next_block, sub_m_id, next_sm))

            if (next_block, next_sm) in state_index:
                # has assigned
                moves.add((next_cluster_id, next_block, m_id, next_sm,
                           sub_m_id))

            self.__update_state_mb(moves)

        # use following code to check correctness
        if self.debug:
            self.__check_correctness(cluster_mb_count, placement)
            self.__check_state_index_correctness(state_index)

    def __check_state_index_correctness(self, state_index):
        reference_state_index = self.__build_state_index(self.state)
        assert len(reference_state_index) == len(state_index)
        for key in reference_state_index:
            assert reference_state_index[key] == state_index[key]

    def __check_correctness(self, cluster_mb_count, placement):
        mb_count = \
            self.__check_placement(placement, self.clusters, self.m_partitions)
        for c_id in mb_count:
            for blk_type in mb_count[c_id]:
                assert cluster_mb_count[c_id][blk_type] == \
                       mb_count[c_id][blk_type]

    @staticmethod
    def update_blk_count(a_count, current_smb_entry, next_smb_entry):
        for blk_type in current_smb_entry:
            if blk_type not in a_count:
                continue
            a_count[blk_type] += current_smb_entry[blk_type]
        for blk_type in next_smb_entry:
            if blk_type not in a_count:
                continue
            a_count[blk_type] -= next_smb_entry[blk_type]
        should_swap = True
        for blk_type in a_count:
            if a_count[blk_type] > 0:
                should_swap = False
                break
        return should_swap

    def __update_state_mb(self, moves):
        placement = self.state["placement"]
        state_index = self.state["state_index"]
        for cluster_id, m_id, next_m_id, smb, next_smb in moves:
            # because we may already pop it
            if state_index[(m_id, smb)] == cluster_id:
                state_index.pop((m_id, smb), None)
            if smb in placement[cluster_id][m_id]:
                placement[cluster_id][m_id].remove(smb)
            if len(placement[cluster_id][m_id]) == 0:
                placement[cluster_id].pop(m_id, None)
            # assign placement
            if next_m_id not in placement[cluster_id]:
                placement[cluster_id][next_m_id] = set()
            placement[cluster_id][next_m_id].add(next_smb)

            # update stage index
            state_index[(next_m_id, next_smb)] = cluster_id

        return

    @staticmethod
    def __update_cord(pos, cord):
        x, y = pos
        if x < cord["xmin"]:
            cord["xmin"] = x
        if x > cord["xmax"]:
            cord["xmax"] = x
        if y < cord["ymin"]:
            cord["ymin"] = y
        if y > cord["ymax"]:
            cord["ymax"] = y

    def energy(self):
        """we use HPWL as the cost function"""
        blk_pos = self.board_pos
        placement = self.state["placement"]
        # Keyi:
        # the energy comes with two parts
        # first is the normal HPWL
        # the second is the HPWL within the cluster, by approximation of the
        # bounding box of centroids.
        # Using these two should allow const update time

        hpwl = 0
        for net_id in self.netlists:
            cord_index = {"xmin": 10000, "xmax": -1, "ymin": 10000, "ymax": -1}
            net = self.netlists[net_id]
            for node_id in net:
                if node_id in blk_pos:
                    self.__update_cord(blk_pos[node_id], cord_index)
                else:
                    assert node_id[0] == "x"
                    cluster_id = int(node_id[1:])
                    cluster_pos = placement[cluster_id]
                    for m_id in cluster_pos:
                        for sub_m in cluster_pos[m_id]:
                            s_pos = self.centroid_index[(m_id, sub_m)]
                            self.__update_cord(s_pos, cord_index)
            hpwl += abs(cord_index["xmax"] - cord_index["xmin"]) + \
                abs(cord_index["ymax"] - cord_index["ymin"])

        # notice that we do double count the wire length here
        # this is necessary to keep all the macro blocks together
        for cluster_id in placement:
            cord_index = {"xmin": 10000, "xmax": -1, "ymin": 10000, "ymax": -1}
            cluster_pos = placement[cluster_id]
            for m_id in cluster_pos:
                for sub_m in cluster_pos[m_id]:
                    s_pos = self.centroid_index[(m_id, sub_m)]
                    self.__update_cord(s_pos, cord_index)
            hpwl += (abs(cord_index["xmax"] - cord_index["xmin"]) +
                     abs(cord_index["ymax"] - cord_index["ymin"])) * 2
        return hpwl

    def realize(self):
        placement = self.state["placement"]
        # merge them into per blk_type
        result_cells = {}
        for cluster_id in placement:
            entry = {}
            result_cells[cluster_id] = entry
            for m_id in placement[cluster_id]:
                for sub_m_id in placement[cluster_id][m_id]:
                    blks = self.m_partitions[m_id][sub_m_id]
                    for blk_type in blks:
                        if blk_type not in entry:
                            entry[blk_type] = []
                        entry[blk_type] += blks[blk_type]

        # return centroids as well
        centroids = compute_centroids(result_cells, "p")

        return result_cells, centroids


class ClusterException(Exception):
    def __init__(self, macroblock_size):
        self.macroblock_size = macroblock_size
