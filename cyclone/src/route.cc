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


void
Router::add_net(const std::vector<std::pair<::string, ::string>> &net) {
    int net_id = static_cast<int>(netlist_.size());
    Net n;
    n.id = net_id;
    for (auto const &entry : net) {
        auto const &[blk_id, port] = entry;
        if (placement_.find(blk_id) == placement_.end())
            throw ::runtime_error("unable to find placement for " + blk_id);
        auto const &[x, y] = placement_[blk_id];
        n.add_pin({x, y, blk_id, port});
    }
    // point the pin to the actual node in the graph
    // notice that we will also assign registers at this stage
    for (auto &pin : n) {
        auto node = get_node(pin.x, pin.y, pin.port);
        if (node == nullptr)
            throw ::runtime_error("unable to find node with given pin");
        pin.node = node;
        // assign register names so that we can identify them
        if (node->type == NodeType::Register)
            node->name = pin.name;
    }
    netlist_.emplace_back(n);
}

void Router::add_placement(const uint32_t &x, const uint32_t &y,
                           const ::string &blk_id) {
    placement_[blk_id] = {x, y};
}

::vector<::shared_ptr<Node>>
Router::u_route_dijkstra(const ::shared_ptr<Node> &start,
                         const ::shared_ptr<Node> &end) {
    auto zero_estimate = [](const ::shared_ptr<Node>,
                            const::shared_ptr<Node>) -> uint32_t {
        return 0;
    };
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node == end;
    };
    return u_route_a_star(start, end_f, zero_estimate);
}

std::vector<std::shared_ptr<Node>>
Router::u_route_a_star(const std::shared_ptr<Node> &start,
                       const std::shared_ptr<Node> &end) {
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node == end;
    };
    return u_route_a_star(start, end_f, manhattan_distance);
}

std::vector<std::shared_ptr<Node>>
Router::u_route_a_star(const std::shared_ptr<Node> &start,
                       const std::pair<uint32_t, uint32_t> &end) {
    auto end_f = [&](const ::shared_ptr<Node> &node) -> bool {
        return node->x == end.first && node->y == end.second;
    };
    return u_route_a_star(start, end_f, manhattan_distance);
}

std::vector<std::shared_ptr<Node>> Router::u_route_a_star(
        const std::shared_ptr<Node> &start,
        std::function<bool(const std::shared_ptr<Node> &)> end_f,
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
            uint32_t edge_cost = head->get_cost(node);
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
        head = trace[head];
    }
    routed_path.emplace_back(head);

    std::reverse(routed_path.begin(), routed_path.end());
    return routed_path;
}

std::shared_ptr<Node> Router::get_node(const uint32_t &x, const uint32_t &y,
                                       const ::string &port) {
    auto nodes = graph_.get_nodes(x, y);
    if (nodes.empty())
        return nullptr;
    for (const auto &node : nodes) {
        if (port == REG_IN || port == REG_OUT) {
            // FIXME:
            // assume one register per tile
            return node;
        } else if (node->name == port) {
            return node;
        }
    }
    return nullptr;
}

void Router::group_reg_nets() {
    ::map<::string, int> main_nets;
    // first pass to determine where the reg nets originates.
    for (auto &net : netlist_) {
        for (const auto &pin : net) {
            if (pin.port == REG_IN) {
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
            if (pin.port == REG_OUT) {
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