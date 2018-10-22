#include <algorithm>
#include <iostream>
#include <cassert>
#include <string>
#include <cmath>
#include "detailed.hh"

#define DEBUG 1

using std::string;
using std::pair;
using std::map;
using std::vector;
using std::runtime_error;
using std::cerr;
using std::endl;
using std::set;


bool operator< (const DetailedMove &m1, const DetailedMove &m2) {
    return m1.blk_id < m2.blk_id;
}

DetailedPlacer
::DetailedPlacer(::vector<::string> cluster_blocks,
                 ::map<::string, ::vector<::string>> netlist,
                 ::map<char, ::vector<::pair<int, int>>> available_pos,
                 ::map<::string, ::pair<int, int>> fixed_pos,
                 char clb_type,
                 bool fold_reg,
                 double step_ratio) :
                 SimAnneal(),
                 instances_(),
                 netlist_(),
                 instance_ids_(),
                 moves_(),
                 instance_type_index_(),
                 clb_type_(clb_type),
                 fold_reg_(fold_reg),
                 reg_no_pos_() {
    // intelligently set the fold reg option
    set_fold_reg(cluster_blocks, fold_reg);

    ::map<::string, int> blk_id_dict;
    create_fixed_pos(fixed_pos, blk_id_dict);

    // initial placement
    this->init_place_regular(cluster_blocks, blk_id_dict, available_pos);

    // place registers
    this->init_place_reg(cluster_blocks, blk_id_dict);

    // compute reg no pos
    this->compute_reg_no_pos(cluster_blocks, netlist, blk_id_dict);

    // legalize the regs
    this->legalize_reg();

    // set up the net
    process_netlist(netlist, blk_id_dict);

    // random setup
    detail_rand_.seed(0);

    this->curr_energy = this->init_energy();

    // annealing setup
    steps = (int)(cluster_blocks.size() * cluster_blocks.size() * step_ratio);
}


DetailedPlacer
::DetailedPlacer(::map<::string, ::pair<int, int>> init_placement,
                 ::map<::string, ::vector<::string>> netlist,
                 ::map<char, ::vector<::pair<int, int>>> available_pos,
                 ::map<::string, ::pair<int, int>> fixed_pos,
                 char clb_type,
                 bool fold_reg,
                 double step_ratio) :
                 SimAnneal(),
                 instances_(),
                 netlist_(),
                 instance_ids_(),
                 moves_(),
                 instance_type_index_(),
                 clb_type_(clb_type),
                 fold_reg_(fold_reg),
                 reg_no_pos_() {
    // re-make cluster blocks
    ::vector<::string> cluster_blocks;
    cluster_blocks.reserve(init_placement.size());
    for (const auto &iter : init_placement) {
        if (fixed_pos.find(iter.first) == fixed_pos.end())
            cluster_blocks.emplace_back(iter.first);
    }

    // intelligently set the fold reg option
    set_fold_reg(cluster_blocks, fold_reg);

    // fixed position
    ::map<::string, int> blk_id_dict;
    create_fixed_pos(fixed_pos, blk_id_dict);

    // copy all the blocks
    copy_init_placement(init_placement, available_pos, cluster_blocks,
                        blk_id_dict);

    // compute reg no pos
    this->compute_reg_no_pos(cluster_blocks, netlist, blk_id_dict);

    // set up the net
    process_netlist(netlist, blk_id_dict);

    // random setup
    detail_rand_.seed(0);

    this->curr_energy = this->init_energy();

    // annealing setup. low temperature global refinement
    steps = (int)(cluster_blocks.size() * cluster_blocks.size() * step_ratio);
    tmin = 1;
    tmax = std::max(tmin + 0.1, 0.001 * netlist.size());
}

