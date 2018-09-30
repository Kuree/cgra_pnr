from __future__ import division, print_function
import random

from anneal import Annealer
from .util import deepcopy, compute_centroids, collapse_netlist


class SAMBClusterPlacer(Annealer):
    def __init__(self, clusters, netlists, board, board_pos, board_meta,
                 is_cell_legal=None, fold_reg=True, seed=0,
                 num_mb=16, num_sub_mb=4, debug=False):
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
                                   num_sm_side=self.sub_mb_side,
                                   total_mb_size=num_mb,
                                   clb_type=self.clb_type)

        # obtain index and table information
        self.mb_table = type_table["mb"]
        self.smb_table = type_table["smb"]
        self.mb_index = index_table["mb"]
        self.sub_mb_index = index_table["smb"]

        # reduce netlists
        self.netlists, self.intra_cluster_count = \
            collapse_netlist(clusters, netlists, board_pos)

        state = self.__init_placement(cluster_ids)
        state_index = self.__build_state_index(state)
        state["state_index"] = state_index
        state["energy"] = self.__init_energy(state)

        self.netlist_index = self.__index_clusters(clusters, self.netlists)

        Annealer.__init__(self, initial_state=state, rand=rand)

        # some scheduling stuff?
        # self.Tmax = 10
        self.steps = 15000

        self.debug = debug
        self.moves = set()
        self.count_change = None



    @staticmethod
    def __index_clusters(clusters, netlist):
        result = {}
        blk_table = {}
        for cluster_id in clusters:
            result[cluster_id] = set()
            for blk in clusters[cluster_id]:
                blk_table[blk] = "x" + str(cluster_id)

        for cluster_id in clusters:
            for blk in clusters[cluster_id]:
                blk_id = blk_table[blk]
                for net_id in netlist:
                    net = netlist[net_id]
                    if blk_id in net:
                        result[cluster_id].add(net_id)
        return result

    @staticmethod
    def partition_board(board_layout, board_info, total_mb_size=16,
                        num_sm_side=2, clb_type="p"):
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

                # clean up block entry if it's empty
                entry_to_remove = set()
                for sub_m_id in sub_blocks:
                    if len(sub_blocks[sub_m_id]) == 0:
                        entry_to_remove.add(sub_m_id)
                for sub_m_id in entry_to_remove:
                    sub_blocks.pop(sub_m_id)
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
                if count == 0:
                    continue
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
                    if len(table_entry) == 0:
                        raise Exception("Cannot be empty")
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
        # NOTE: this can be improved further if clock/power domain is used
        mb_index = {}
        mb_smb_table = {}
        for m_id in m_partitions:
            entry = {}
            # get the flatten version
            for sub_mb_id in m_partitions[m_id]:
                if (m_id, sub_mb_id) not in sub_mb_index:
                    continue
                smb_type = sub_mb_index[(m_id, sub_mb_id)]
                entry[sub_mb_id] = smb_type

            found = False
            for mb_type in mb_smb_table:
                table_entry = mb_smb_table[mb_type]
                found = True
                for smb_id in table_entry:
                    if smb_id not in entry:
                        found = False
                        break
                    if entry[smb_id] != table_entry[smb_id]:
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

        mb_table = {}
        for mb_type in mb_smb_table:
            entry = mb_smb_table[mb_type]
            table_entry = {}
            for smb_id in entry:
                smb_type = entry[smb_id]
                smb_entry = sub_mb_table[smb_type]
                for blk_type in smb_entry:
                    if blk_type not in table_entry:
                        table_entry[blk_type] = 0
                    table_entry[blk_type] += smb_entry[blk_type]
            mb_table[mb_type] = table_entry
        # check the table built for mb and smb is correct
        for mb_id in mb_index:
            mb_entry = mb_table[mb_index[mb_id]]
            for blk_type in m_partitions[mb_id]:
                if isinstance(blk_type, int):
                    continue
                if blk_type == "i":
                    continue
                assert mb_entry[blk_type] == m_partitions[mb_id][blk_type]
        for m_id, smb_m_id in sub_mb_index:
            smb_entry = sub_mb_table[sub_mb_index[(m_id, smb_m_id)]]
            for blk_type in m_partitions[m_id][smb_m_id]:
                if blk_type == "i":
                    continue
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
                    if blk_type not in partitions[m_id]:
                        continue
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

    def _check_correctness(self):
        if self.debug:
            placement = self.state["placement"]
            cluster_mb_count = self.state["cluster_mb_count"]
            state_index = self.state["state_index"]
            self.__check_correctness(cluster_mb_count, placement)
            self.__check_state_index_correctness(state_index)

            reference_hpwl = self.__init_energy(self.state)
            assert self.state["energy"] == reference_hpwl

    def move(self):
        # optimizations for checking sub-macroblocks
        # 1. check their type. if the type is the same then
        # automatically allow the swap for that particular
        # sub-macroblocks
        placement = self.state["placement"]
        cluster_mb_count = self.state["cluster_mb_count"]
        state_index = self.state["state_index"]

        self.moves = set()
        self.count_change = None

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
                    self.moves.add((cluster_id, m_id, next_m_id, smb, smb))
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
                        self.moves.add((next_cluster_id, next_m_id, m_id, smb,
                                        smb))
                # move over
                for smb in placement[cluster_id][m_id]:
                    self.moves.add((cluster_id, m_id, next_m_id, smb, smb))

            if not bypass_count:
                # notice that we have already re-compute the count
                # just need to update the count
                assert a_count is not None
                self.count_change = {cluster_id: a_count}
                if b_count_dict is not None:
                    self.count_change.update(b_count_dict)

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
                if different_owner or (filled != self.num_sub_mb and
                                       filled > 0):
                    for i in range(self.num_sub_mb):
                        if (block_id, i) in state_index:
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
            self.count_change = {cluster_id: a_count}
            if b_count is not None:
                self.count_change[next_cluster_id] = b_count

            # update the state
            self.moves.add((cluster_id, m_id, next_block, sub_m_id, next_sm))

            if (next_block, next_sm) in state_index:
                # has assigned
                self.moves.add((next_cluster_id, next_block, m_id, next_sm,
                               sub_m_id))

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
        cluster_mb_count = self.state["cluster_mb_count"]
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
        if self.count_change is not None:
            for next_cluster_id in self.count_change:
                cluster_mb_count[next_cluster_id] = \
                    self.count_change[next_cluster_id]

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

    def __init_energy(self, state):
        """we use HPWL as the cost function"""
        blk_pos = self.board_pos
        placement = state["placement"]
        # Keyi:
        # the energy comes with two parts
        # first is the normal HPWL
        # the second is the HPWL within the cluster, by approximation of the
        # bounding box of centroids.
        # Using these two should allow const update time

        hpwl = 0
        for net_id in self.netlists:
            xmin = 10000
            xmax = -1
            ymin = 10000
            ymax = -1
            net = self.netlists[net_id]
            for node_id in net:
                if node_id in blk_pos:
                    # instead of call the function use plain comparison
                    # instead to speed up python
                    x, y = blk_pos[node_id]
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
                else:
                    assert node_id[0] == "x"
                    cluster_id = int(node_id[1:])
                    cluster_pos = placement[cluster_id]
                    for m_id in cluster_pos:
                        for sub_m in cluster_pos[m_id]:
                            x, y = self.centroid_index[(m_id, sub_m)]
                            if x < xmin:
                                xmin = x
                            if x > xmax:
                                xmax = x
                            if y < ymin:
                                ymin = y
                            if y > ymax:
                                ymax = y
            hpwl += xmax - xmin + ymax - ymin

        # this is necessary to keep all the macro blocks together
        for cluster_id in placement:
            xmin = 10000
            xmax = -1
            ymin = 10000
            ymax = -1
            cluster_pos = placement[cluster_id]
            for m_id in cluster_pos:
                for sub_m in cluster_pos[m_id]:
                    x, y = self.centroid_index[(m_id, sub_m)]
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
            hpwl += (xmax - xmin + ymax - ymin) * \
                self.intra_cluster_count[cluster_id]
        return hpwl

    def commit_changes(self):
        self.__update_state_mb(self.moves)

    def energy(self):
        if len(self.moves) == 0:
            return self.state["energy"]

        placement = self.state["placement"]
        blk_pos = self.board_pos

        # get a list of clusters to recompute the cost function
        # also build change table
        cluster_changed = set()
        smb_change_table = {}
        for cluster_id, m_id, next_block, sub_m_id, next_sm in self.moves:
            cluster_changed.add(cluster_id)
            smb_change_table[(cluster_id, m_id, sub_m_id)] = \
                self.centroid_index[(next_block, next_sm)]

        affected_nets = set()
        for cluster_id in cluster_changed:
            affected_nets.update(self.netlist_index[cluster_id])

        # if too many affected nets, fall back to old one
        if len(affected_nets) * 2.5 > len(self.netlists):
            pre_state = deepcopy(self.state)
            self.commit_changes()
            result = self.__init_energy(self.state)
            self.state = pre_state
            return result

        # first, recompute the nets that got affected before
        old_hpwl = 0
        for net_id in affected_nets:
            xmin = 10000
            xmax = -1
            ymin = 10000
            ymax = -1
            net = self.netlists[net_id]
            for node_id in net:
                if node_id in blk_pos:
                    x, y = blk_pos[node_id]
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
                else:
                    assert node_id[0] == "x"
                    cluster_id = int(node_id[1:])
                    cluster_pos = placement[cluster_id]
                    for m_id in cluster_pos:
                        for sub_m in cluster_pos[m_id]:
                            x, y = self.centroid_index[(m_id, sub_m)]
                            if x < xmin:
                                xmin = x
                            if x > xmax:
                                xmax = x
                            if y < ymin:
                                ymin = y
                            if y > ymax:
                                ymax = y
            old_hpwl += xmax - xmin + ymax - ymin

        for cluster_id in cluster_changed:
            xmin = 10000
            xmax = -1
            ymin = 10000
            ymax = -1
            cluster_pos = placement[cluster_id]
            for m_id in cluster_pos:
                for sub_m in cluster_pos[m_id]:
                    x, y = self.centroid_index[(m_id, sub_m)]
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
            old_hpwl += (xmax - xmin + ymax - ymin) * \
                self.intra_cluster_count[cluster_id]

        new_hpwl = 0
        for net_id in affected_nets:
            xmin = 10000
            xmax = -1
            ymin = 10000
            ymax = -1
            net = self.netlists[net_id]
            for node_id in net:
                if node_id in blk_pos:
                    x, y = blk_pos[node_id]
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
                else:
                    assert node_id[0] == "x"
                    cluster_id = int(node_id[1:])
                    cluster_pos = placement[cluster_id]
                    for m_id in cluster_pos:
                        for sub_m in cluster_pos[m_id]:
                            key_entry = (cluster_id, m_id, sub_m)
                            if key_entry in smb_change_table:
                                s_pos = smb_change_table[key_entry]
                            else:
                                s_pos = self.centroid_index[(m_id, sub_m)]
                            x, y = s_pos
                            if x < xmin:
                                xmin = x
                            if x > xmax:
                                xmax = x
                            if y < ymin:
                                ymin = y
                            if y > ymax:
                                ymax = y
            new_hpwl += xmax - xmin + ymax - ymin

        for cluster_id in cluster_changed:
            xmin = 10000
            xmax = -1
            ymin = 10000
            ymax = -1
            cluster_pos = placement[cluster_id]
            for m_id in cluster_pos:
                for sub_m in cluster_pos[m_id]:
                    key_entry = (cluster_id, m_id, sub_m)
                    if key_entry in smb_change_table:
                        s_pos = smb_change_table[key_entry]
                    else:
                        s_pos = self.centroid_index[(m_id, sub_m)]
                    x, y = s_pos
                    if x < xmin:
                        xmin = x
                    if x > xmax:
                        xmax = x
                    if y < ymin:
                        ymin = y
                    if y > ymax:
                        ymax = y
            new_hpwl += (xmax - xmin + ymax - ymin) * \
                self.intra_cluster_count[cluster_id]

        energy = self.state["energy"] + (new_hpwl - old_hpwl)
        return energy

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
        centroids = compute_centroids(result_cells, self.clb_type)

        return result_cells, centroids


class ClusterException(Exception):
    def __init__(self, macroblock_size):
        self.macroblock_size = macroblock_size