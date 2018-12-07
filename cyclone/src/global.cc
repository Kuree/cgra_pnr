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

    ::map<::pair<::shared_ptr<Node>, ::shared_ptr<Node>>, double> slack_ratio;

    for (uint32_t it = 0; it < num_iteration_; it++) {
        fail_count_ = 0;
        // update the slack ratio table
        compute_slack_ratio(slack_ratio, it);

        for (auto &net : netlist_) {
            route_net(net, it, slack_ratio);
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

void GlobalRouter::compute_slack_ratio(::map<::pair<::shared_ptr<Node>,
                                                    ::shared_ptr<Node>>,
                                             double> &ratio,
                                       uint32_t current_iter) {
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
                ratio[{src, sink}] = 1;
            }
        }
    } else {
        // traverse the segments to find the actual delay
        double max_delay = 0;
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
                ratio[{src, sink}] = delay;
                if (delay > max_delay)
                    max_delay = delay;
            }
        }
        // normalize
        for (auto &iter : ratio)
            iter.second = iter.second / max_delay;
    }
}

void
GlobalRouter::route_net(Net &net, uint32_t it,
                       const ::map<::pair<::shared_ptr<Node>,
                                          ::shared_ptr<Node>>,
                                   double> &slack_ratio) {
    const auto &src = net[0].node;
    if (src == nullptr)
        throw ::runtime_error("unable to find src when route net");
    for (uint32_t i = 1; i < net.size(); i++) {
        auto const &sink_node = net[i];
        auto slack = static_cast<uint32_t>(slack_ratio.at({src,
                                                           sink_node.node}));
        auto cost_f = create_cost_function(slack);
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
            auto segment = route_a_star(src, end, cost_f);
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
        } else {
            if (sink_node.node == nullptr)
                throw ::runtime_error("unable to find node for block"
                                      " " + sink_node.name);
            auto segment = route_a_star(src, sink_node.node, cost_f);
            if (segment.back() != sink_node.node) {
                fail_count_++;
                continue;
            }
            current_routes[net.id][sink_node.node] = segment;
        }
    }
}

::function<uint32_t(const ::shared_ptr<Node> &, const ::shared_ptr<Node> &)>
GlobalRouter::create_cost_function(uint32_t slack) {
    return [&](const ::shared_ptr<Node> &node1,
               const ::shared_ptr<Node> &node2) -> uint32_t {
        // based of the PathFinder paper
        auto pn = get_presence_cost(node1, node2, OUT);
        pn += get_presence_cost(node2, node1, IN);
        auto dn = node1->get_edge_cost(node2);
        auto hn = get_history_cost(node1, node2);
        auto an = slack;
        return an * dn + (1 - an) * (dn + hn) * pn;
    };
}

GlobalRouter::GlobalRouter(uint32_t num_iteration, const RoutingGraph &g) :
    Router(g), num_iteration_(num_iteration) {}
