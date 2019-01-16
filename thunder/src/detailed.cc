#include <algorithm>
#include <iostream>
#include <cassert>
#include <string>
#include <cmath>
#include "detailed.hh"
#include "include/tqdm.h"

#define CLAMP(x, low, high)  (((x) > (high)) ? (high) : \
                             (((x) < (low)) ? (low) : (x)))
#define DEBUG 0

using std::string;
using std::pair;
using std::map;
using std::vector;
using std::runtime_error;
using std::cerr;
using std::endl;
using std::set;

char DetailedPlacer::REG_BLK_TYPE = 'r';

bool operator< (const DetailedMove &m1, const DetailedMove &m2) {
    return m1.blk_id < m2.blk_id;
}

DetailedPlacer
::DetailedPlacer(::vector<::string> cluster_blocks,
                 ::map<::string, ::vector<::string>> netlist,
                 ::map<char, ::vector<::pair<int, int>>> available_pos,
                 ::map<::string, ::pair<int, int>> fixed_pos,
                 char clb_type,
                 bool fold_reg) :
                 SimAnneal(),
                 instances_(),
                 netlist_(),
                 instance_ids_(),
                 moves_(),
                 instance_type_index_(),
                 clb_type_(clb_type),
                 fold_reg_(fold_reg),
                 reg_no_pos_(),
                 loc_instances_() {
    // intelligently set the fold reg option
    set_fold_reg(cluster_blocks, fold_reg);

    ::map<::string, int> blk_id_dict;
    create_fixed_pos(fixed_pos, blk_id_dict);

    // initial placement
    this->init_place_regular(cluster_blocks, blk_id_dict, available_pos);

    // place registers
    this->init_place_reg(cluster_blocks, available_pos, blk_id_dict);

    // compute reg no pos
    this->compute_reg_no_pos(cluster_blocks, netlist, blk_id_dict);

    // legalize the regs
    this->legalize_reg();

    // set up the net
    process_netlist(netlist, blk_id_dict);

    // random setup
    detail_rand_.seed(0);

    this->curr_energy = this->init_energy();

    index_loc();

    // set bounds
    set_bounds(available_pos);
}

void DetailedPlacer::set_seed(uint32_t seed) {
    detail_rand_.seed(seed);
}

void DetailedPlacer::index_loc() {
    // index to loc
    for (const auto &instance : instances_) {
        auto pos = instance.pos;
        const char blk_type = instance.name[0];
        if (loc_instances_.find(blk_type) == loc_instances_.end())
            loc_instances_[blk_type] = {};
        loc_instances_[blk_type].insert({{pos.x, pos.y}, instance.id});
    }
}

void
DetailedPlacer::set_bounds(const ::map<char, ::vector<pair<int, int>>>
                           &available_pos) {
    // determine the d_limit by looping through the available pos
    int xmax = 0, ymax = 0;
    for (const auto &iter : available_pos) {
        for (const auto &p : iter.second) {
            if (p.first > xmax)
                xmax = p.first;
            if (p.second > ymax)
                ymax = p.second;
        }
    }
    max_dim_ = xmax > ymax ? xmax : ymax;
    d_limit_ = static_cast<uint32_t>(max_dim_);
    num_blocks_ = static_cast<uint32_t>(instance_ids_.size());
}


DetailedPlacer
::DetailedPlacer(::map<::string, ::pair<int, int>> init_placement,
                 ::map<::string, ::vector<::string>> netlist,
                 ::map<char, ::vector<::pair<int, int>>> available_pos,
                 ::map<::string, ::pair<int, int>> fixed_pos,
                 char clb_type,
                 bool fold_reg) :
                 SimAnneal(),
                 instances_(),
                 netlist_(),
                 instance_ids_(),
                 moves_(),
                 instance_type_index_(),
                 clb_type_(clb_type),
                 fold_reg_(fold_reg),
                 reg_no_pos_(),
                 loc_instances_() {
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

    index_loc();

    // set bounds
    set_bounds(available_pos);
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
        if (blk_counts.find(blk_type) == blk_counts.end())
            blk_counts.insert({blk_type, {}});
        blk_counts[blk_type].emplace_back(blk_name);
    }

    // compute empty spaces
    for (const auto &iter : blk_counts) {
        char blk_type = iter.first;
        int64_t empty_space = available_pos[blk_type].size() -
                              iter.second.size();
        if (empty_space < 0)
            throw ::runtime_error("Not enough block pos for " +
                                  ::string(1, blk_type) + " got " +
                                  std::to_string(
                                          available_pos[blk_type].size())
                                  + " need " +
                                  std::to_string(iter.second.size()) );
        empty_spaces.insert({blk_type, empty_space});
    }
}

