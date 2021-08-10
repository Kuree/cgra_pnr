#ifndef CYCLONE_TIMING_HH
#define CYCLONE_TIMING_HH

#include "net.hh"
#include "route.hh"
#include "graph.hh"

#include <unordered_map>

enum class TimingCost {
    CLB_OP,
    MEM,
    CLB_SB,
    MEM_SB,
    RMUX
};


std::unordered_map<TimingCost, uint64_t> get_default_timing_info() {
    return {{TimingCost::CLB_OP, 1000},
            {TimingCost::MEM,    0},
            {TimingCost::CLB_SB, 200},
            {TimingCost::MEM_SB, 300},
            {TimingCost::RMUX,   10}};
}


class TimingAnalysis {
public:
    explicit TimingAnalysis(const Router &router): router_(router) {}
    void set_timing_cost(const std::unordered_map<TimingCost, uint64_t> &timing_cost) { timing_cost_ = timing_cost; }

    void retime();

private:
    const Router &router_;

    std::unordered_map<TimingCost, uint64_t> timing_cost_;
};


#endif //CYCLONE_TIMING_HH
