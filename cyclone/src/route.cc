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
using std::unordered_map;


constexpr auto gsv = get_side_value;
constexpr auto gsi = get_side_int;

Router::Router(const RoutingGraph &g) : graph_(g) {
    // create the look up table for cost analysis
    for (const auto &tile_iter : graph_) {
        const auto &tile = tile_iter.second;
        for (uint32_t side = 0; side < Switch::SIDES; side++) {
            auto &side_sbs = tile.switchbox[get_side_int(side)];
            for (const auto &sb : side_sbs) {
                for (uint32_t io = 0; io < Node::IO; io++) {
                    node_connections_[io].insert({sb, {}});
                    node_history_[io].insert({sb, {}});
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
                       const ::shared_ptr<Node> &end,
                       const ::shared_ptr<Node> &pre_node) {
    return route_dijkstra(start, end, zero_cost, pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_dijkstra(const std::shared_ptr<Node> &start,
                       const std::shared_ptr<Node> &end,
                       ::function<uint32_t(const ::shared_ptr<Node> &,
                                           const ::shared_ptr<Node> &,
                                           const ::shared_ptr<Node> &)>
                       cost_f,
                       const ::shared_ptr<Node> &pre_node) {
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node == end;
    };
    return route_a_star(start, end_f, ::move(cost_f), zero_estimate, pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end,
                     const ::shared_ptr<Node> &pre_node) {
    return route_a_star(start, end, zero_cost, pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     const ::shared_ptr<Node> &pre_node) {
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node == end;
    };
    return route_a_star(start, end_f, ::move(cost_f), manhattan_distance,
                        pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::pair<uint32_t, uint32_t> &end,
                     const ::shared_ptr<Node> &pre_node) {
    return route_a_star(start, end, zero_cost, pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::pair<uint32_t, uint32_t> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     const ::shared_ptr<Node> &pre_node) {
    return route_a_star(start, end, ::move(cost_f), manhattan_distance,
                        pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     std::function<bool(const std::shared_ptr<Node> &)> end_f,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     const ::shared_ptr<Node> &pre_node) {
    return route_a_star(start, ::move(end_f), ::move(cost_f),
                        manhattan_distance, pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::pair<uint32_t, uint32_t> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node>)> h_f,
                     const ::shared_ptr<Node> &pre_node) {
    return route_a_star(start, same_loc(end), ::move(cost_f), ::move(h_f),
                        pre_node);
}

std::vector<std::shared_ptr<Node>>
Router::route_a_star(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node> &)> cost_f,
                     ::function<uint32_t(const ::shared_ptr<Node> &,
                                         const ::shared_ptr<Node>)> h_f,
                     const ::shared_ptr<Node> &pre_node) {
    return route_a_star(start, same_node(end), ::move(cost_f), ::move(h_f),
                        pre_node);
}

std::vector<std::shared_ptr<Node>> Router::route_a_star(
        const std::shared_ptr<Node> &start,
        std::function<bool(const std::shared_ptr<Node> &)> end_f,
        std::function<uint32_t(const std::shared_ptr<Node> &,
                               const std::shared_ptr<Node> &,
                               const std::shared_ptr<Node> &)> cost_f,
        std::function<uint32_t(const ::shared_ptr<Node> &,
                               const ::shared_ptr<Node>)> h_f,
        const ::shared_ptr<Node> &pre_node) {
    ::set<::shared_ptr<Node>> visited;
    ::unordered_map<::shared_ptr<Node>, uint32_t> cost = {{start, 0}};
    ::unordered_map<::shared_ptr<Node>, uint32_t> t_cost = {{start, 0}};
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
    ::shared_ptr<Node> before_head = pre_node;
    while (!end_f(head)) {
        if (working_set.empty())
            throw ::runtime_error("failed to route");
        // get the one with lowest cost
        head = working_set.top();
        working_set.pop();

        if (trace.find(head) != trace.end())
            before_head = trace.at(head);

        uint32_t current_cost = cost[head];
        for (auto const &node : head->get_neighbor(before_head)) {
            if (visited.find(node) != visited.end())
                continue;
            uint32_t edge_cost = head->get_edge_cost(before_head, node) +
                                 cost_f(before_head, head, node);
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

std::shared_ptr<Node> Router::get_port(const uint32_t &x, const uint32_t &y,
                                       const string &port) {
    return graph_.get_port(x, y, port);
}

void Router::group_reg_nets() {
    ::map<::string, int> driven_by;
    // first pass to determine where the reg nets originates.
    for (auto &net : netlist_) {
        for (uint32_t i = 1; i < net.size(); i++) {
            auto const &pin = net[i];
            if (pin.port == REG and pin.name[0] == 'r') {
                // we assume it's already packed
                driven_by.insert({pin.name, net.id});
            }
        }
    }

    // second pass to create a map from the reg src to sink
    for (auto &net : netlist_) {
        if (driven_by.find(net[0].name) != driven_by.end()) {
            // we have found a reg that drives this net
            reg_net_src_.insert({net[0].name, net.id});
        }
    }

    // a similar algorithm to topological sort to assure the orders
    // we don't care about the lowest level of the reg tree.
    // it is because by ensuring routing the nets that has reg sinks first,
    // the leaves regs will automatically be routed last, hence ensure its
    // legality
    for (const auto &iter : driven_by) {
        uint32_t level = 0;
        ::string name = iter.first;
        while (driven_by.find(name) != driven_by.end()) {
            name = netlist_[driven_by.at(name)][0].name;
            level++;
        }
        reg_net_order_.insert({iter.first, level});
        reg_net_order_.insert({name, 0});
    }
}

std::vector<uint32_t>
Router::reorder_reg_nets() {
    ::vector<uint32_t> result(netlist_.size());
    for (uint32_t i = 0; i < netlist_.size(); i++)
        result[i] = i;
    std::sort(result.begin(), result.end(),
              [&](uint32_t n1, uint32_t n2) -> bool {
        auto &net1 = netlist_[n1];
        auto &net2 = netlist_[n2];
        uint32_t net1_value = reg_net_order_.find(net1[0].name)
                                  != reg_net_order_.end()?
                              reg_net_order_.at(net1[0].name)
                              : std::numeric_limits<uint32_t>::max();
        uint32_t net2_value = reg_net_order_.find(net2[0].name)
                                  != reg_net_order_.end()?
                              reg_net_order_.at(net2[0].name)
                              : std::numeric_limits<uint32_t>::max();
        return net1_value < net2_value;
    });
    return result;
}

bool Router::overflow() {
    return overflowed_;
}

void Router::assign_net(int net_id) {
    auto segments = current_routes[net_id];
    for (auto &seg_it : segments) {
        auto &segment = seg_it.second;
        for (uint32_t i = 0; i < segment.size() - 1; i++) {
            auto &node1 = segment[i];
            auto &node2 = segment[i + 1];
            assign_connection(node1, OUT, net_id);
            assign_connection(node2, IN, net_id);
        }
    }
}

void Router::assign_history() {
    for (const auto &net : netlist_) {
        auto segments = current_routes[net.id];
        for (auto &seg_it : segments) {
            auto &segment = seg_it.second;
            for (uint32_t i = 0; i < segment.size() - 1; i++) {
                auto &node1 = segment[i];
                auto &node2 = segment[i + 1];
                assign_history(node1, OUT);
                assign_history(node2, IN);
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

void Router::assign_connection(const std::shared_ptr<Node> &node, uint32_t io,
                               int net_id) {
    node_connections_[io].at(node).insert(net_id);
    if (!overflowed_ && node_connections_[io].at(node).size() > 1)
        overflowed_ = true;

}

void Router::assign_history(std::shared_ptr<Node> &end,
                            uint32_t io) {
    node_history_[io].at(end)++;
}

void Router::clear_connections() {
    for (auto &io : node_connections_) {
        for (auto &iter : io) {
            iter.second.clear();
        }
    }
}

uint32_t Router::get_history_cost(const std::shared_ptr<Node> &,
                                  const std::shared_ptr<Node> &end) {
    uint32_t result = 0;

    for (auto &io : node_history_) {
        result += io.at(end);
    }
    return result;
}

uint32_t Router::get_presence_cost(const std::shared_ptr<Node> &node,
                                   uint32_t io,
                                   int net_id) {
    ::set<int> start_connection = node_connections_[io].at(node);

    if (start_connection.find(net_id) == start_connection.end())
        return static_cast<uint32_t>(start_connection.size());
    else
        return static_cast<uint32_t>(start_connection.size() - 1);

}