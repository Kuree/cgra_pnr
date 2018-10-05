from __future__ import division, print_function
import random

from arch import group_reg_nets
from placer import Annealer
from .util import deepcopy, compute_hpwl


class SADetailedPlacer(Annealer):
    def __init__(self, blocks, total_cells, netlists, raw_netlist, board,
                 board_pos, disallowed_pos,
                 is_legal=None, fold_reg=True, seed=0, debug=False,
                 clb_type="p"):
        """Please notice that netlists has to be prepared already, i.e., replace
        the remote partition with a pseudo block.
        Also assumes that available_pos is the same size as blocks. If not,
        you have to shrink it the available_pos.
        The board can be an empty board.
        """
        self.blocks = blocks
        available_pos = total_cells[clb_type]
        self.total_cells = total_cells
        self.netlists = netlists
        self.blk_pos = board_pos
        self.board = board
        self.disallowed_pos = disallowed_pos
        self.clb_type = clb_type

        clb_blocks = [b for b in blocks if b[0] == clb_type]
        assert (len(clb_blocks) <= len(available_pos))

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
        current_energy = self.__init_energy(placement)
        board = self.__create_board(placement)
        state = {"placement": placement,
                 "energy": current_energy,
                 "board": board}

        Annealer.__init__(self, initial_state=state, rand=rand)

        # schedule
        self.steps = len(blocks) * 600
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
        pos = list(self.total_cells[self.clb_type])
        num_pos = len(pos)
        placement = {}
        pe_blocks = [b for b in self.blocks if b[0] == self.clb_type]
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
            if blk_id[0] == self.clb_type:
                if len(board[new_pos]) > 0 and board[new_pos][0][0] ==\
                        self.clb_type:
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
                elif len(board[new_pos]) > 0 and board[new_pos][0][0] ==\
                        self.clb_type:
                    p_block = board[new_pos][0]
                    if (blk_id in self.reg_no_pos and
                            p_block in self.reg_no_pos[blk_id]) or \
                            (blk_id[0] == "r" and
                             new_pos in self.disallowed_pos):
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
            available_cells = list(special_cells[blk_type])
            available_cells.sort(key=lambda p: p[0])
            available_cells.sort(key=lambda p: p[1])
            cells = rand.sample(available_cells, len(blks))
            blks.sort(key=lambda x: int(x[1:]))
            for i in range(len(blks)):
                placement[blks[i]] = cells[i]

        assert len(placement) == len(self.blocks)
        return placement

    def __reg_net(self, pos, blk, board):
        # the board will always be occupied
        # this one doesn't check if the board if over populated or not
        if blk[0] == self.clb_type:
            reg = [x for x in board[pos] if x[0] == "r"]
            assert (len(reg) < 2)
            if len(reg) == 1:
                reg = reg[0]
                if reg in self.reg_no_pos and blk in self.reg_no_pos[reg]:
                    return False
        else:
            if blk[0] == "r" and pos in self.disallowed_pos:
                return False
            pe = [x for x in board[pos] if x[0] == self.clb_type]
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

    def commit_changes(self):
        placement = self.state["placement"]
        board = self.state["board"]
        for blk, pos, next_pos in self.moves:
            placement[blk] = next_pos
            self.__update_board(board, blk, pos, next_pos)
        self.moves = set()

    def move(self):
        # reset the move set
        self.moves = set()
        placement = self.state["placement"]
        board = self.state["board"]
        if self.debug:
            available_ids = list(placement.keys())
            available_ids.sort(key=lambda x: int(x[1:]))
            available_pos = list(self.total_cells[self.clb_type])
        else:
            available_ids = placement.keys()
            available_pos = self.total_cells[self.clb_type]

        # use this code to check implementation correctness
        if self.debug:
            self.__check_board_correctness(board, placement)
            reference_hpwl = self.__init_energy(placement)
            assert self.state["energy"] == reference_hpwl

        blk = self.random.sample(available_ids, 1)[0]
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
                self.moves.add((blk, blk_pos, next_pos))
                # self.__update_board(board, blk, blk_pos, next_pos)
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
                    self.moves.add((blk, blk_pos, next_pos))
                    self.moves.add((next_blk, next_pos, blk_pos))
            return

        if self.fold_reg:
            next_pos = self.random.sample(available_pos, 1)[0]
            if next_pos in board:
                blks = board[next_pos]
                same_type_blocks = [b for b in blks if b[0] == blk[0]]
                if len(same_type_blocks) == 1:
                    # swap
                    blk_swap = same_type_blocks[0]
                    if self.__reg_net(next_pos, blk, board) and \
                            self.__reg_net(blk_pos, blk_swap, board):
                        # placement[blk] = next_pos
                        # placement[blk_swap] = blk_pos

                        self.moves.add((blk, blk_pos, next_pos))
                        self.moves.add((blk_swap, next_pos, blk_pos))

                        # update board
                        # self.__update_board(board, blk, blk_pos, next_pos)
                        # self.__update_board(board, blk_swap, next_pos,
                        # blk_pos)

                elif len(same_type_blocks) == 0:
                    # just move there
                    if self.__reg_net(next_pos, blk, board):
                        # update the move
                        # placement[blk] = next_pos
                        self.moves.add((blk, blk_pos, next_pos))

                        # update board
                        # self.__update_board(board, blk, blk_pos, next_pos)
            else:
                # it's an empty spot
                # placement[blk] = next_pos
                self.moves.add((blk, blk_pos, next_pos))

                # update board
                # self.__update_board(board, blk, blk_pos, next_pos)

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

    def __init_energy(self, placement):
        """we use HPWL as the cost function"""
        # merge with state + prefixed positions
        board_pos = self.blk_pos.copy()
        for blk_id in placement:
            pos = placement[blk_id]
            board_pos[blk_id] = pos

        return compute_hpwl(self.netlists, board_pos)

    def energy(self):
        """we use HPWL as the cost function"""
        # early exit
        if len(self.moves) == 0:
            return self.state["energy"]
        changed_nets = {}
        change_net_ids = set()
        pre_energy = self.state["energy"]
        placement = self.state["placement"]

        new_pos = {}
        for blk, _, blk_pos in self.moves:
            new_pos[blk] = blk_pos

        for blk, _, _ in self.moves:
            change_net_ids.update(self.blk_index[blk])
        for net_id in change_net_ids:
            changed_nets[net_id] = self.netlists[net_id]

        board_pos = self.blk_pos.copy()
        for blk_id in placement:
            pos = placement[blk_id]
            board_pos[blk_id] = pos
        old_hpwl = compute_hpwl(changed_nets, board_pos)

        for blk_id in new_pos:
            board_pos[blk_id] = new_pos[blk_id]
        new_hpwl = compute_hpwl(changed_nets, board_pos)

        final_hpwl = pre_energy + (new_hpwl - old_hpwl)

        return final_hpwl

    def realize(self):
        return self.state["placement"]