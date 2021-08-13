#ifndef CYCLONE_TIMING_HH
#define CYCLONE_TIMING_HH

#include "net.hh"
#include "route.hh"
#include "graph.hh"
#include "layout.hh"

#include <unordered_map>

struct TimingNode;

enum class TimingCost {
    CLB_OP,
    MEM,
    CLB_SB,
    MEM_SB,
    RMUX,
    REG
};


inline std::unordered_map<TimingCost, uint64_t> get_default_timing_info() {
    return {{TimingCost::CLB_OP, 1000},
            {TimingCost::MEM,    0},
            {TimingCost::CLB_SB, 200},
            {TimingCost::MEM_SB, 300},
            {TimingCost::RMUX,   10},
            {TimingCost::REG,    0}};
}


class TimingAnalysis {
public:
    explicit TimingAnalysis(Router &router) : router_(router) {}

    void set_timing_cost(const std::unordered_map<TimingCost, uint64_t> &timing_cost) { timing_cost_ = timing_cost; }

    uint64_t retime();
    void set_layout(const std::string &path);
    void set_minimum_frequency(uint64_t f) { min_frequency_ = f; }

private:
    Router &router_;
    Layout layout_;
    uint64_t min_frequency_ = 200;

    std::unordered_map<TimingCost, uint64_t> timing_cost_;

    uint64_t get_delay(const Node *node);
    uint64_t maximum_delay() const;
};


#endif //CYCLONE_TIMING_HH
