#ifndef CYCLONE_ROUTE_HH
#define CYCLONE_ROUTE_HH

#include <functional>
#include <map>
#include "graph.hh"
#include "net.hh"

// base class for global and detailed routers
// implement basic routing algorithms and IO handling
class Router {
public:
    Router() = default;

    // add_net has to be used after constructing all the routing graph
    // otherwise it will throw errors
    void add_net(const std::vector<std::pair<std::string, std::string>> &net);
    void add_placement(const uint32_t &x, const uint32_t &y,
                       const std::string &blk_id);
    void add_edge(const Node &node1, const Node &node2)
    { graph_.add_edge(node1, node2); }

protected:
    RoutingGraph graph_;
    std::vector<Net> netlist_;
    std::map<std::string, std::pair<uint32_t, uint32_t>> placement_;

    // u indicates it doesn't care about congestion or routing resources
    std::vector<std::shared_ptr<Node>>
    u_route_dijkstra(const std::shared_ptr<Node> &start,
                     const std::shared_ptr<Node> &end);
    std::vector<std::shared_ptr<Node>>
    u_route_a_star(const std::shared_ptr<Node> &start,
                   const std::shared_ptr<Node> &end);

    // this is the actual routing engine shared by Dijkstra and A*
    std::vector<std::shared_ptr<Node>>
    u_route_a_star(const std::shared_ptr<Node> &start,
                   const std::shared_ptr<Node> &end,
                   std::function<uint32_t(const std::shared_ptr<Node> &,
                                          const std::shared_ptr<Node>)> h_f);

    std::shared_ptr<Node> get_node(const uint32_t &x,
                                   const uint32_t &y,
                                   const std::string &port);
};

#endif //CYCLONE_ROUTE_HH
