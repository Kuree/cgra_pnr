#include <map>
#include <queue>
#include <algorithm>
#include "route.hh"
#include "util.hh"

using std::map;
using std::shared_ptr;
using std::vector;
using std::set;
using std::pair;
using std::runtime_error;
using std::priority_queue;
using std::string;
using std::function;
using std::move;

constexpr auto gsv = get_side_value;

Router::Router(const RoutingGraph &g) : graph_(g) {
    // create the look up table for cost analysis
    for (const auto &tile_iter : graph_) {
        const auto &tile = tile_iter.second;
        for (auto const &sb : tile.sbs) {
            for (uint32_t side = 0; side < SwitchBoxNode::SIDES; side++) {
                for (uint32_t io = 0; io < Node::IO; io++) {
                    sb_connections_[side][io].insert({sb, {}});
                    sb_history_[side][io].insert({sb, {}});
                }
            }
        }
        for (auto const &port : tile.ports) {
            for (uint32_t io = 0; io < Node::IO; io++) {
                node_connections_[io].insert({port.second, {}});
                node_history_[io].insert({port.second, {}});
            }
        }
        for (auto const &reg : tile.registers) {
            for (uint32_t io = 0; io < Node::IO; io++) {
                node_connections_[io].insert({reg.second, {}});
                node_history_[io].insert({reg.second, {}});
            }
        }
    }
}

void
Router::add_net(const ::string &name,
                const ::vector<::pair<::string, ::string>> &net) {
    int net_id = static_cast<int>(netlist_.size());
    Net n;
    n.id = net_id;
    n.name = name;
    ::set<uint64_t> reg_index;
    for (auto const &entry : net) {
        auto const &[blk_id, port] = entry;
        if (placement_.find(blk_id) == placement_.end())
            throw ::runtime_error("unable to find placement for " + blk_id);
        auto const &[x, y] = placement_[blk_id];
        // FIXME
        // right now uses 'r' as a way to indicate register inputs
        if (blk_id[0] == 'r')
            reg_index.insert(n.size());
        n.add_pin({x, y, blk_id, port});
    }
    // point the pin to the actual node in the graph
    // notice that we will also assign registers at this stage
    for (uint64_t i = 0; i < n.size(); i++) {
        Pin &pin = n[i];
        if (reg_index.find(i) != reg_index.end()) {
            // keyi:
            // this is a design choice
            // assignment happens during the global routing stage while
            // performing the routing negotiation
            pin.node = nullptr;
        } else {
            auto node = get_port(pin.x, pin.y, pin.port);
            if (node == nullptr)
                throw ::runtime_error("unable to find node with given pin");
            pin.node = node;
        }
    }
    netlist_.emplace_back(n);
}

void Router::add_placement(const uint32_t &x, const uint32_t &y,
                           const ::string &blk_id) {
    placement_.insert({blk_id, {x, y}});
}

::vector<::shared_ptr<Node>>
Router::route_dijkstra(const ::shared_ptr<Node> &start,
                       const ::shared_ptr<Node> &end) {
    return route_dijkstra(start, end, zero_cost);
}

std::vector<std::shared_ptr<Node>>
Router::route_dijkstra(const std::shared_ptr<Node> &start,
                       const std::shared_ptr<Node> &end,
                       ::function<uint32_t(const ::shared_ptr<Node> &,
                                           const ::shared_ptr<Node> &)>
                       cost_f) {
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node == end;
    };
    return route_a_star(start, end_f, ::move(cost_f), zero_estimate);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end) {
    return route_a_star(start, end, zero_cost);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f) {
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node == end;
    };
    return route_a_star(start, end_f, ::move(cost_f), manhattan_distance);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::pair<uint32_t, uint32_t> &end) {
    return route_a_star(start, end, zero_cost);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::pair<uint32_t, uint32_t> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f) {
    return route_a_star(start, end, ::move(cost_f), manhattan_distance);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::pair<uint32_t, uint32_t> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node>)> h_f) {
    return route_a_star(start, same_loc(end), ::move(cost_f), ::move(h_f));
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node>)> h_f) {
    return route_a_star(start, same_node(end), ::move(cost_f), ::move(h_f));
}


