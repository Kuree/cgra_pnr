#include <algorithm>
#include <iostream>
#include <cassert>
#include "detailed.hh"

#define DEBUG 0

using namespace std;

bool operator< (const DetailedMove &m1, const DetailedMove &m2) {
    return m1.blk_id < m2.blk_id;
}

DetailedPlacer::DetailedPlacer(std::vector<std::string> cluster_blocks,
                               std::map<std::string, std::vector<std::string>> netlist,
                               std::map<char, std::vector<std::pair<int, int>>> available_pos,
                               std::map<::string, std::pair<int, int>> fixed_pos,
                               char clb_type,
                               bool fold_reg) :
                               SimAnneal(),
                               instances(),
                               netlist(),
                               available_pos(),
                               fixed_pos(),
                               board(),
                               moves(),
                               clb_type(clb_type),
                               fold_reg(fold_reg)
{
    map<::string, int> blk_id_dict;
    int id_count = 0;
    // copy fixed pos over
    this->fixed_pos.reserve(fixed_pos.size());
    for (const auto & iter : fixed_pos) {
        Instance ins(iter.first, Point(iter.second), id_count);
        this->fixed_pos.emplace_back(ins);
        blk_id_dict.insert({ins.name, id_count++});
    }

    // check if we have enough instances
    // if so, create dummy instances to fill out the board
    map<char, int> blk_counts;
    for (const auto &blk_name: cluster_blocks) {
        char blk_type = blk_name[0];
        if (blk_counts.find(blk_type) == blk_counts.end())
            blk_counts.insert({blk_type, 0});
        blk_counts[blk_type] += 1;
    }

    // compute empty spaces
    map<char, int64_t> empty_spaces;
    for (const auto &iter : blk_counts) {
        char blk_type = iter.first;
        if (fold_reg && blk_type == 'r')
            continue;
        int64_t empty_space = available_pos[blk_type].size() - iter.second;
        if (empty_space < 0)
            throw ::runtime_error("Not enough block pos for " + ::string(1, blk_type));
        empty_spaces.insert({blk_type, empty_space});
    }
    // initial placement
    for (const auto &blk_name : cluster_blocks) {
        char blk_type = blk_name[0];
        auto pos = available_pos[blk_type].back();
        available_pos[blk_type].pop_back();
        Instance instance(blk_name, pos, id_count);
        instances.emplace_back(instance);
        blk_id_dict.insert({blk_name, id_count++});
    }

    // TODO:
    // add register net stuff
    // and place register
    if (fold_reg)
        throw ::runtime_error("Not implemented");

    // fill in dummies
    for (auto const &iter : empty_spaces) {
        char blk_type = iter.first;
        if (iter.second <= 0) {
            continue;
        } else{
            assert (iter.second == (int64_t)available_pos[blk_type].size());
        }
        auto pos = available_pos[blk_type].back();
        available_pos[blk_type].pop_back();
        Instance ins(blk_type, pos, (int)instances.size());
        instances.emplace_back(ins);
    }

    // create 2D grid
    // the board is essentially the reverse of placement
    // we need to do that because of the floating registers
    // init it first
    for (const auto &ins : instances) {
        board.insert({ins.pos, make_pair(-1, -1)});
    }

    // initial placement
    for (const auto &ins : instances) {
        if (ins.id >= 0) {
            assert (board.find(ins.pos) != board.end());
            if (board[ins.pos].first == -1) {
                board[ins.pos] = make_pair(ins.id, -1);
            } else if (board[ins.pos].second == -1) {
                board[ins.pos] = make_pair(board[ins.pos].first, ins.id);
            } else {
                cerr << "pos_0: " << board[ins.pos].first
                     << " pos_1: " << board[ins.pos].second
                     << " new: " << ins.id << endl;
                throw ::runtime_error("More than two instances on the same tile!");
            }
        }
    }

    // set up the net
    uint32_t net_id_count = 0;
    for (auto const &iter : netlist) {
        Net net {.net_id = iter.first, .instances = ::vector<int>()};
        for (auto const &blk : iter.second) {
            int blk_id = blk_id_dict[blk];
            net.instances.emplace_back(blk_id);
            this->instances[blk_id].nets.emplace_back(net_id_count);
        }
        this->netlist.emplace_back(net);
        net_id_count++;
        assert(net_id_count == this->netlist.size());
    }

    // random setup
    randutils::random_generator<std::mt19937> detail_rand_;
    detail_rand_.seed(0);

    this->curr_energy = this->init_energy();
}

void DetailedPlacer::move() {
#if DEBUG
    double real_hpwl = get_hpwl(this->netlist, this->instances);
    if (real_hpwl != this->curr_energy) {
        cerr << current_step << " "
             << "real: " << real_hpwl << " current: " << this->curr_energy << endl;
        throw ::runtime_error(" checking failed at step " + ::to_string(this->current_step));
    }
#endif
    this->moves.clear();
    auto curr_ins = instances[detail_rand_.uniform<uint64_t>(0, instances.size() - 1)];
    if (curr_ins.name[0] != 'r') {
        auto next_ins = instances[detail_rand_.uniform<uint64_t>(0, instances.size() - 1)];
        // if it's legal then swap
        // TODO: add legal check for registers
        if (curr_ins.name[0] != next_ins.name[0])
            return;
        // swap
        this->moves.insert(DetailedMove{.blk_id = curr_ins.id, .new_pos = next_ins.pos});
        this->moves.insert(DetailedMove{.blk_id = next_ins.id, .new_pos = curr_ins.pos});
    }
}

double DetailedPlacer::energy() {
    if (!this->moves.empty()) {
        map<int, Point> original;
        set<int> changed_net;
        for (auto const &move : this->moves) {
            original[move.blk_id] = Point(instances[move.blk_id].pos);
            for (const int net: instances[move.blk_id].nets) {
                changed_net.insert(net);
            }
        }
        // convert to net
        vector<Net> nets(changed_net.size());
        int count = 0;
        for (auto const net_id : changed_net) {
            nets[count++] = netlist[net_id];
        }
        double old_hpwl = get_hpwl(nets, this->instances);

        // change the locations
        this->commit_changes();

        // compute the new hpwl
        double new_hpwl = get_hpwl(nets, this->instances);

        // revert
        for (const auto &iter : original)
            instances[iter.first].pos = iter.second;

        return this->curr_energy + (new_hpwl - old_hpwl);

    } else {
        return this->curr_energy;
    }
}

void DetailedPlacer::commit_changes() {
    for (const auto &move : this->moves) {
        int blk_id = move.blk_id;
        instances[blk_id].pos = Point(move.new_pos);
    }
}

double DetailedPlacer::init_energy() {
    return get_hpwl(this->netlist, this->instances);
}

::map<std::string, std::pair<int, int>> DetailedPlacer::realize() {
    map<::string, ::pair<int, int>> result;
    for (auto const &ins : instances) {
        result[ins.name] = ::make_pair(ins.pos.x, ins.pos.y);
    }
    return result;
}