#include "timing.hh"
#include "thunder_io.hh"
#include "io.hh"
#include <unordered_set>

#include <queue>

using Netlist = std::map<int, const Net*>;

std::vector<std::pair<int, const Pin *>> get_source_pins(const std::map<int, const Net*> &netlist) {
    std::vector<std::pair<int, const Pin *>> result;
    // any pin that has I as the name is an IO pin
    for (auto const &[net_id, net]: netlist) {
        auto const &p = (*net)[0];
        if (p.name[0] == 'i' || p.name[0] == 'I') {
            result.emplace_back(std::make_pair(net->id, &p));
        }
    }
    return result;
}

// simple graph to topological sort and figure out the timing
struct TimingNode {
    std::string name;
    std::vector<const Pin *> src_pins;
    std::vector<const Pin *> sink_pins;
    std::vector<TimingNode *> next;
};

class TimingGraph {
public:
    explicit TimingGraph(const Netlist &netlist) : netlist_(netlist) {
        for (auto const &[net_id, net]: netlist) {
            auto const &src_pin = (*net)[0];
            auto *src_node = get_node(src_pin);
            src_node->sink_pins.emplace_back(&src_pin);
            for (uint64_t i = 1; i < net->size(); i++) {
                auto const &sink = (*net)[i];
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
        for (auto const &[net_id, net]: netlist_) {
            if ((*net)[0].name == node->name) {
                result.emplace_back(net->id);
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
            node_ptr->name = name;
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
    for (auto const &[net_id, net]: netlist) {
        auto const &src = (*net)[0];
        if (src.x == pin.x && src.y == pin.y && src.name[0] != 'r') {
            // it's placed on the same tile, but it's not a pipeline register
            result.emplace(&src);
        }
    }

    return result;
}

std::unordered_map<const Node *, const TimingNode *>
get_timing_node_mapping(const std::vector<const TimingNode *> &nodes) {
    std::unordered_map<const Node *, const TimingNode *> result;
    for (auto const *node: nodes) {
        for (auto const *src: node->src_pins) {
            result.emplace(src->node.get(), node);
        }
        for (auto const *sink: node->sink_pins) {
            result.emplace(sink->node.get(), node);
        }
    }

    return result;
}


uint64_t get_max_wave_number(const std::unordered_map<const Pin *, uint64_t> &pin_wave) {
    uint64_t result = 0;
    for (auto const &iter: pin_wave) {
        if (iter.second > result)
            result = iter.second;
    }

    return result;
}

[[nodiscard]] uint64_t wave_matching(std::unordered_map<int, RoutedGraph> &routed_graphs,
                                     const std::unordered_map<const Pin *, int> &pin_src_net,
                                     const std::vector<const Pin *> &src_pins,
                   std::unordered_map<const Pin *, uint64_t> &pin_wave) {
    // gather the pin wave information
    uint64_t max_wave = 0;
    std::unordered_map<const Pin *, uint64_t> waves;
    std::unordered_map<const Pin *, const Pin *> pin_map;
    for (auto const *pin: src_pins) {
        auto w = pin_wave.at(pin);
        pin_map.emplace(pin, pin);
        waves.emplace(pin, w);
        if (w > max_wave) {
            max_wave = w;
        }
    }

    bool match;
    do {
        match = false;
        for (auto *pin: src_pins) {
            auto w = pin_wave.at(pin);
            if (w < max_wave) {
                // get routed graph
                int net_id = pin_src_net.at(pin);
                auto &routed_graph = routed_graphs.at(net_id);
                // need to pipeline this pin
                auto pins = routed_graph.insert_pipeline_reg(pin);
                for (auto pin_id: pins) {
                    auto const *p = pin_map.at(pin_id);
                    pin_wave[p]++;
                    waves[p] = pin_wave[p];
                }
                break;
            }
        }
        match = true;
        for (auto const &iter: waves) {
            if (iter.second < max_wave) {
                match = false;
                break;
            }
        }

    } while (!match);
    return max_wave;
}

uint64_t TimingAnalysis::recompute_pin_delay(const std::unordered_map<int, RoutedGraph> &routed_graphs,
                                             const std::unordered_map<const Pin *, int> &pin_src_net,
                                             const std::vector<const Pin *> &src_pins,
                                             const std::unordered_map<const Pin *, uint64_t> &pin_delay,
                                             const std::unordered_map<const Node *, const Pin *> &node_to_pin) const {
    std::vector<uint64_t> delays;
    delays.reserve(src_pins.size());

    for (auto const *pin: src_pins) {
        auto net_id = pin_src_net.at(pin);
        auto const &routed_graph = routed_graphs.at(net_id);
        auto route = routed_graph.get_sink_to_src_route(pin);

        uint64_t delay = 0;
        bool has_reg = false;
        for (auto const &node: route) {
            if (node->type == NodeType::Register) {
                has_reg = true;
                break;
            }
            delay += get_delay(node.get());
        }
        if (!has_reg) {
            // need to use the end node delay as well
            auto end_node = route.back().get();
            auto end_pin = node_to_pin.at(end_node);
            auto d = pin_delay.at(end_pin);
            delay += d;
        }

        delays.emplace_back(delay);

    }

    uint64_t delay = 0;
    for (auto d: delays) {
        if (d > delay) delay = d;
    }
    return delay;
}

uint64_t TimingAnalysis::retime() {
    std::map<int, const Net*> netlist;
    std::unordered_map<int, RoutedGraph> routed_graphs;
    for (auto const &iter: routers_) {
        auto const &nets = iter.second->get_netlist();
        for (auto const &[id, net]: nets) {
            netlist.emplace(id, &net);
        }
    }
    for (auto const &iter: routers_) {
        auto const &g = iter.second->get_routed_graph();
        for (auto const &entry: g) {
            routed_graphs.emplace(entry);
        }
    }

    auto io_pins = get_source_pins(netlist);
    auto allowed_delay = maximum_delay();

    std::unordered_map<const Pin *, uint64_t> pin_delay_;
    std::unordered_map<const TimingNode *, uint64_t> node_delay_;
    std::unordered_map<const Pin *, uint64_t> pin_wave_;
    std::unordered_map<const Node *, const Pin *> node_to_pin;
    std::unordered_map<const Pin *, int> pin_src_net_;

    for (auto const &[id, pin]: io_pins) {
        pin_wave_.emplace(pin, 0);
        pin_delay_.emplace(pin, 0);
    }

    for (auto const &[net_id, net]: netlist) {
        for (auto const &pin: *net) {
            node_to_pin.emplace(pin.node.get(), &pin);
        }
        for (auto i = 1u; i < net->size(); i++) {
            pin_src_net_.emplace(&(*net)[i], net_id);
        }
    }

    const TimingGraph timing_graph(netlist);

    auto nodes = timing_graph.topological_sort();
    auto timing_node_mapping = get_timing_node_mapping(nodes);
    std::map<int, std::map<uint32_t, std::vector<std::shared_ptr<Node>>>> final_result;

    // start STA on each node
    for (auto const *timing_node: nodes) {
        // the delay table is already calculated after the input, i.e., we don't consider the src pin
        // delay
        std::cout << "Timing at " << timing_node->name << std::endl;
        uint64_t start_delay = node_delay_[timing_node];
        auto sink_net_ids = timing_graph.get_sink_ids(timing_node);
        for (auto const net_id: sink_net_ids) {
            auto const &net = netlist[net_id];

            // all its source pins have to be available
            auto const &src_pins = timing_node->src_pins;
            uint64_t max_delay = start_delay;
            std::unordered_set<uint64_t> pin_waves;
            // if it's not registered element, we need to compute
            // the source pin delays, otherwise it's 0
            for (auto const *src_pin: src_pins) {
                // gather the pin information
                if (pin_wave_.find(src_pin) == pin_wave_.end()) {
                    throw std::runtime_error("Unable to find wave number for " + src_pin->name);
                }

                pin_waves.emplace(pin_wave_.at(src_pin));

                if (timing_node->name[0] == 'p') {
                    if (pin_delay_.find(src_pin) == pin_delay_.end()) {
                        throw std::runtime_error("Unable to find pin delay for " + src_pin->name);
                    }
                    if (pin_delay_.at(src_pin) > max_delay) {
                        max_delay = pin_delay_.at(src_pin);
                    }
                }
            }
            auto const &sink_pins = timing_node->sink_pins;
            for (auto const *sink_pin: sink_pins) {
                // use max delay for all sink pins, since we already calculated the delay through src pins
                pin_delay_[sink_pin] = max_delay;
            }
            // we assume at this point the pin data waves should be matched
            uint64_t src_wave;
            if (pin_waves.empty()) {
                src_wave = 0;
            }
            else if (pin_waves.size() != 1) {
                // if the pin waves doesn't match, we have to insert extra ones to those that lack of it
                src_wave = wave_matching(routed_graphs, pin_src_net_, src_pins, pin_wave_);
                // then we need to recalculate the delay since all register information is changed
                max_delay = recompute_pin_delay(routed_graphs, pin_src_net_, src_pins, pin_delay_, node_to_pin);
            } else {
                src_wave = *pin_waves.begin();
            }

            // now we need to compute the delay for each node
            auto &routed_graph = routed_graphs.at(net->id);
            auto const *source_node = (*net)[0].node.get();
            std::unordered_map<const Node *, uint64_t> node_delay = {{source_node, max_delay}};
            bool updated;
            std::unordered_set<Node *> inserted_node;
            do {
                updated = false;
                auto segments = routed_graph.get_route();
                auto pin_order = routed_graph.pin_order(segments);
                for (auto pin_id: pin_order) {
                    auto const segment = segments.at(pin_id);
                    uint64_t num_reg = 0;
                    for (uint64_t i = 1; i < segment.size(); i++) {
                        auto const current_node = segment[i];
                        auto const pre_node = segment[i - 1];
                        if (node_delay.find(pre_node.get()) == node_delay.end()) {
                            throw std::runtime_error("Unable to find delay for node " + pre_node->name);
                        }
                        auto delay = node_delay.at(pre_node.get());
                        // if the original sink pin is a register, don't count the wave
                        if (current_node->type == NodeType::Register && i != (segment.size() - 1)) {
                            // reset the delay
                            delay = 0;
                            node_delay[current_node.get()] = 0;
                            num_reg++;
                        } else {
                            delay += get_delay(current_node.get());
                        }

                        // if the delay is more than we can handle, we need to insert the pipeline registers
                        if (delay > allowed_delay && inserted_node.find(current_node.get()) == inserted_node.end()) {
                            // need to pipeline register it
                            auto pins = routed_graph.insert_reg_output(current_node, true);
                            // those are pins affected
                            updated = true;
                            if (pins.empty()) {
                                throw std::runtime_error("Failed to insert pipeline register at " + current_node->name);
                            }
                            num_reg++;
                            // need to update the wave number
                            auto const pin_node = segment.back();
                            auto const *pin = node_to_pin.at(pin_node.get());
                            pin_wave_[pin] = src_wave + num_reg;
                            // reset the node delay
                            node_delay = {{source_node, max_delay}};
                            inserted_node.emplace(current_node.get());
                            break;
                        } else {
                            // insert updated timing
                            node_delay[current_node.get()] = delay;
                            // use the same pin wave
                            auto const pin_node = segment.back();
                            auto const *pin = node_to_pin.at(pin_node.get());
                            pin_wave_[pin] = src_wave + num_reg;
                            pin_delay_[pin] = delay;
                        }
                    }
                    // redo all the work
                    if (updated) break;
                }
            } while (updated);
            // update the delay
            for (auto const *next_timing_node: timing_node->next) {
                if (next_timing_node->name[0] != 'p') {
                    // delay is 0
                    node_delay_[next_timing_node] = 0;
                } else {
                    auto const &source_pins = next_timing_node->src_pins;
                    for (auto const *src_pin : source_pins) {
                        auto const *pin_node = src_pin->node.get();
                        if (node_delay.find(pin_node) != node_delay.end()) {
                            auto d = node_delay.at(pin_node);
                            if (node_delay_[next_timing_node] != d) {
                                node_delay_[next_timing_node] = d;
                            }
                        }
                    }
                }
            }
        }
    }

    for (auto const &[net_id, g]: routed_graphs) {
        auto segments = g.get_route();
        final_result.emplace(net_id, segments);
    }

    // reassemble the result
    for (auto const &iter: routers_) {
        std::map<int, std::map<uint32_t, std::vector<std::shared_ptr<Node>>>> router_result;
        auto &router = *iter.second;
        for (auto const &[net_id, routes]: final_result) {
            if (router.has_net(net_id)) {
                router_result.emplace(net_id, routes);
            }
        }
        router.set_current_routes(router_result);
    }

    auto r = get_max_wave_number(pin_wave_);
    for (auto const &[pin, w]: pin_wave_) {
        if (node_waves_.find(pin->name) == node_waves_.end()) {
            node_waves_.emplace(pin->name, w);
        }
    }
    return r;
}

void TimingAnalysis::adjust_pipeline_registers() {
    // compute for each pin's timing and then figure out if we can move the
    // pin's associated pipeline registers
    std::map<int, const Net *> netlist;
    std::unordered_map<int, RoutedGraph> routed_graphs;
    for (auto const &iter: routers_) {
        auto const &nets = iter.second->get_netlist();
        for (auto const &[id, net]: nets) {
            netlist.emplace(id, &net);
        }
    }
    for (auto const &iter: routers_) {
        auto const &g = iter.second->get_routed_graph();
        for (auto const &entry: g) {
            routed_graphs.emplace(entry);
        }
    }

    auto io_pins = get_source_pins(netlist);

    std::unordered_map<const Pin *, uint64_t> pin_delay_;
    std::unordered_map<const TimingNode *, uint64_t> node_delay_;
    std::unordered_map<const Node *, const Pin *> node_to_pin;
    std::unordered_map<const Pin *, int> pin_src_net_;
    std::unordered_map<const Pin*, int> pin_sink_net_;

    for (auto const &[id, pin]: io_pins) {
        pin_delay_.emplace(pin, 0);
    }

    for (auto const &[net_id, net]: netlist) {
        for (auto const &pin: *net) {
            node_to_pin.emplace(pin.node.get(), &pin);
        }
        for (auto i = 1u; i < net->size(); i++) {
            pin_src_net_.emplace(&(*net)[i], net_id);
        }
        pin_sink_net_.emplace(&(*net)[0], net_id);
    }

    const TimingGraph timing_graph(netlist);

    auto nodes = timing_graph.topological_sort();
    auto timing_node_mapping = get_timing_node_mapping(nodes);

    // we go through two passes
    // the first pass compute the timing and figure out which nets
    // can be adjusted. the second pass is to adjust the nets

    std::set<std::pair<int, int>> target_nets;

    // compute timing
    for (auto const *node: nodes) {
        uint64_t max_delay = 0;
        for (auto const *src_pin: node->src_pins) {
            auto delay = pin_delay_.at(src_pin);
            if (delay > max_delay) {
                max_delay = delay;
            }
        }
        node_delay_.emplace(node, max_delay);
        // compute the route to the sinks and update the delay
        // notice that if the timing node is registered, it doesn't have delay in the output
        // registered elements doesn't have delay
        auto node_type = node->name[0];
        if (node_type == 'm' || node_type == 'r') {
            max_delay = 0;
        }
        // walk through the routed net and compute timing
        std::unordered_map<const Node *, uint64_t> route_node_delay;
        uint64_t num_sinks = 0;
        for (auto const *pin: node->sink_pins) {
            route_node_delay.emplace(pin->node.get(), max_delay);
            auto net_id = pin_sink_net_.at(pin);
            auto const &routed = routed_graphs.at(net_id);

            auto segments = routed.get_route();
            auto pin_order = routed.pin_order(segments);
            for (auto pin_id: pin_order) {
                auto const segment = segments.at(pin_id);
                num_sinks++;
                for (uint64_t i = 0; i < segment.size(); i++) {
                    auto r_node = segment[i];
                    auto d = get_delay(r_node.get());
                    auto current_delay = route_node_delay.at(r_node.get());
                    current_delay += d;
                    if (i == (segment.size() - 1)) {
                        // update the src pin info
                        auto const *src_pin = node_to_pin.at(r_node.get());
                        pin_delay_.emplace(src_pin, current_delay);
                    } else {
                        auto next_node = segment[i + 1];
                        route_node_delay.emplace(next_node.get(), current_delay);
                    }
                }
            }
        }

        // detect if we can move the register (src) or not
        // and if so, which is the connected route
        if (node_type == 'r') {
            // the sink has to be a non-register type, and we only have fan out one
            if (node->sink_pins.size() == 1 && num_sinks == 1) {
                auto *sink_pin = node->sink_pins.front();
                // we found one.
                // need to find out two nets. the current net, and it's source
                // since when we move the register, we also need to change the source net route
                auto source_net = pin_src_net_.at(node->src_pins[0]);
                auto current_net = pin_sink_net_.at(sink_pin);
                target_nets.emplace(std::make_pair(current_net, source_net));

            }
        }
    }

    // second pass
    for (auto const &[current_net, source_net]: target_nets) {
        // because register track is decided right away, the track might not be optimal,
        // so we move it down to ease the downstream slack
        // need to compute the current register timing and its sink timing
        // if the sink timing is larger than the current register timing, we can move it down
        // until they are about equal
        auto &current_routed_graph = routed_graphs.at(current_net);
        auto const &current_route = current_routed_graph.get_route().begin()->second;
        auto const *sink_pin = node_to_pin.at(current_route.back().get());
        auto const *target_pin = node_to_pin.at(current_route.front().get());
        auto current_delay = pin_delay_.at(sink_pin);
        // get the source delay from the previous net
        auto &source_routed_graph = routed_graphs.at(current_net);
        // need to get the source pin id
        const Pin *src_pin = nullptr;
        auto const &source_segments = source_routed_graph.get_route();
        for (auto const &[pin_id, segments]: source_segments) {
            auto const &sink_node = segments.back();
            auto const *pin = node_to_pin.at(sink_node.get());
            if (pin->name == target_pin->name) {
                src_pin = pin;
                break;
            }
        }
        if (!src_pin) {
            throw std::runtime_error("Unable to identify source net routed segment " + target_pin->name);
        }
        auto source_delay = pin_delay_.at(src_pin);
        // now we try to move down the routed graph until we balanced the slack
        uint64_t idx = 0;
        std::optional<uint64_t> reg_insertion;
        while (current_delay > source_delay) {
            auto *node = current_route[idx].get();
            if (node->name == sink_pin->name) {
                // can't do stuff anymore
                break;
            } else if (node->type == NodeType::SwitchBox) {
                auto *sb = reinterpret_cast<SwitchBoxNode*>(node);
                if (sb->io == SwitchBoxIO::SB_OUT) {
                    reg_insertion = idx;
                }
                idx++;
            } else {
                idx++;
            }
            auto delay = get_delay(node);
            current_delay -= delay;
            source_delay += delay;
        }

        // if reg insertion is set
        if (reg_insertion) {
            idx = *reg_insertion;
            // compute the new current segment
            std::shared_ptr<Node> target_reg_node = nullptr;
            {
                auto sb_out_internal = current_routed_graph.get_internal_node(current_route[idx]);
                auto rmux_internal = current_routed_graph.get_internal_node(current_route[idx + 1]);
                // cut the
                sb_out_internal->remove_edge(rmux_internal);
                // need to find that register node
                for (auto const &n: *current_route[idx]) {
                    auto const &node = n.lock();
                    if (node->type == NodeType::Register) {
                        target_reg_node = node;
                        break;
                    }
                }
                if (target_reg_node == nullptr) {
                    throw std::runtime_error("Unable to find regiter node");
                }
                current_routed_graph.connect(target_reg_node, current_route[idx + 1]);
            }
            // need to modify the source net
            {
                // node that this is the reversed route
                auto const &source_route_reversed = source_routed_graph.get_sink_to_src_route(src_pin);
                auto const &reg_node = source_route_reversed[0];
                auto const &rmux = source_route_reversed[1];
                source_routed_graph.remove_connection(rmux, reg_node);
                // now we add connections until the idx
                std::shared_ptr<Node> pre_node = rmux;
                // starting from 1 to skipp the reg
                for (uint64_t i = 1; i <= idx; i++) {
                    auto node = current_route[i];
                    source_routed_graph.connect(pre_node, node);
                    pre_node = node;
                }
                // then connect it to the reg node
                source_routed_graph.connect(pre_node, target_reg_node);
            }

            for (auto const &iter: routers_) {
                auto routes = source_routed_graph.get_route();
                iter.second->update_net_route(source_net, routes);
                routes = current_routed_graph.get_route();
                iter.second->update_net_route(current_net, routes);
            }
        }
    }

}

void TimingAnalysis::set_layout(const std::string &path) {
    layout_ = load_layout(path);
}

uint64_t TimingAnalysis::get_delay(const Node *node) const {
    switch (node->type) {
        case NodeType::Port: {
            auto clb_type = layout_.get_blk_type(node->x, node->y);
            switch (clb_type) {
                case 'p':
                    return timing_cost_.at(TimingCost::CLB_OP);
                case 'm':
                    // assume memory is registered
                    return timing_cost_.at(TimingCost::MEM);
                case 'i':
                case 'I': return 0;
                default:
                    throw std::runtime_error("Unable to identify delay for node: " + node->name);
            }
        }
        case NodeType::Register: {
            return timing_cost_.at(TimingCost::REG);
        }
        case NodeType::SwitchBox: {
            // need to determine if it's input or output, and the location
            auto *sb = reinterpret_cast<const SwitchBoxNode *>(node);
            if (sb->io == SwitchBoxIO::SB_IN) {
                return 0;
            } else {
                // need to figure out the tile type
                auto clb_type = layout_.get_blk_type(node->x, node->y);
                switch (clb_type) {
                    case 'p':
                        return timing_cost_.at(TimingCost::CLB_SB);
                    case 'm':
                        return timing_cost_.at(TimingCost::MEM_SB);
                    case 'i':
                        return 0;
                    default:
                        throw std::runtime_error("Unable to identify timing for blk " + node->name);
                }
            }
        }
        case NodeType::Generic: {
            return timing_cost_.at(TimingCost::RMUX);
        }
        default:
            throw std::runtime_error("Unable to identify node to compute delay");
    }
}

uint64_t TimingAnalysis::maximum_delay() const {
    // the frequency is in mhz
    auto ns = 1'000'000 / min_frequency_;
    return ns;
}

void TimingAnalysis::save_wave_info(const std::string &filename) {
    dump_wave_info(node_waves_, filename);
}
