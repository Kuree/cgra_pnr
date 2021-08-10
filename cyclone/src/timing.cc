#include "timing.hh"
#include <unordered_set>

#include <queue>

using Netlist = std::vector<Net>;

std::vector<std::pair<int, const Pin *>> get_source_pins(const std::vector<Net> &netlist) {
    std::vector<std::pair<int, const Pin *>> result;
    // any pin that has I as the name is an IO pin
    for (auto const &net: netlist) {
        auto const &p = net[0];
        if (p.name[0] == 'i' || p.name[0] == 'I') {
            result.emplace_back(std::make_pair(net.id, &p));
        }
    }
    return result;
}

// simple graph to topological sort and figure out the timing
struct TimingNode {
    std::string name;
    std::vector<const Pin *> src_pins;
    std::vector<TimingNode *> next;
};

class TimingGraph {
public:
    explicit TimingGraph(const Netlist &netlist): netlist_(netlist) {
        for (auto const &net: netlist) {
            auto const &src_pin = net[0];
            auto *src_node = get_node(src_pin);
            for (uint64_t i = 1; i < net.size(); i++) {
                auto const &sink = net[i];
                auto *sink_node = get_node(sink);
                src_node->next.emplace_back(sink_node);
                sink_node->src_pins.emplace_back(&sink);
            }
        }
    }

    std::vector<const TimingNode *> topological_sort() const {
        std::vector<const TimingNode *> result;
        std::unordered_set<const TimingNode *> visited;

        for (auto const &node: nodes_) {
            if (visited.find(node.get()) == visited.end()) {
                sort_(result, visited, node.get());
            }
        }

        std::reverse(result.begin(), result.end());
        return result;
    }

    std::vector<int> get_sink_ids(const TimingNode *node) const {
        std::vector<int> result;
        for (auto const *n: node->next) {
            for (auto const &net: netlist_) {
                if (net[0].name == node->name) {
                    result.emplace_back(net.id);
                }
            }
        }

        return result;
    }

private:
    const Netlist &netlist_;
    std::unordered_map<std::string, TimingNode *> name_to_node_;
    std::unordered_set<std::unique_ptr<TimingNode>> nodes_;

    TimingNode *get_node(const Pin &pin) {
        auto const &name = pin.name;
        if (name_to_node_.find(name) == name_to_node_.end()) {
            auto node_ptr = std::make_unique<TimingNode>();
            auto *ptr = node_ptr.get();
            nodes_.emplace(std::move(node_ptr));
            name_to_node_.emplace(name, ptr);
        }
        return name_to_node_.at(name);
    }

    void sort_(std::vector<const TimingNode *> &result, std::unordered_set<const TimingNode *> &visited,
               const TimingNode *node) const {
        visited.emplace(node);
        for (auto const *n: node->next) {
            if (visited.find(n) == visited.end()) {
                sort_(result, visited, n);
            }
        }
        result.emplace_back(node);
    }

};


std::unordered_set<const Pin *> get_sink_pins(const Pin &pin, const Netlist &netlist) {
    // brute-force search
    std::unordered_set<const Pin *> result;
    for (auto const &net: netlist) {
        auto const &src = net[0];
        if (src.x == pin.x && src.y == pin.y && src.name[0] != 'r') {
            // it's placed on the same tile, but it's not a pipeline register
            result.emplace(&src);
        }
    }

    return result;
}


void TimingAnalysis::retime() {
    auto const &netlist = router_.get_netlist();
    auto const routed_graphs = router_.get_routed_graph();

    auto io_pins = get_source_pins(netlist);

    std::unordered_map<const TimingNode *, uint64_t> node_delay_;
    std::unordered_map<const Pin *, uint64_t> pin_wave_;

    const TimingGraph timing_graph(netlist);

    auto nodes = timing_graph.topological_sort();
    std::map<std::string, std::vector<std::vector<std::shared_ptr<Node>>>> final_result;

    // start STA on each node
    for (auto const *timing_node: nodes) {
        // the delay table is already calculated after the input, i.e., we don't consider the src pin
        // delay
        uint64_t start_delay = node_delay_[timing_node];
        auto sink_net_ids = timing_graph.get_sink_ids(timing_node);
        for (auto const net_id: sink_net_ids) {
            auto const &net = netlist[net_id];
            auto const &routed_graph = routed_graphs.at(net.id);

            // need to time it based on the cost

            auto segments = routed_graph.get_route();
            final_result.emplace(net.name, segments);
        }
    }

}