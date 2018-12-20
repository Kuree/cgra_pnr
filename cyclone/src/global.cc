#include <limits>
#include <cmath>
#include <iostream>
#include <chrono>
#include <iomanip>
#include <ctime>
#include <queue>
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
using std::setw;

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
    auto reordered_netlist = reorder_reg_nets();

    for (uint32_t it = 0; it < num_iteration_; it++) {
        auto time_start = std::chrono::system_clock::now();

        std::cout << "Routing iteration: " << ::setw(3) << it;

        // update the slack ratio table
        compute_slack_ratio(it);
        overflowed_ = false;

        // clear the routing resources, i.e. rip up all the nets
        clear_connections();

        for (const auto &net_id : reordered_netlist) {
            route_net(netlist_[net_id], it);
        }

        // assign history table
        assign_history();

        auto time_end = std::chrono::system_clock::now();
        // compute the duration
        auto duration =
                std::chrono::duration_cast<
                        std::chrono::milliseconds>(time_end - time_start);
        std::cout << " duration: " << duration.count() << " ms" << std::endl;

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
            for (uint32_t seg_index = 1; seg_index < net.size(); seg_index++) {
                slack_ratio_[{net.id, seg_index}] = 1;
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
            for (uint32_t seg_index = 1; seg_index < net.size(); seg_index++) {
                auto const &sink = net[seg_index].node;
                // find the routes
                if (sink == nullptr)
                    throw ::runtime_error("unable to find sink when compute"
                                          "slack ratio");
                auto const &route = segments.at(sink);
                double delay = 0;
                for (const auto &node : route) {
                    delay += node->delay;
                }
                slack_ratio_[{net.id, seg_index}] = delay;
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
    auto pin_indices = reorder_pins(net);
    for (uint32_t pin_index = 0; pin_index < net.size(); pin_index++) {
        auto seg_index = pin_indices[pin_index];
        auto const &sink_node = net[seg_index];
        auto slack_entry = make_pair(src, sink_node.name);
        auto sink_coord = std::make_pair(sink_node.x, sink_node.y);
        double slack = slack_ratio_.at({net.id, seg_index});
        RoutingStrategy strategy = slack > route_strategy_ratio ?
                                   RoutingStrategy::DelayDriven :
                                   RoutingStrategy::CongestionDriven;
        ::shared_ptr<Node> src_node = src;
        // choose src_node
        if (strategy == RoutingStrategy::CongestionDriven
            && !current_path.empty()) {
            // find the closest point
            uint32_t min_dist = manhattan_distance(src_node, sink_coord);
            for (uint32_t p = 1; p < current_path.size(); p++) {
                const auto &node = current_path[p];
                const auto &pre_node = current_path[p - 1];
                const auto &conn = node_connections_.at(node);
                // break them into several parts so that it's easier to
                // read and modify
                if (node->type != NodeType::SwitchBox) {
                    // it has to be a switch box
                    continue;
                }
                // it can't be overflowed already
                if (conn.size() > 1) {
                    continue;
                }

                // also there exists one empty switch box it's connected
                bool empty = false;
                for (auto const &n : *node) {
                    const auto &conn_n = node_connections_.at(n);
                    if (n->type == NodeType::SwitchBox &&
                        (conn_n.empty() ||
                         (conn_n.size() == 1 &&
                          conn_n.find(pre_node) != conn_n.end()))) {
                        empty = true;
                        break;
                    }
                }
                if (!empty)
                    continue;
                if (manhattan_distance(node, sink_coord) < min_dist) {
                    src_node = node;
                }
            }
        }
        auto an = slack * slack_factor_;
        auto cost_f = create_cost_function(an, it);

        // find the routes
        if (sink_node.name[0] == 'r') {
            ::pair<uint32_t, uint32_t> end = {sink_node.x, sink_node.y};
            if (it != 0 && sink_node.node == nullptr) {
                throw ::runtime_error("iteration 0 failed to assign registers");
            }
            // for now just find the switch in and decides the register later
            /*
             * FIXME: in the future where the register is sparse, change this
             *        route to the register, then roll back to the switch in.
             *        in this way the router can handle both sparse and
             *        rich register resources.
            */
            auto end_f = get_free_switch(end);
            auto h_f = manhattan_distance(end);
            auto segment = route_a_star(src_node, end_f, cost_f, h_f);

            if (segment.back()->type != NodeType::SwitchBox) {
                throw ::runtime_error("cannot connect to the reg tile");
            }

            auto switch_node = segment.back();
            // make sure it's an reg node
            if (switch_node == nullptr)
                throw ::runtime_error("unable to route for net id " + net.name);
            if (switch_node->x != sink_node.x || switch_node->y != sink_node.y)
                throw ::runtime_error("error in assigning switch box for reg " +
                                      sink_node.name);
            // assign register locations across all grouped nets
            net[seg_index].node = switch_node;

            // assign pins to the downstream
            int reg_net_id = reg_net_src_.at(sink_node.name);
            netlist_[reg_net_id][0].node = switch_node;

            // store the segment
            current_routes[net.id][sink_node.node] = segment;

            // add some metadata information so that we can fix the reg net very
            // quickly later
            reg_net_table_.insert({reg_net_id, {net.id, sink_node.node}});

        } else {
            if (sink_node.node == nullptr)
                throw ::runtime_error("unable to find node for block"
                                      " " + sink_node.name);
            auto segment = route_a_star(src_node, sink_node.node, cost_f);
            if (segment.back() != sink_node.node) {
                throw ::runtime_error("unable to route to port " +
                                      sink_node.node->name);
            }
            current_routes[net.id][sink_node.node] = segment;
        }

        // fix the reg net
        if (net[0].name[0] == 'r') {
            if (pin_index != 0 && src->type != NodeType::SwitchBox) {
                throw ::runtime_error("failed to fix register net");
            } else if (pin_index == 0) {
                // we need to find an register along the path and fix it
                fix_register_net(net.id, net[seg_index]);
            }
        }

        // also put segment into the current path
        const auto &segment = current_routes[net.id][sink_node.node];
        current_path.insert(current_path.end(), segment.begin(), segment.end());
        // assign it to the node_connections
        assign_net_segment(segment);
    }
}

::function<double(const ::shared_ptr<Node> &, const ::shared_ptr<Node> &)>
GlobalRouter::create_cost_function(double an,
                                   uint32_t it) {
    return [&, an, it](const ::shared_ptr<Node> &node1,
               const ::shared_ptr<Node> &node2) -> double {
        // based of the PathFinder paper
        auto pn = get_presence_cost(node2, node1, it);
        auto dn = node1->get_edge_cost(node2);
        auto hn = get_history_cost(node2) * hn_factor_;

        auto result = an * dn + (1 - an) * (dn + hn) * pn;
        return result;
    };
}

GlobalRouter::GlobalRouter(uint32_t num_iteration, const RoutingGraph &g) :
    Router(g), num_iteration_(num_iteration), slack_ratio_()  {}

std::function<bool(const std::shared_ptr<Node> &)>
GlobalRouter::get_free_switch(const std::pair<uint32_t, uint32_t> &p) {
    return [&, p](const std::shared_ptr<Node> &node) -> bool {
        if (node == nullptr || node->type != NodeType::SwitchBox
            || node->x != p.first || node->y != p.second) {
            return false;
        }
        else {
            // see it's been used or not
            if (!node_connections_.at(node).empty())
                return false;
            // one of it's connections has to be free
            for (auto const &n : *node) {
                if (node_connections_.at(n).empty())
                    return true;
            }

            return false;
        }
    };
}

std::vector<uint32_t> GlobalRouter::reorder_pins(const Net &net) {
    ::vector<uint32_t> result(net.size());
    for (uint32_t i = 0; i < result.size(); i++)
        result[i] = i;

    // first based on distance
    auto src_pos = std::make_pair(net[0].x, net[0].y);
    const auto src_pin = &net[0];
    std::stable_sort(result.begin(), result.end(),
                     [&](uint32_t a, uint32_t b) -> bool {
        uint32_t dist_a = manhattan_distance({net[a].x, net[a].y}, src_pos);
        uint32_t dist_b = manhattan_distance({net[b].x, net[b].y}, src_pos);
        return dist_a < dist_b;
    });

    // the src should be the same
    if (src_pin != &net[result[0]])
        throw ::runtime_error("after sorting src node is not the first node");

    // don't need to src node for index
    result.erase(result.begin());

    return result;
}

void GlobalRouter::fix_register_net(int net_id, Pin &pin) {
    auto segment = current_routes[net_id][pin.node];
    auto src_node = segment[0];
    if (src_node->type != NodeType::SwitchBox)
        throw ::runtime_error("the beginning of a reg fix has to be a sb");

    // found all nodes width that tile
    ::set<::shared_ptr<Node>> tile_nodes;
    for (auto const &node : segment) {
        if (node->x == pin.x && node->y == pin.y)
            tile_nodes.insert(node);
    }

    /* Note:
     * search to see if there any registers connected to them.
     * it is safe to assume that the registers are pipeline registers
     * that points to the same node
     */
    ::shared_ptr<Node> reg_node = nullptr;
    ::shared_ptr<Node> pre_node = nullptr;
    for (const auto &node : segment) {
        for (const auto &next : *node) {
            if (next->type == NodeType::Register) {
                if (!node_connections_.at(next).empty()) {
                    continue;
                } else {
                    pre_node = node;
                    reg_node = next;
                    break;
                }
            }
        }
        if (reg_node)
            break;
    }

    if (!reg_node) {
        throw ::runtime_error("unable to find free register node in the give "
                              "tile specified by the placer");
    }


    // it has to be a pipeline register! so find where it connected to in the
    // path
    auto next_node = *reg_node->begin();
    if (next_node->type != NodeType::SwitchBox)
        throw ::runtime_error("the register has to be in the switch box");
    // that node has to be in the path
    uint32_t index;
    for (index = 0; index < segment.size(); index++) {
        if (segment[index] == next_node) {
            break;
        }
    }
    if (index == segment.size())
        throw ::runtime_error("unable to find the connected register in given "
                              "path");
    // do a surgery to fix the path
    ::vector<::shared_ptr<Node>> new_segment = {reg_node};
    for (uint32_t i = index; i < segment.size(); i++) {
        // append to the new segment
        new_segment.emplace_back(segment[i]);
    }
    // this will be the new segment
    // first, remove the wrong entry
    current_routes[net_id].erase(pin.node);
    // then assign the new pin node
    pin.node = reg_node;
    // update the current_routes
    current_routes[net_id][pin.node] = new_segment;

    // and we need to fix the old segment by appending to the new ones
    auto key_entry = reg_net_table_.at(net_id);
    auto &src_segment = current_routes.at(key_entry.first).at(key_entry.second);
    auto fix_index = src_segment.size();
    if (src_segment.back() != segment.front())
        throw ::runtime_error("reg src net and reg net doesn't match with src");
    for (uint32_t node_index = 1; node_index < segment.size(); node_index++) {
        if (segment[node_index - 1] == pre_node) {
            break;
        } else {
            src_segment.emplace_back(segment[node_index]);
        }
    }
    // append the register
    src_segment.emplace_back(reg_node);
    // update with the node assignment for the new one and finally we're done
    for (auto i = fix_index; i < src_segment.size(); i++) {
        assign_connection(src_segment[i], src_segment[i - 1]);
    }
}