void
DetailedPlacer::init_place_reg(const ::vector<::string> &cluster_blocks,
                               ::map<char,
                                     ::vector<::pair<int, int>>> &available_pos,
                               ::map<::string, int> &blk_id_dict) {
    if (fold_reg_) {
        uint64_t start_index = instances_.size();
        ::vector<Point> positions;
        auto reg_positions = available_pos[REG_BLK_TYPE];
        for (const auto &pos : reg_positions) {
            positions.emplace_back(pos);
        }

        // initial placement for reg fold
        uint32_t reg_count = 0;
        for (const auto &instance_name : cluster_blocks) {
            if (instance_name[0] != REG_BLK_TYPE)
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
        if (ins.name[0] != REG_BLK_TYPE)
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
                    if (blk[0] == REG_BLK_TYPE) {
                        for (auto const &bb : net) {
                            if (bb[0] != REG_BLK_TYPE)
                                reg_no_pos_[blk_id].insert(blk_id_dict[bb]);
                        }
                    } else {
                        // only put registers there
                        for (auto const &bb : net) {
                            if (bb[0] == REG_BLK_TYPE)
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

    // check loc instance
    for (const auto &id : instance_ids_) {
        const auto &instance = instances_[id];
        const auto blk_type = instance.name[0];
        auto pos = std::make_pair(instance.pos.x, instance.pos.y);
        if (loc_instances_[blk_type][pos] != id)
            throw ::runtime_error("loc checking is wrong");
    }

#endif
    this->moves_.clear();
    auto curr_ins_id =
            instance_ids_[detail_rand_.uniform<uint64_t>
                          (0, instance_ids_.size() - 1)];
    auto curr_ins = instances_[curr_ins_id];
    // only swap with the same type
    char blk_type = curr_ins.name[0];
    // search for x, y that is within the d_limit
    const auto curr_pos = curr_ins.pos;
    Instance next_ins;
    if (d_limit_ >= max_dim_) {
        auto[start_index, end_index] = instance_type_index_[blk_type];
        next_ins = instances_[detail_rand_.uniform<uint64_t>(start_index,
                                                                  end_index)];
    } else {
        int r = (int)(d_limit_ / 2);
        r = r > 0 ? r : 1;
        const int x_start = CLAMP(curr_pos.x - r, 0, max_dim_);
        const int x_end = CLAMP(curr_pos.x + r, 0, max_dim_);
        const int y_start = CLAMP(curr_pos.y - r, 0, max_dim_);
        const int y_end = CLAMP(curr_pos.y + r, 0, max_dim_);
        const int next_x = detail_rand_.uniform(x_start, x_end);
        const int next_y = detail_rand_.uniform(y_start, y_end);
        const auto pos = std::make_pair(next_x, next_y);
        if (loc_instances_[blk_type].find(pos)
            == loc_instances_[blk_type].end())
            return;

        const int id = loc_instances_[blk_type][pos];
        next_ins = instances_[id];
    }

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

void DetailedPlacer::anneal() {
    // the anneal schedule is different from VPR's because we want to
    // estimate the overall iterations
    sa_setup();
    tqdm bar;
    uint32_t total_swaps = estimate_num_swaps() * num_swap_;
    double temp = tmax;
    uint32_t current_swap = 0;
    while (temp >= tmin) {
        uint32_t accept = 0;
        for (uint32_t i = 0; i < num_swap_; i++) {
            move();
            double new_energy = energy();
            double de = new_energy - this->curr_energy;
            if (de == 0)
                continue;
            if (de > 0.0 && exp(-de / temp) < rand_.uniform<double>(0.0, 1.0)) {
                continue;
            } else {
                commit_changes();
                curr_energy = new_energy;
                accept++;
            }
        }

        // same schedule as estimation
        // 0.5
        if (temp == tmax) {
            temp /= 2;
        }
        // 0.9
        else if (temp >= tmax * 0.1) {
            temp *= 0.9;
        }
        // 0.95
        else if (temp >= tmax * 0.0001) {
            temp *= 0.95;
        }
        // 0.8
        else if (temp >= tmin) {
            temp *= 0.8;
        }

        bar.progress(current_swap++, total_swaps);

        double r_accept = (double)accept / num_swap_;
        d_limit_ = d_limit_ * (1 - 0.44 + r_accept);
        d_limit_ = CLAMP(d_limit_, 1, max_dim_);
    }
    bar.finish();
}

void DetailedPlacer::sa_setup() {
    if (num_swap_ != 0)
        return;
    // assume we have obtained the random placement
    // obtained the initial temperature
    auto diff_e = vector<double>(num_blocks_);
    for (uint32_t i = 0; i < num_blocks_; i++) {
        moves_.clear();
        move();
        auto new_e = energy();
        diff_e[i] = new_e;
    }
    // calculate the std dev
    double mean = 0;
    for (auto const e : diff_e)
        mean += e;
    mean /= num_blocks_;
    double diff_sum = 0;
    for (auto const e: diff_e)
        diff_sum += (e - mean) * (e - mean);
    tmax = sqrt(diff_sum / (num_blocks_ + 1)) * 20;
    num_swap_ = static_cast<uint32_t>(10 * pow(num_blocks_, 1.33));
    tmin = 0.005 * curr_energy / netlist_.size();

    // very very rare cases
    if (tmax <= tmin) {
        cerr << "Unable to determine tmax. Use default temperature\n";
        tmax = 3000;
    }
}

double DetailedPlacer::estimate() {
    sa_setup();

    double swap_time = SimAnneal::estimate(num_swap_);
    uint32_t num_swaps = estimate_num_swaps();

    return swap_time * num_swaps;
}

uint32_t DetailedPlacer::estimate_num_swaps() const {
    uint32_t num_swaps = 0;
    auto temp = tmax;
    // 0.5
    temp /= 2;
    num_swaps++;
    // 0.9
    while (temp >= tmax * 0.1) {
        temp *= 0.9;
        num_swaps++;
    }
    // 0.95
    while (temp >= tmax * 0.0002) {
        temp *= 0.95;
        num_swaps++;
    }
    // 0.8
    while (temp >= tmin) {
        temp *= 0.8;
        num_swaps++;
    }
    return num_swaps;
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
    for (const auto &move : moves_) {
        auto new_pos = std::make_pair(move.new_pos.x, move.new_pos.y);
        const char blk_type = instances_[move.blk_id].name[0];
        loc_instances_[blk_type][new_pos] = move.blk_id;

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

void DetailedPlacer::refine(int num_iter, double threshold,
                          bool print_improvement) {
    d_limit_ = sqrt(max_dim_) * 2;
    SimAnneal::refine(num_iter, threshold, print_improvement);
}