void DetailedPlacer
::copy_init_placement(::map<::string, ::pair<int, int>> &init_placement,
                      ::map<char, ::vector<::pair<int, int>>> &available_pos,
                      const ::vector<::string> &cluster_blocks,
                      ::map<::string, int> &blk_id_dict) {
    ::map<char, ::vector<::string>> blk_counts;
    ::map<char, int64_t> empty_spaces;
    compute_blk_pos(cluster_blocks, available_pos, blk_counts, empty_spaces);

    // create instances as well as dummies
    // also set up the pos index
    for (const auto &iter : blk_counts) {
        uint64_t start_index = instances_.size();
        const char blk_type = iter.first;
        set<Point> working_set;
        for (const auto &pos_iter : available_pos[blk_type]) {
            working_set.insert(Point{pos_iter});
        }
        for (const auto &ins_iter : blk_counts[blk_type]) {
            auto const pos = Point(init_placement[ins_iter]);
            if (working_set.find(pos) == working_set.end())
                throw ::runtime_error("pos " + std::string(pos) +
                                      " for blk " + ins_iter +
                                      " not in working set");
            Instance ins(ins_iter, pos,
                         (int) instances_.size());
            instances_.emplace_back(ins);
            working_set.erase(pos);
            instance_ids_.emplace_back(ins.id);
            blk_id_dict[ins.name] = ins.id;
        }
        // add dummies
        for (uint32_t i = 0; i < empty_spaces[blk_type]; i++) {
            auto pos = *working_set.begin();
            Instance ins(string(1, blk_type), pos, (int) instances_.size());
            instances_.emplace_back(ins);
            working_set.erase(pos);
        }
        if (!working_set.empty())
            throw ::runtime_error("working set not empty!");
        uint64_t end_index = instances_.size() - 1;
        instance_type_index_[blk_type] = {start_index, end_index};
    }
    // and the registers
    if (fold_reg_) {
        uint64_t start_index = instances_.size();
        set<Point> working_set;
        // reg can float everywhere
        for (const auto &iter2 : available_pos[clb_type_])
            working_set.insert(Point(iter2));
        for (const auto &pos_iter : init_placement) {
            if (pos_iter.first[0] != 'r') {
                continue;
            }
            auto pos = Point(pos_iter.second);
            Instance ins(pos_iter.first, pos, (int) instances_.size());
            instances_.emplace_back(ins);
            working_set.erase(pos);
            instance_ids_.emplace_back(ins.id);
            blk_id_dict[ins.name] = ins.id;
        }
        // fill in dummies
        for (auto const &pos : working_set) {
            Instance ins(string(1, 'r'), pos, (int) instances_.size());
            instances_.emplace_back(ins);
        }
        uint64_t end_index = instances_.size() - 1;
        instance_type_index_['r'] = {start_index, end_index};
    }
}


void DetailedPlacer
::create_fixed_pos(const ::map<::string, ::pair<int, int>> &fixed_pos,
                   map<::string, int> &blk_id_dict) {
    // copy fixed pos over
    for (const auto & iter : fixed_pos) {
        Instance ins(iter.first, Point(iter.second), (int) instances_.size());
        blk_id_dict.insert({ins.name, ins.id});
        instances_.emplace_back(ins);
        assert (blk_id_dict[ins.name] == ins.id);
    }
}

void DetailedPlacer::process_netlist(const map<string, vector<string>> &netlist,
                                     map<string, int> &blk_id_dict) {
    uint32_t net_id_count = 0;
    for (auto const &iter : netlist) {
        Net net {.net_id = iter.first, .instances = vector<int>()};
        for (auto const &blk : iter.second) {
            if (blk_id_dict.find(blk) == blk_id_dict.end()) {
                throw ::runtime_error("unknown block " + blk);
            }
            int blk_id = blk_id_dict[blk];
            net.instances.emplace_back(blk_id);
            if (blk_id >= (int) instances_.size()) {
                cerr << blk_id << " blk name: " << blk << endl;
                cerr << instances_.size() << " " << blk_id_dict.size() << endl;
                throw ::runtime_error("no enough space left.");
            }
            instances_[blk_id].nets.emplace_back(net_id_count);
        }
        netlist_.emplace_back(net);
        net_id_count++;
        if (net_id_count != netlist_.size()) {
            throw ::runtime_error("error in creating netlist");
        }
    }
}

