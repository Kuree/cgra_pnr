from __future__ import division, print_function
from simanneal import Annealer
from util import compute_hpwl, manhattan_distance, deepcopy
from util import reduce_cluster_graph, compute_centroids
from arch.netlist import group_reg_nets
import numpy as np
import random


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
            if pos in board:
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
            else:
                # it's an empty spot
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
        self.m_partitions, self.centroid_index\
            = self.partition_board(self.board_layout, board_info)

        state = self.__init_placement(cluster_ids)
        self.state_index = self.__build_reverse_placement(state)

        Annealer.__init__(self, initial_state=state, rand=rand)

        self.netlists = reduce_cluster_graph(netlists, clusters, board_pos)

        # some scheduling stuff?
        # self.Tmax = 10
        self.steps = 100

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

        centroid_index = {}

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
        return m_partitions, centroid_index

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

    @staticmethod
    def __build_reverse_placement(state):
        index = {}
        for cluster_id in state:
            for m_id in state[cluster_id]:
                for sub_m_id in state[cluster_id][m_id]:
                    index[(m_id, sub_m_id)] = cluster_id
        return index

    def __initial_energy(self):
        # TO BE IMPLEMENTED
        pass

    def move(self):
        self.state_index = self.__build_reverse_placement(self.state)
        # first we randomly pickup a sub-macroblock
        (m_id, sub_m_id), cluster_id = \
            self.random.choice(list(self.state_index.items()))
        if len(self.state[cluster_id][m_id]) == 4:
            # it's an entire macroblock
            # just find another macroblock and swap with it
            next_m_id = self.random.choice(list(self.m_partitions.keys()))
            if next_m_id in self.state[cluster_id]:
                # early exit
                return
            # see if there is any blocks occupied there
            next_clusters = set()
            for i in range(4):
                if (next_m_id, i) in self.state_index:
                    next_clusters.add(self.state_index[(next_m_id, i)])
            if len(next_clusters) == 0:
                # it's an empty macroblock
                # we are good to go
                self.__update_state_mb(cluster_id, m_id, next_m_id)
            else:
                # we have some clusters there
                # move them all the way to the old macroblock
                for next_cluster_id in next_clusters:
                    self.__update_state_mb(next_cluster_id, next_m_id, m_id)
                # move over
                self.__update_state_mb(cluster_id, m_id, next_m_id)
            return
        else:
            # we have two choice
            # either shuffle, or move around
            if self.random.random() < 0.5:
                # shuffle
                indexes = [None for _ in range(4)]
                old_clusters = {}
                for i in range(4):
                    if (m_id, i) in self.state_index:
                        cluster_id = self.state_index[(m_id, i)]
                        indexes[i] = cluster_id
                        if cluster_id not in old_clusters:
                            old_clusters[cluster_id] = set()
                        old_clusters[cluster_id].add(i)
                self.random.shuffle(indexes)
                clusters = {}
                for i in range(4):
                    cluster_id = indexes[i]
                    if cluster_id is None:
                        continue
                    if cluster_id not in clusters:
                        clusters[cluster_id] = set()
                    clusters[cluster_id].add(i)
                # remove all the old data
                for cluster_id in old_clusters:
                    for sub_m_id in old_clusters[cluster_id]:
                        self.state[cluster_id][m_id].remove(sub_m_id)
                        # remove the old state index
                        self.state_index.pop((m_id, sub_m_id), None)
                # add new data
                for cluster_id in clusters:
                    for sub_m_id in clusters[cluster_id]:
                        self.state[cluster_id][m_id].add(sub_m_id)
                        self.state_index[(m_id, sub_m_id)] = cluster_id
            else:
                # try to change elements with other half-filled macroblocks
                # find other half filled blocks
                blocks = []
                for block_id in self.m_partitions:
                    different_owner = False
                    owner = None
                    filled = 0
                    for i in range(0, 4):
                        if (block_id, i) in self.state_index:
                            if owner is None:
                                owner = self.state_index[(block_id, i)]
                            if self.state_index[(block_id, i)] != owner:
                                different_owner = True
                                break
                            else:
                                filled += 1
                    if different_owner or (filled != 4 and filled != 0):
                        blocks.append(block_id)
                assert m_id in blocks
                # build another table to get random sub-macroblock
                # TODO: implement better update algorithm to allow
                #       fast movement
                blocks.remove(m_id)
                if len(blocks) == 0:
                    # we're good
                    return
                next_block = self.random.sample(blocks, 1)[0]
                # find out its sub-macroblocks
                sub_blocks = []
                for i in range(4):
                    if (next_block, i) in self.state_index:
                        sub_blocks.append(i)
                next_sm = self.random.sample(sub_blocks, 1)[0]
                next_cluster_id = self.state_index[(next_block, next_sm)]

                # update the state
                self.state[cluster_id][m_id].remove(sub_m_id)
                if next_block not in self.state[cluster_id]:
                    self.state[cluster_id][next_block] = set()
                self.state[cluster_id][next_block].add(next_sm)

                self.state[next_cluster_id][next_block].remove(next_sm)
                if m_id not in self.state[next_cluster_id]:
                    self.state[next_cluster_id][m_id] = set()
                self.state[next_cluster_id][m_id].add(sub_m_id)

    def __update_state_mb(self, cluster_id, m_id, next_m_id):
        sub_m = self.state[cluster_id].pop(m_id, None)
        assert sub_m is not None
        self.state[cluster_id][next_m_id] = sub_m

        return

    def energy(self):
        """we use HPWL as the cost function"""
        blk_pos = self.board_pos
        # Keyi:
        # the energy comes with two parts
        # first is the normal HPWL
        # the second is the HPWL within the cluster, by approximation of the
        # bounding box of centroids.
        # Using these two should allow const update time

        def update(pos, cord):
            x, y = pos
            if x < cord["xmin"]:
                cord["xmin"] = x
            if x > cord["xmax"]:
                cord["xmax"] = x
            if y < cord["ymin"]:
                cord["ymin"] = y
            if y > cord["ymax"]:
                cord["ymax"] = y
        hpwl = 0
        for net_id in self.netlists:
            cord_index = {"xmin": 10000, "xmax": -1, "ymin": 10000, "ymax": -1}
            net = self.netlists[net_id]
            for node_id in net:
                if node_id in blk_pos:
                    update(blk_pos[node_id], cord_index)
                else:
                    assert node_id[0] == "x"
                    cluster_id = int(node_id[1:])
                    cluster_pos = self.state[cluster_id]
                    for m_id in cluster_pos:
                        for sub_m in cluster_pos[m_id]:
                            s_pos = self.centroid_index[(m_id, sub_m)]
                            update(s_pos, cord_index)
            hpwl += abs(cord_index["xmax"] - cord_index["xmin"]) + \
                abs(cord_index["ymax"] - cord_index["ymin"])

        # notice that we do double count the wire length here
        # this is necessary to keep all the macro blocks together
        for cluster_id in self.state:
            cord_index = {"xmin": 10000, "xmax": -1, "ymin": 10000, "ymax": -1}
            cluster_pos = self.state[cluster_id]
            for m_id in cluster_pos:
                for sub_m in cluster_pos[m_id]:
                    s_pos = self.centroid_index[(m_id, sub_m)]
                    update(s_pos, cord_index)
            hpwl += abs(cord_index["xmax"] - cord_index["xmin"]) + \
                abs(cord_index["ymax"] - cord_index["ymin"])
        return hpwl

    def realize(self):
        # merge them into per blk_type
        result_cells = {}
        for cluster_id in self.state:
            entry = {}
            result_cells[cluster_id] = entry
            for m_id in self.state[cluster_id]:
                for sub_m_id in self.state[cluster_id][m_id]:
                    blks = self.m_partitions[m_id][sub_m_id]
                    for blk_type in blks:
                        if blk_type not in entry:
                            entry[blk_type] = []
                        entry[blk_type] += blks[blk_type]

        # return centroids as well
        centroids = compute_centroids(result_cells, "p")

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
