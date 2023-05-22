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
                                    ::move(available_pos),
                                    ::move(fixed_pos), clb_type, fold_reg) {}

void VPRPlacer::anneal() {
    auto temp = tmax;
    curr_energy = init_energy();
    // anneal loop
    while (temp >= 0.005 * curr_energy / netlist_.size()) {
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
        double r_accept = (double)accept / num_swap_;
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
               curr_energy, temp, r_accept, alpha, d_limit_ / max_dim_);
        temp *= alpha;
        d_limit_ = d_limit_ * (1 - 0.44 + r_accept);
        d_limit_ = CLAMP(d_limit_, 1, max_dim_);
    }
}