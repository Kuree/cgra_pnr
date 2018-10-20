#include <algorithm>
#include <iostream>
#include <cassert>
#include "detailed.hh"

#define DEBUG 1

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
                               fixed_pos(),
                               moves_(),
                               clb_type(clb_type),
                               fold_reg_(fold_reg),
                               reg_no_pos_()
{
    // intelligently set the fold reg option
    set_fold_reg(cluster_blocks, fold_reg);

    map<::string, int> blk_id_dict;
    // copy fixed pos over
    this->fixed_pos.reserve(fixed_pos.size());
    for (const auto & iter : fixed_pos) {
        Instance ins(iter.first, Point(iter.second), (int)this->instances.size());
        blk_id_dict.insert({ins.name, ins.id});
        this->fixed_pos.emplace_back(ins);
        this->instances.emplace_back(ins);
        assert (blk_id_dict[ins.name] == ins.id);
    }

    // initial placement
    this->init_place_regular(cluster_blocks, blk_id_dict, available_pos);

    // compute reg no pos
    this->compute_reg_no_pos(cluster_blocks, netlist, blk_id_dict);

    // place registers
    this->init_place_reg(cluster_blocks, blk_id_dict);

    // set up the net
    uint32_t net_id_count = 0;
    for (auto const &iter : netlist) {
        Net net {.net_id = iter.first, .instances = ::vector<int>()};
        for (auto const &blk : iter.second) {
            assert (blk_id_dict.find(blk) != blk_id_dict.end());
            int blk_id = blk_id_dict[blk];
            net.instances.emplace_back(blk_id);
            if (blk_id >= (int)this->instances.size()) {
                std::cerr << blk_id << " blk name: " << blk << std::endl;
                std::cerr << this->instances.size() << " " << blk_id_dict.size() << std::endl;
                assert (false);
            }
            this->instances[blk_id].nets.emplace_back(net_id_count);
        }
        this->netlist.emplace_back(net);
        net_id_count++;
        assert(net_id_count == this->netlist.size());
    }

    // random setup
    detail_rand_.seed(0);

    this->curr_energy = this->init_energy();
}

void DetailedPlacer::set_fold_reg(const std::vector<std::string> &cluster_blocks,
                                  bool fold_reg) {
    if (fold_reg) {
        bool found_reg = false;
        for (auto const & blk_id : cluster_blocks) {
            if (blk_id[0] == 'r') {
                found_reg = true;
                break;
            }
        }
        this->fold_reg_ = found_reg;
    } else {
        this->fold_reg_ = fold_reg;
    }
}

void DetailedPlacer::init_place_regular(const std::vector<std::string> &cluster_blocks,
                                        std::map<std::string, int> &blk_id_dict,
                                        std::map<char, std::vector<std::pair<int, int>>> &available_pos) {
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
        if (fold_reg_ && blk_type == 'r')
            continue;
        int64_t empty_space = available_pos[blk_type].size() - iter.second;
        if (empty_space < 0)
            throw ::runtime_error("Not enough block pos for " + ::string(1, blk_type));
        empty_spaces.insert({blk_type, empty_space});
    }

    for (const auto &blk_name : cluster_blocks) {
        char blk_type = blk_name[0];
        // register has to be done differently
        if (fold_reg_ && blk_type == 'r')
            continue;
        auto pos = available_pos[blk_type].back();
        available_pos[blk_type].pop_back();
        Instance instance(blk_name, pos, (int)instances.size());
        instances.emplace_back(instance);
        blk_id_dict.insert({blk_name, instance.id});
        assert (blk_id_dict[instance.name] == instance.id);
    }

    // fill in dummies
    for (auto const &iter : empty_spaces) {
        char blk_type = iter.first;
        if (iter.second <= 0) {
            continue;
        } else {
            assert (iter.second == (int64_t)available_pos[blk_type].size());
        }
        auto pos = available_pos[blk_type].back();
        available_pos[blk_type].pop_back();
        Instance ins(blk_type, pos, (int)instances.size());
        instances.emplace_back(ins);
    }

    for (const auto &ins : instances) {
        board_.insert({ins.pos, make_pair(ins.id, -1)});
    }
}

void DetailedPlacer::init_place_reg(const std::vector<std::string> &cluster_blocks,
                                    std::map<std::string, int> &blk_id_dict) {
    // create 2D grid
    // for reg fold
    // init it first
    if (fold_reg_) {
        ::vector<Point> positions;
        for (const auto &ins : instances) {
                positions.emplace_back(ins.pos);
        }

        // initial placement for reg fold
        for (const auto &instance_name : cluster_blocks) {
            if (instance_name[0] != 'r')
                continue;
            for (auto const &pos : positions) {
                auto assignment = board_[pos];
                if (assignment.second != -1)
                    continue;
                assert (assignment.first != -1);
                if (reg_no_pos_.find(instance_name) != reg_no_pos_.end()) {
                    auto blks = reg_no_pos_[instance_name];
                    if (std::find(blks.begin(), blks.end(), assignment.second) != blks.end())
                        continue;
                }
                Instance ins(instance_name, pos, (int) instances.size());
                board_[pos] = make_pair(board_[pos].first, ins.id);
                instances.emplace_back(ins);

                blk_id_dict.insert({ins.name, ins.id});
                break;
            }
        }
        // next pass to create dummy registers
        for (const auto &iter : board_) {
            Point pos = iter.first;
            assert (board_[pos].first != -1);
            if (board_[pos].second == -1) {
                Instance ins(::string(1, 'r'), pos, (int) instances.size());
                instances.emplace_back(ins);
                board_[pos] = {board_[pos].first, ins.id};
            }
        }
    }
}

