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
    explicit Router(const RoutingGraph &g) : graph_(std::move(g)) { }

    // add_net has to be used after constructing all the routing graph
    // otherwise it will throw errors
    void add_net(const std::string &name,
                 const std::vector<std::pair<std::string, std::string>> &net);
    void add_placement(const uint32_t &x, const uint32_t &y,
                       const std::string &blk_id);
    void add_edge(const Node &node1, const Node &node2)
    { graph_.add_edge(node1, node2); }
    bool overflow();

    // routing related function
    virtual void route() { };
    // assign nets
    void assign_nets();
    void clear_connections();
    std::map<std::string, std::vector<std::vector<std::shared_ptr<Node>>>>
    realize();

protected:
    RoutingGraph graph_;
    std::vector<Net> netlist_;
    std::map<std::string, std::pair<uint32_t, uint32_t>> placement_;
    std::map<int, std::set<int>> reg_nets_;
    // a list of routing segments indexed by net id
    std::map<int,
            std::map<std::shared_ptr<Node>,
                    std::vector<std::shared_ptr<Node>>>> current_routes;

    // graph independent look tables for computing routing cost
    std::map<std::shared_ptr<Node>,
            std::set<std::shared_ptr<Node>>
            [SwitchBoxNode::SIDES][Node::IO]> sb_connections_;
    std::map<std::shared_ptr<Node>,
            std::set<std::shared_ptr<Node>>[Node::IO]> node_connections_;

    std::map<std::shared_ptr<Node>,
             uint32_t[SwitchBoxNode::SIDES][Node::IO]> sb_history_;
    std::map<std::shared_ptr<Node>, uint32_t[Node::IO]> node_history_;

    const static uint32_t IN = 0;
    const static uint32_t OUT = 1;

    std::vector<std::shared_ptr<Node>>
    route_dijkstra(const std::shared_ptr<Node> &start,
                   const std::shared_ptr<Node> &end);

    std::vector<std::shared_ptr<Node>>
    route_dijkstra(const std::shared_ptr<Node> &start,
                   const std::shared_ptr<Node> &end,
                   std::function<uint32_t(const std::shared_ptr<Node> &,
                                          const std::shared_ptr<Node> &)>
                                          cost_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::shared_ptr<Node> &end);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::shared_ptr<Node> &end,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node> &)> cost_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::pair<uint32_t, uint32_t> &end);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::pair<uint32_t, uint32_t> &end,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node> &)> cost_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::pair<uint32_t, uint32_t> &end,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node> &)> cost_f,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node>)> h_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::shared_ptr<Node> &end,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node> &)> cost_f,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node>)> h_f);

    // tries its best to route an L shape based on a_star routing
    // it's theoretically a little bit slower than directly wiring a L shape
    std::vector<std::shared_ptr<Node>>
    route_l(const std::shared_ptr<Node> &start,
            const std::shared_ptr<Node> &end,
            const std::pair<uint32_t, uint32_t> &steiner_p,
            std::function<uint32_t(const std::shared_ptr<Node> &,
                                   const std::shared_ptr<Node> &)> cost_f,
            std::function<uint32_t(const std::shared_ptr<Node> &,
                                   const std::shared_ptr<Node>)> h_f);

    // this is the actual routing engine shared by Dijkstra and A*
    // it's designed to be flexible
    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 std::function<bool(const std::shared_ptr<Node> &)> end_f,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node> &)> cost_f,
                 std::function<uint32_t(const std::shared_ptr<Node> &,
                                        const std::shared_ptr<Node>)> h_f);

    std::shared_ptr<Node> get_port(const uint32_t &x,
                                   const uint32_t &y,
                                   const std::string &port);

    // group the nets to determine the relative net placement order
    // this is because we assign register locations on the fly
    void group_reg_nets();
    void reorder_reg_nets();


    void assign_connection(std::shared_ptr<Node> &start,
                           std::shared_ptr<Node> &end,
                           uint32_t io);

    uint32_t get_history_cost(const std::shared_ptr<Node> &start,
                              const std::shared_ptr<Node> &end);

    uint32_t get_presence_cost(const std::shared_ptr<Node> &start,
                               const std::shared_ptr<Node> &end,
                               uint32_t io);

private:
    static constexpr char REG_IN[] = "in";
    static constexpr char REG_OUT[] = "out";

};

#endif //CYCLONE_ROUTE_HH