std::vector<std::shared_ptr<Node>> Router::route_a_star(
        const std::shared_ptr<Node> &start,
        std::function<bool(const std::shared_ptr<Node> &)> end_f,
        std::function<uint32_t(const std::shared_ptr<Node> &,
                               const std::shared_ptr<Node> &)> cost_f,
        std::function<uint32_t(const ::shared_ptr<Node> &,
                               const ::shared_ptr<Node>)> h_f) {
    ::set<::shared_ptr<Node>> visited;
    ::map<::shared_ptr<Node>, uint32_t> cost = {{start, 0}};
    ::map<::shared_ptr<Node>, uint32_t> t_cost = {{start, 0}};
    // use cost as a comparator
    auto cost_comp = [&](const ::shared_ptr<Node> &a,
                         const ::shared_ptr<Node> &b) -> bool {
        return t_cost[a] > t_cost[b];
    };

    ::priority_queue<::shared_ptr<Node>,
            ::vector<::shared_ptr<Node>>,
            decltype(cost_comp)> working_set(cost_comp);
    working_set.emplace(start);

    ::map<::shared_ptr<Node>, ::shared_ptr<Node>> trace;

    ::shared_ptr<Node> head = nullptr;

    while (!end_f(head)) {
        if (working_set.empty())
            throw ::runtime_error("failed to route");
        // get the one with lowest cost
        head = working_set.top();
        working_set.pop();

        uint32_t current_cost = cost[head];
        for (auto const &node : *head) {
            if (visited.find(node) != visited.end())
                continue;
            uint32_t edge_cost = head->get_edge_cost(node) + cost_f(head, node);
            uint32_t real_cost = edge_cost + current_cost;
            if (cost.find(node) == cost.end()) {
                cost[node] = real_cost;
                working_set.emplace(node);
                trace[node] = head;
                t_cost[node] = real_cost + h_f(head, node);
            } else if (cost[node] > real_cost) {
                cost[node] = real_cost;
                trace[node] = head;
                t_cost[node] = real_cost + h_f(head, node);
            }
        }

        if (cost.find(head) == cost.end())
            throw ::runtime_error("cannot find node in the tentative score");


        visited.insert(head);
    }

    ::vector<::shared_ptr<Node>> routed_path;
    // back trace the route
    // head is the end
    while (head != start) {
        routed_path.emplace_back(head);
        if (trace.find(head) == trace.end())
            throw ::runtime_error("unexpected error in tracing back route");
        head = trace.at(head);
    }
    routed_path.emplace_back(head);

    std::reverse(routed_path.begin(), routed_path.end());
    return routed_path;
}

std::vector<std::shared_ptr<Node>>
Router::route_l(const std::shared_ptr<Node> &start,
                const std::shared_ptr<Node> &end,
                const std::pair<uint32_t, uint32_t> &steiner_p,
                std::function<uint32_t(const std::shared_ptr<Node> &,
                                       const std::shared_ptr<Node> &)> cost_f,
                std::function<uint32_t(const std::shared_ptr<Node> &,
                                       const std::shared_ptr<Node>)> h_f) {
    // it has two steps, first, route to that steiner point,
    // then route from that steiner point to the end
    auto first_segment = route_a_star(start, steiner_p, cost_f, h_f);
    auto &last_node = first_segment.back();
    // it has to be a switch box
    if (last_node->type != NodeType::SwitchBox)
        throw ::runtime_error("steiner point is not a switchbox");
    auto second_segment = route_a_star(last_node, end, cost_f, h_f);
    // merge these two and return
    first_segment.insert(first_segment.end(), second_segment.begin() + 1,
                         second_segment.end());
    return first_segment;
}

std::shared_ptr<Node> Router::get_port(const uint32_t &x, const uint32_t &y,
                                       const string &port) {
    return graph_.get_port(x, y, port);
}

void Router::group_reg_nets() {
    ::map<::string, int> main_nets;
    // first pass to determine where the reg nets originates.
    for (auto &net : netlist_) {
        for (const auto &pin : net) {
            if (pin.port == REG_IN and pin.name[0] == 'r') {
                // we assume it's already packed
                main_nets[pin.name] = net.id;
                reg_nets_[net.id] = {};
                break;
            }
        }
    }

    // second pass the group the reg nets
    for (auto &net : netlist_) {
        for (const auto &pin : net) {
            if (pin.port == REG_OUT and pin.name[0] == 'r') {
                // it has to be included in the main_nets;
                if (main_nets.find(pin.name) == main_nets.end())
                    throw ::runtime_error("unable to find " + pin.name);
                auto main_id = main_nets[pin.name];
                reg_nets_[main_id].insert(net.id);
                break;
            }
        }
    }
}