void DetailedPlacer::compute_reg_no_pos(
        const std::vector<std::string> &cluster_blocks,
        std::map<std::string, std::vector<std::string>> &nets,
        std::map<std::string, int> &blk_id_dict) {
    // direct translate from Python implementation
    if (this->fold_reg_) {
        auto linked_net = group_reg_nets(nets);
        for (auto const &iter : linked_net) {
            auto net_id = iter.first;
            auto net = ::vector<::string>();
            net.insert(net.end(), nets[net_id].begin(), nets[net_id].end());
            if (linked_net.find(net_id) != linked_net.end()) {
                for (auto const  &reg_net_id : linked_net[net_id]) {
                    if (nets.find(reg_net_id) != nets.end()) {
                        auto temp_net = nets[reg_net_id];
                        net.insert(net.end(), temp_net.begin(), temp_net.end());
                    }
                }
            }

            for (auto const &blk : net) {
                // we only care about the wire it's driving
                if (blk[0] == 'r' and std::find(cluster_blocks.begin(),
                                                cluster_blocks.end(),
                                                blk) != cluster_blocks.end()) {
                    if (reg_no_pos_.find(blk) == reg_no_pos_.end()) {
                        reg_no_pos_.insert({blk, {}});
                    }
                    for (auto const & bb : net) {
                        if (bb[0] != 'r')
                            reg_no_pos_[blk].insert(blk_id_dict[bb]);
                    }
                }
            }
        }
    }
}

bool DetailedPlacer::is_reg_net(const Instance &ins, const Point &next_pos) {
    if (ins.name[0] == clb_type) {
        auto assigned = board_[next_pos];
        int reg_id = -1;
        if (instances[assigned.first].name[0] == 'r')
            reg_id = assigned.first;
        else if (instances[assigned.second].name[0] == 'r')
            reg_id = assigned.second;
        if (reg_id != -1) {
            const auto &reg_name = instances[reg_id].name;
            if (reg_no_pos_.find(reg_name) != reg_no_pos_.end()) {
                auto ins_list = reg_no_pos_[reg_name];
                if (::find(ins_list.begin(), ins_list.end(), ins.id) != ins_list.end())
                    return false;
            }
        }
    } else if (ins.name[0] == 'r') {
        if (reg_no_pos_.find(ins.name) != reg_no_pos_.end()) {
            auto ins_list = reg_no_pos_[ins.name];
            auto assigned = board_[next_pos];
            if (::find(ins_list.begin(), ins_list.end(), assigned.first) != ins_list.end())
                return false;
            if (::find(ins_list.begin(), ins_list.end(), assigned.second) != ins_list.end())
                return false;
        }
    }
    return true;
}

void DetailedPlacer::move() {
#if DEBUG
    double real_hpwl = get_hpwl(this->netlist, this->instances);
    if (real_hpwl != this->curr_energy) {
        cerr << current_step << " "
             << "real: " << real_hpwl << " current: " << this->curr_energy << endl;
        throw ::runtime_error("checking failed at step " + ::to_string(this->current_step));
    }
    if (fold_reg_) {
        // check board placement is correct
        for (auto const &ins : instances) {
            auto pos = ins.pos;
            assert (board_.find(pos) != board_.end());
            auto assigned = board_[pos];
            if (assigned.first != ins.id && assigned.second != ins.id)
                throw ::runtime_error("checking failed at ins " + ::to_string(ins.id));
        }
    }
#endif
    this->moves_.clear();
    auto curr_ins = instances[detail_rand_.uniform<uint64_t>(this->fixed_pos.size(),
                                                             instances.size() - 1)];
    auto next_ins = instances[detail_rand_.uniform<uint64_t>(this->fixed_pos.size(),
                                                             instances.size() - 1)];
    // if it's legal then swap
    if (curr_ins.name[0] != next_ins.name[0])
        return;

    // check if it's legal in reg net
    if (fold_reg_) {
        if ((!is_reg_net(curr_ins, next_ins.pos))
        || (!is_reg_net(next_ins, curr_ins.pos)))
            return;
    }

    // swap
    this->moves_.insert(DetailedMove{.blk_id = curr_ins.id, .new_pos = next_ins.pos});
    this->moves_.insert(DetailedMove{.blk_id = next_ins.id, .new_pos = curr_ins.pos});
}

double DetailedPlacer::energy() {
    if (!this->moves_.empty()) {
        map<int, Point> original;
        set<int> changed_net;
        for (auto const &move : this->moves_) {
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
        for (const auto &move : moves_) {
            int blk_id = move.blk_id;
            instances[blk_id].pos = move.new_pos;
        }

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
    for (const auto &move : this->moves_) {
        int blk_id = move.blk_id;
        instances[blk_id].pos = Point(move.new_pos);

        if (fold_reg_) {
            assert (board_.find(move.new_pos) != board_.end());
            auto assigned = board_[move.new_pos];
            if (instances[assigned.first].name[0] == instances[blk_id].name[0]) {
                board_[move.new_pos] = {blk_id, assigned.second};
            } else if (instances[assigned.second].name[0] == instances[blk_id].name[0]) {
                board_[move.new_pos] = {assigned.first, blk_id};
            } else {
                throw ::runtime_error("block state not found for instance " +
                                      instances[blk_id].name);
            }
        }
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