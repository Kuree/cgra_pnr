#include <map>
#include <queue>
#include <algorithm>
#include "route.hh"

using std::map;
using std::shared_ptr;
using std::vector;
using std::set;
using std::pair;
using std::runtime_error;
using std::priority_queue;


void Router::add_net(const std::vector<std::pair<std::pair<uint32_t, uint32_t>,
                     std::string>> &net) {
    int net_id = static_cast<int>(netlist_.size());
    Net n(net);
    n.id = net_id;
    netlist_.emplace_back(n);
}

::vector<::shared_ptr<Node>>
Router::u_route_dijkstra(const ::shared_ptr<Node> &start,
                         const ::shared_ptr<Node> &end) {
    ::set<::shared_ptr<Node>> visited;
    ::map<::shared_ptr<Node>, uint32_t> cost = {{start, 0}};
    // use cost as a comparator
    auto cost_comp = [&](const ::shared_ptr<Node> &a,
                         const ::shared_ptr<Node> &b) -> bool {
        return cost[a] > cost[b];
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
            uint32_t tentative_cost = edge_cost + current_cost;
            if (cost.find(node) == cost.end()) {
                cost[node] = tentative_cost;
                working_set.emplace(node);
                trace[node] = head;
            } else if (cost[node] > tentative_cost) {
                cost[node] = tentative_cost;
                trace[node] = head;
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