void DetailedPlacer::set_fold_reg(const ::vector<::string> &cluster_blocks,
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

void DetailedPlacer
::init_place_regular(const ::vector<::string> &cluster_blocks,
                     ::map<::string, int> &blk_id_dict,
                     ::map<char, ::vector<::pair<int, int>>> &available_pos) {
    ::map<char, ::vector<::string>> blk_counts;
    ::map<char, int64_t> empty_spaces;
    compute_blk_pos(cluster_blocks, available_pos, blk_counts, empty_spaces);

    // create instances for each block (except registers) as well as dummies
    for (const auto &iter : blk_counts) {
        uint64_t start_index = instances_.size();

        char blk_type = iter.first;
        // register has to be done differently
        if (fold_reg_ && blk_type == 'r')
            continue;
        // regular blocks
        for (const auto &blk_name : iter.second) {
            auto pos = available_pos[blk_type].back();
            available_pos[blk_type].pop_back();
            Instance instance(blk_name, pos, (int)instances_.size());
            instances_.emplace_back(instance);
            blk_id_dict.insert({blk_name, instance.id});
            assert (blk_id_dict[instance.name] == instance.id);
            instance_ids_.emplace_back(instance.id);
        }

        // empty dummies
        int64_t available_space = empty_spaces[blk_type];
        if (available_space > 0) {
            assert (available_space == (int64_t)available_pos[blk_type].size());
            for (int i = 0; i < available_space; i++) {
                auto pos = available_pos[blk_type].back();
                available_pos[blk_type].pop_back();
                Instance ins(blk_type, pos, (int) instances_.size());
                instances_.emplace_back(ins);
            }
        }
        uint64_t end_index = instances_.size() - 1;
        instance_type_index_.insert({blk_type, {start_index, end_index}});
    }
}

void DetailedPlacer
::compute_blk_pos(const ::vector<::string> &cluster_blocks,
                  ::map<char, ::vector<::pair<int, int>>> &available_pos,
                  ::map<char, ::vector<::string>> &blk_counts,
                  ::map<char, int64_t> &empty_spaces) const {
    // check if we have enough instances
    // if so, create dummy instances to fill out the board
    for (const auto &blk_name: cluster_blocks) {
        char blk_type = blk_name[0];
        if (fold_reg_ && blk_type == 'r')
            continue;
        if (blk_counts.find(blk_type) == blk_counts.end())
            blk_counts.insert({blk_type, {}});
        blk_counts[blk_type].emplace_back(blk_name);
    }

    // compute empty spaces
    for (const auto &iter : blk_counts) {
        char blk_type = iter.first;
        if (fold_reg_ && blk_type == 'r')
            continue;
        int64_t empty_space = available_pos[blk_type].size() -
                              iter.second.size();
        if (empty_space < 0)
            throw ::runtime_error("Not enough block pos for " +
                                  ::string(1, blk_type));
        empty_spaces.insert({blk_type, empty_space});
    }
}

void DetailedPlacer::init_place_reg(const ::vector<::string> &cluster_blocks,
                                    ::map<::string, int> &blk_id_dict) {
    if (fold_reg_) {
        uint64_t start_index = instances_.size();
        ::vector<Point> positions;
        for (const auto &ins : instances_) {
            if (ins.name[0] == clb_type_)
                positions.emplace_back(ins.pos);
        }

        // initial placement for reg fold
        uint32_t reg_count = 0;
        for (const auto &instance_name : cluster_blocks) {
            if (instance_name[0] != 'r')
                continue;
            const auto &pos = positions[reg_count++];
            Instance ins(instance_name, pos, (int) instances_.size());
            instances_.emplace_back(ins);
            instance_ids_.emplace_back(ins.id);
            blk_id_dict.insert({ins.name, ins.id});

        }
        // next pass to create dummy registers
        for (uint32_t i = reg_count; i < positions.size(); i++) {
            const auto & pos = positions[i];
            Instance ins(::string(1, 'r'), pos, (int) instances_.size());
            instances_.emplace_back(ins);
        }
        uint64_t end_index = instances_.size() - 1;
        instance_type_index_.insert({'r', {start_index, end_index}});
    }
}

void DetailedPlacer::legalize_reg() {
    ::set<Point> available_pos;
    ::set<int> finished_set;
    ::set<int> working_set;

    // get all the available positions
    for (auto const &ins : instances_) {
        if (ins.name[0] != 'r')
            continue;
        available_pos.insert(ins.pos);
        working_set.insert(ins.id);
    }

    // focus on the regs that drives nets
    for (auto const id : working_set) {
        if (reg_no_pos_.find(id) == reg_no_pos_.end())
            continue;
        // find a suitable position
        bool found = false;
        for (auto const &pos : available_pos) {
            bool use = true;
            for (auto const blk_id : reg_no_pos_[id]) {
                if (instances_[blk_id].pos == pos) {
                    use = false;
                    break;
                }
            }
            if (use) {
                instances_[id].pos = pos;
                found = true;
                finished_set.insert(id);
                available_pos.erase(pos);
                break;
            }
        }
        if (!found) {
            throw ::runtime_error("cannot find pos for " + instances_[id].name);
        }
    }

    // randomly assign the rest of them
    for (auto const id : working_set) {
        if (finished_set.find(id) != finished_set.end())
            continue;
        Point pos = *available_pos.begin();
        instances_[id].pos = pos;
        available_pos.erase(pos);
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
                if (std::find(cluster_blocks.begin(),
                              cluster_blocks.end(),
                              blk) != cluster_blocks.end()) {
                    int blk_id = blk_id_dict[blk];
                    if (reg_no_pos_.find(blk_id) == reg_no_pos_.end()) {
                        reg_no_pos_.insert({blk_id, {}});
                    }
                    if (blk[0] == 'r') {
                        for (auto const &bb : net) {
                            if (bb[0] != 'r')
                                reg_no_pos_[blk_id].insert(blk_id_dict[bb]);
                        }
                    } else {
                        // only put registers there
                        for (auto const &bb : net) {
                            if (bb[0] == 'r')
                                reg_no_pos_[blk_id].insert(blk_id_dict[bb]);
                        }
                    }
                }
            }
        }
    }
}

