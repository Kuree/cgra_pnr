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
    explicit TimingAnalysis(const std::map<uint32_t, std::unique_ptr<Router>> &routers) : routers_(routers) {}

    void set_timing_cost(const std::unordered_map<TimingCost, uint64_t> &timing_cost) { timing_cost_ = timing_cost; }

    uint64_t retime();

    void adjust_pipeline_registers();

    void set_layout(const std::string &path);

    void set_minimum_frequency(uint64_t f) { min_frequency_ = f; }

    void save_wave_info(const std::string &filename);

private:
    const std::map<uint32_t, std::unique_ptr<Router>> &routers_;
    Layout layout_;
    uint64_t min_frequency_ = 200;

    std::unordered_map<TimingCost, uint64_t> timing_cost_;
    std::map<std::string, uint64_t> node_waves_;

    uint64_t get_delay(const Node *node) const;

    uint64_t maximum_delay() const;

    uint64_t recompute_pin_delay(const std::unordered_map<int, RoutedGraph> &routed_graphs,
                                 const std::unordered_map<const Pin *, int> &pin_src_net,
                                 const std::vector<const Pin *> &src_pins,
                                 const std::unordered_map<const Pin *, uint64_t> &pin_delay,
                                 const std::unordered_map<const Node *, const Pin *> &node_to_pin) const;
};


#endif //CYCLONE_TIMING_HH
