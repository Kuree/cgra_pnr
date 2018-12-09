#include <limits>
#include "global.hh"
#include "util.hh"

using std::map;
using std::shared_ptr;
using std::vector;
using std::set;
using std::pair;
using std::runtime_error;
using std::string;
using std::function;
using std::move;

// routing strategy
enum class RoutingStrategy {
    DelayDriven,
    CongestionDriven
};

void GlobalRouter::route() {
    // the actual routing part
    // algorithm based on PathFinder with modification for CGRA architecture
    // TODO:
    // make it domain-specific

    // 1. reorder the nets so that nets with register sinks are routed
    //    first to determine the register position at each iteration. this is
    //    fine since the relative ordering of these two groups (with and
    //    and without) doesn't matter
    // 2. calculate the slack ratio to determine what kind od routing algorithm
    //    to use. either RSMT or shortest-path for each pin pairs
    // 3. actually perform iterations (described in PathFiner)

    group_reg_nets();
    reorder_reg_nets();

    for (uint32_t it = 0; it < num_iteration_; it++) {
        fail_count_ = 0;
        // update the slack ratio table
        compute_slack_ratio(it);

        for (auto &net : netlist_) {
            route_net(net, it);
        }

        // clear the routing resources, i.e. rip up all the nets
        clear_connections();
        // assign to the routing resource
        assign_nets();

        if (!overflow()) {
            return;
        }

    }
    if (overflow())
        throw ::runtime_error("unable to route. sorry!");
}

void GlobalRouter::compute_slack_ratio(uint32_t current_iter) {
    // Note
    // this is slightly different from the PathFinder
    // here we compute slack ratio for each pin pair, rather than for every
    // possible routable node pair. this reduces the computation intensity
    // significantly.
    if (current_iter == 0) {
        // all timing-driven first thus 1 for every routing pair
        // also notice that for pins that haven't got assigned, this is
        // fine since nullptr will be entered into the ratio, which really
        // doesn't matter since everything is 1
        for (auto &net : netlist_) {
            // FIXME
            // refactor the net to distinguish the source and sinks
            const auto &src = net[0].node;
            for (uint32_t i = 1; i < net.size(); i++) {
                auto const &sink = net[i].node;
                slack_ratio_[{src, sink}] = 1;
            }
        }
    } else {
        // Note:
        // Keyi:
        // This is a little bit different from the original path finder
        // we also calculate the min delay to normalize the slack ratio
        // there fore A_n is actually \in [0, 1]
        // traverse the segments to find the actual delay
        double max_delay = 0;
        double min_delay = std::numeric_limits<double>::max();
        for (auto &net : netlist_) {
            const auto &src = net[0].node;
            const auto &segments = current_routes[net.id];
            if (src == nullptr)
                throw ::runtime_error("unable to find src when compute slack"
                                      "ratio");
            for (uint32_t i = 1; i < net.size(); i++) {
                auto const &sink = net[i].node;
                // find the routes
                if (sink == nullptr)
                    throw ::runtime_error("unable to find sink when compute"
                                          "slack ratio");
                auto const &route = segments.at(sink);
                double delay = 0;
                for (const auto &node : route) {
                    delay += node->delay;
                }
                slack_ratio_[{src, sink}] = delay;
                if (delay > max_delay)
                    max_delay = delay;
                if (delay < min_delay)
                    min_delay = delay;
            }
        }
        // normalize
        max_delay -= min_delay;
        if (max_delay != 0) {
            for (auto &iter : slack_ratio_)
                slack_ratio_[iter.first] =
                        (iter.second - min_delay) / max_delay;
        } else {
            // every net has the same delay
            for (auto &iter : slack_ratio_)
                slack_ratio_[iter.first] = 1;
        }
    }
}

void
GlobalRouter::route_net(Net &net, uint32_t it) {
    const auto &src = net[0].node;
    if (src == nullptr)
        throw ::runtime_error("unable to find src when route net");
    ::vector<::shared_ptr<Node>> current_path;
    for (uint32_t i = 1; i < net.size(); i++) {
        auto const &sink_node = net[i];
        auto slack = slack_ratio_.at({src, sink_node.node});
        RoutingStrategy strategy = slack > route_strategy_ratio ?
                                   RoutingStrategy::DelayDriven :
                                   RoutingStrategy::CongestionDriven;
        ::shared_ptr<Node> src_node = src;
        // choose src_node
        if (strategy == RoutingStrategy::CongestionDriven
            && !current_path.empty()) {
            // find the closest point
            uint32_t min_dist = manhattan_distance(src_node, sink_node.node);
            for (uint32_t p = 1; p < current_path.size(); p++) {
                if (manhattan_distance(current_path[p], sink_node.node)
                    < min_dist) {
                    src_node = current_path[p];
                }
            }
        }
        auto cost_f = create_cost_function(src, sink_node.node);
        // find the routes
        if (sink_node.name[0] == 'r') {
            ::pair<uint32_t, uint32_t> end = {sink_node.x, sink_node.y};
            if (it != 0 && sink_node.node == nullptr) {
                // previous attempts have failed;
                // don't clear the previous routing table so that it will
                // increase the cost function to re-use the same route.
                // FIXME: remove failed count
                fail_count_++;
                continue;
            }
            // based on the slack ratio, we choose which one to start

            auto segment = route_a_star(src_node, end, cost_f);
            ::shared_ptr<Node> end_node = segment.back();
            // then route for nearest
            auto reg_segment = route_a_star(end_node, end_reg_f, cost_f,
                                            zero_estimate);
            auto reg_node = reg_segment.back();
            // make sure it's an reg node
            if (reg_node == nullptr || reg_node->type != NodeType::Register)
                throw ::runtime_error("unable to route for net id " + net.name);
            // assign register locations across all grouped nets
            net[i].node = reg_node;
            for (auto &net_id: reg_nets_.at(net.id)) {
                netlist_[net_id][0].node = reg_node;
            }
            // add it to the segment
            segment.insert(segment.end(), reg_segment.begin() + 1,
                           reg_segment.end());
            // store the segment
            current_routes[net.id][sink_node.node] = segment;
        } else {
            if (sink_node.node == nullptr)
                throw ::runtime_error("unable to find node for block"
                                      " " + sink_node.name);
            auto segment = route_a_star(src_node, sink_node.node, cost_f);
            if (segment.back() != sink_node.node) {
                fail_count_++;
                continue;
            }
            current_routes[net.id][sink_node.node] = segment;
        }
        // also put segment into the current path
        const auto &segment = current_routes[net.id][sink_node.node];
        current_path.insert(current_path.end(), segment.begin(), segment.end());
    }
}

::function<uint32_t(const ::shared_ptr<Node> &, const ::shared_ptr<Node> &)>
GlobalRouter::create_cost_function(const ::shared_ptr<Node> &n1,
                                   const ::shared_ptr<Node> &n2) {
    return [&](const ::shared_ptr<Node> &node1,
               const ::shared_ptr<Node> &node2) -> uint32_t {
        // based of the PathFinder paper
        auto pn = get_presence_cost(node1, node2, OUT);
        pn += get_presence_cost(node2, node1, IN);
        auto dn = node1->get_edge_cost(node2);
        auto hn = get_history_cost(node1, node2);
        auto an = slack_ratio_.at({n1, n2});
        return static_cast<uint32_t>(an * dn + (1 - an) * (dn + hn) * pn);
    };
}

GlobalRouter::GlobalRouter(uint32_t num_iteration, const RoutingGraph &g) :
    Router(g), num_iteration_(num_iteration) {}