bool DetailedPlacer::is_reg_net(const Instance &ins, const Point &next_pos) {
    int blk_id = ins.id;
    if (reg_no_pos_.find(blk_id) != reg_no_pos_.end()) {
        for (auto const &id : reg_no_pos_[blk_id]) {
            if (next_pos == instances_[id].pos)
                return false;
        }
    }
    return true;
}

void DetailedPlacer::move() {
#if DEBUG
    double real_hpwl = get_hpwl(this->netlist_, this->instances_);
    if (real_hpwl != this->curr_energy) {
        cerr << current_step << " "
             << "real: " << real_hpwl << " current: "
             << this->curr_energy << endl;
        throw ::runtime_error("checking failed at step " +
                              std::to_string(this->current_step));
    }

#endif
    this->moves_.clear();
    auto curr_ins_id =
            instance_ids_[detail_rand_.uniform<uint64_t>
                          (0, instance_ids_.size() - 1)];
    auto curr_ins = instances_[curr_ins_id];
    // only swap with the same type
    char blk_type = curr_ins.name[0];
    auto [start_index, end_index] = instance_type_index_[blk_type];
    auto next_ins = instances_[detail_rand_.uniform<uint64_t>(start_index,
                                                              end_index)];

    if (curr_ins.name[0] != next_ins.name[0])
        throw ::runtime_error("unexpected move selection error");

    if (curr_ins.name == next_ins.name)
        return;

    // check if it's legal in reg net
    if (fold_reg_) {
        if ((!is_reg_net(curr_ins, next_ins.pos))
        || (!is_reg_net(next_ins, curr_ins.pos)))
            return;
    }

    // swap
    this->moves_.insert(DetailedMove{.blk_id = curr_ins.id,
                                     .new_pos = next_ins.pos});
    this->moves_.insert(DetailedMove{.blk_id = next_ins.id,
                                     .new_pos = curr_ins.pos});
}

double DetailedPlacer::energy() {
    if (!this->moves_.empty()) {
        map<int, Point> original;
        set<int> changed_net;
        for (auto const &move : this->moves_) {
            original[move.blk_id] = Point(instances_[move.blk_id].pos);
            for (const int net: instances_[move.blk_id].nets) {
                changed_net.insert(net);
            }
        }
        // convert to net
        vector<Net> nets(changed_net.size());
        int count = 0;
        for (auto const net_id : changed_net) {
            nets[count++] = netlist_[net_id];
        }
        double old_hpwl = get_hpwl(nets, this->instances_);

        // change the locations
        for (const auto &move : moves_) {
            int blk_id = move.blk_id;
            instances_[blk_id].pos = Point(move.new_pos);
        }

        // compute the new hpwl
        double new_hpwl = get_hpwl(nets, this->instances_);

        // revert
        for (const auto &iter : original)
            instances_[iter.first].pos = iter.second;

        return this->curr_energy + (new_hpwl - old_hpwl);

    } else {
        return this->curr_energy;
    }
}

void DetailedPlacer::commit_changes() {
    for (const auto &move : this->moves_) {
        int blk_id = move.blk_id;
        instances_[blk_id].pos = Point(move.new_pos);
    }
}

double DetailedPlacer::init_energy() {
    return get_hpwl(this->netlist_, this->instances_);
}

::map<std::string, std::pair<int, int>> DetailedPlacer::realize() {
    map<::string, ::pair<int, int>> result;
    for (auto const &ins : instances_) {
        if (ins.name.length() > 1)
            result[ins.name] = {ins.pos.x, ins.pos.y};
    }
    return result;
}