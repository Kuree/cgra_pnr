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


void
Router::add_net(const std::vector<std::pair<std::string, std::string>> &net) {
    int net_id = static_cast<int>(netlist_.size());
    Net n;
    n.id = net_id;
    for (auto const &entry : net) {
        auto const &[blk_id, port] = entry;
        if (placement_.find(blk_id) == placement_.end())
            throw ::runtime_error("unable to find placement for " + blk_id);
        auto const &[x, y] = placement_[blk_id];
        n.add_pin({x, y, port});
    }
    // point the pin to the actual node in the graph
    // notice that registers won't be assigned at this stage because we need to
    // construct mega nets later
    for (auto &pin : n) {
        auto node = get_node(pin.x, pin.y, pin.port);
        // reg's in and out will be marked as rin and rout
        if (node == nullptr && (pin.port != "rin" && pin.port != "rout"))
            throw ::runtime_error("unable to find node with given pin");
        pin.node = node;
    }
    netlist_.emplace_back(n);
}

void Router::add_placement(const uint32_t &x, const uint32_t &y,
                           const std::string &blk_id) {
    placement_[blk_id] = {x, y};
}

::vector<::shared_ptr<Node>>
Router::u_route_dijkstra(const ::shared_ptr<Node> &start,
                         const ::shared_ptr<Node> &end) {
    auto zero_estimate = [](const ::shared_ptr<Node>,
                            const::shared_ptr<Node>) -> uint32_t {
        return 0;
    };
    return u_route_a_star(start, end, zero_estimate);
}

std::vector<std::shared_ptr<Node>> Router::u_route_a_star(
        const std::shared_ptr<Node> &start, const std::shared_ptr<Node> &end) {
    return u_route_a_star(start, end, manhattan_distance);
}

std::vector<std::shared_ptr<Node>> Router::u_route_a_star(
        const std::shared_ptr<Node> &start, const std::shared_ptr<Node> &end,
        std::function<uint32_t(const std::shared_ptr<Node> &,
                               const std::shared_ptr<Node>)> h_f) {
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

    while (head != end) {
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
    head = end;
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
                                       const std::string &port) {
    auto nodes = graph_.get_nodes(x, y);
    if (nodes.empty())
        return nullptr;
    for (const auto &node : nodes) {
        if (node->name == port) {
            return node;
        }
    }
    return nullptr;
}