void Router::reorder_reg_nets() {
    std::sort(netlist_.begin(), netlist_.end(),
              [&](const Net &net1, const Net &net2) -> bool {
        int net1_value = reg_nets_.find(net1.id) == reg_nets_.end()? 1 : 0;
        int net2_value = reg_nets_.find(net2.id) == reg_nets_.end()? 1 : 0;
        return net1_value < net2_value;
    });
}

bool Router::overflow() {
    for (const auto &side : sb_connections_) {
        for (const auto &io : side) {
            for (const auto &iter : io) {
                if (iter.second.size() > 1)
                    return true;
            }
        }
    }

    // also look at the nodes
    for (const auto &io : node_connections_) {
        for (const auto &iter : io) {
            if (iter.second.size() > 1)
                return true;
        }
    }

    return false;
}

void Router::assign_nets() {
    // using the current nets to assign routes
    for (Net &net : netlist_) {
        auto segments = current_routes[net.id];
        for (auto &seg_it : segments) {
            auto &segment = seg_it.second;
            for (uint32_t i = 0; i < segment.size() - 1; i++) {
                auto &node1 = segment[i];
                auto &node2 = segment[i + 1];
                assign_connection(node1, node2, OUT);
                assign_connection(node2, node1, IN);
            }
        }
    }
}

::map<::string, ::vector<::vector<::shared_ptr<Node>>>>
Router::realize() {
    ::map<::string, ::vector<::vector<::shared_ptr<Node>>>>
    result;
    for (const auto &iter : current_routes) {
        const auto &name = netlist_[iter.first].name;
        ::vector<::vector<shared_ptr<Node>>> segments;
        for (const auto &seg_iter : iter.second)
            segments.emplace_back(seg_iter.second);
        result.insert({name, segments});
    }
    return result;
}

void Router::assign_connection(std::shared_ptr<Node> &start,
                               std::shared_ptr<Node> &end, uint32_t io) {
    if (start->type == NodeType::SwitchBox) {
        auto sb = std::reinterpret_pointer_cast<SwitchBoxNode>(start);
        auto side = sb->get_side(end);
        sb_connections_[gsv(side)][io].at(start).insert(end);
        sb_history_[gsv(side)][io].at(start)++;
    } else {
        node_connections_[io].at(start).insert(end);
        node_history_[io].at(start)++;
    }
}

void Router::clear_connections() {
    for (auto &io : node_connections_) {
        for (auto &iter : io) {
            iter.second.clear();
        }
    }
    for (auto &chan : sb_connections_) {
        for (auto &io : chan) {
            for (auto &iter : io) {
                iter.second.clear();
            }
        }
    }

}

uint32_t Router::get_history_cost(const std::shared_ptr<Node> &start,
                                  const std::shared_ptr<Node> &end) {
    uint32_t result = 0;
    if (start->type == NodeType::SwitchBox) {
        auto sb = std::reinterpret_pointer_cast<SwitchBoxNode>(start);
        auto side = sb->get_side(end);
        const auto &history = sb_history_[gsv(side)];
        for (const auto &io_conn : history) {
            result += io_conn.at(start);
        }

    } else {
        for (auto &io : node_history_) {
            result += io.at(start);
        }
    }
    return result;
}

uint32_t Router::get_presence_cost(const std::shared_ptr<Node> &start,
                                   const std::shared_ptr<Node> &end,
                                   uint32_t io) {
    ::set<shared_ptr<Node>> start_connection;
    if (start->type == NodeType::SwitchBox) {
        auto sb = std::reinterpret_pointer_cast<SwitchBoxNode>(start);
        auto side = sb->get_side(end);
        start_connection = sb_connections_[gsv(side)][io].at(start);
    } else {
        start_connection = node_connections_[io].at(start);
    }
    if (start_connection.find(end) == start_connection.end())
        return static_cast<uint32_t>(start_connection.size());
    else
        return static_cast<uint32_t>(start_connection.size() - 1);

}