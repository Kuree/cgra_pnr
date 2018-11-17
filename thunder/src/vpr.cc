#include <iostream>
#include "vpr.hh"


using std::move;
using std::vector;
using std::cerr;
using std::runtime_error;
using std::endl;

#define DEBUG 0
#define CLAMP(x, low, high)  (((x) > (high)) ? (high) : \
                             (((x) < (low)) ? (low) : (x)))


VPRPlacer::VPRPlacer(std::map<std::string, std::pair<int, int>> init_placement,
                     std::map<std::string, std::vector<std::string>> netlist,
                     std::map<char,
                             std::vector<std::pair<int, int>>> available_pos,
                     std::map<std::string, std::pair<int, int>> fixed_pos,
                     char clb_type, bool fold_reg) :
                     DetailedPlacer(::move(init_placement),
                                    ::move(netlist),
                                    available_pos,
                                    fixed_pos, clb_type, fold_reg),
                     loc_instances_() {
    // index to loc
    for (const auto &instance : instances_) {
        auto pos = instance.pos;
        const char blk_type = instance.name[0];
        if (loc_instances_.find(blk_type) == loc_instances_.end())
            loc_instances_[blk_type] = {};
        loc_instances_[blk_type].insert({{pos.x, pos.y}, instance.id});
    }

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
    max_dim_ = xmax > ymax? xmax : ymax;
    d_limit = max_dim_;
    num_blocks_ = (uint32_t)(instance_ids_.size() - fixed_pos.size());
}

void VPRPlacer::anneal() {
    // assume we have obtained the random placement
    // 1. obtained the initial temperature
    auto diff_e = ::vector<double>(num_blocks_);
    for (uint32_t i = 0; i < num_blocks_; i++) {
        this->moves_.clear();
        this->move();
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
    double temp = sqrt(diff_sum / (num_blocks_ + 1)) * 20;
    const double num_swap = 10 * pow(num_blocks_, 1.33);
    curr_energy = init_energy();
    // anneal loop
    while (temp >= 0.005 * curr_energy / netlist_.size()) {
        uint32_t accept = 0;
        for (uint32_t i = 0; i < num_swap; i++) {
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
        double r_accept = (double)accept / num_swap;
        double alpha = 0;
        if (r_accept > 0.96)
            alpha = 0.5;
        else if (r_accept > 0.8)
            alpha = 0.9;
        else if (r_accept > 0.15)
            alpha = 0.95;
        else
            alpha = 0.8;
        printf("Wirelength: %f T: %f r_accept: %f alpha: %f d_limit: %f%%\n",
               curr_energy, temp, r_accept, alpha, d_limit / max_dim_);
        temp *= alpha;
        d_limit = d_limit * (1 - 0.44 + r_accept);
        d_limit = CLAMP(d_limit, 1, max_dim_);
    }
}

void VPRPlacer::commit_changes() {
    for (const auto &move : moves_) {
        auto new_pos = std::make_pair(move.new_pos.x, move.new_pos.y);
        const char blk_type = instances_[move.blk_id].name[0];
        loc_instances_[blk_type][new_pos] = move.blk_id;
    }
    DetailedPlacer::commit_changes();
}

void VPRPlacer::move() {
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
    const char blk_type = curr_ins.name[0];

    // search for x, y that is within the d_limit
    const auto curr_pos = curr_ins.pos;
    Instance next_ins;
    // some optimizations
    if (d_limit >= max_dim_) {
        auto [start_index, end_index] = instance_type_index_[blk_type];
        next_ins = instances_[detail_rand_.uniform<uint64_t>(start_index,
                                                                  end_index)];
    } else {
        int r = (int)(d_limit / 2);
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