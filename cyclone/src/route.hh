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
    explicit Router(const RoutingGraph &g);

    // add_net has to be used after constructing all the routing graph
    // otherwise it will throw errors
    void add_net(const std::string &name,
                 const std::vector<std::pair<std::string, std::string>> &net);
    void add_placement(const uint32_t &x, const uint32_t &y,
                       const std::string &blk_id);
    bool overflow();

    // routing related function
    virtual void route() { };
    // assign nets
    void assign_net_segment(const std::vector<std::shared_ptr<Node>> &segment,
                            int net_id);
    void assign_history();
    void clear_connections();
    std::map<std::string, std::vector<std::vector<std::shared_ptr<Node>>>>
    realize() const;

    // getter & setter
    double get_init_pn() const { return init_pn_; }
    void set_init_pn(double init_pn) { init_pn_ = init_pn; }
    double get_pn_factor() const  { return pn_factor_; }
    void set_pn_factor(double pn_factor) { pn_factor_ = pn_factor; }
    const std::vector<Net>& get_netlist() const { return netlist_; }


protected:
    RoutingGraph graph_;
    std::vector<Net> netlist_;
    std::map<std::string, std::pair<uint32_t, uint32_t>> placement_;
    std::map<int, std::vector<int>> reg_net_order_;
    std::map<std::string, int> reg_net_src_;
    // a list of routing segments indexed by net id
    std::map<int,
            std::map<uint32_t,
                    std::vector<std::shared_ptr<Node>>>> current_routes;

    // graph independent look tables for computing routing cost
    std::map<std::shared_ptr<Node>, std::set<std::shared_ptr<Node>>>
    node_connections_;
    std::unordered_map<std::shared_ptr<Node>, std::set<int>> node_net_ids_;

    std::map<std::shared_ptr<Node>, uint32_t> node_history_;

    bool overflowed_ = false;

    const static uint32_t IN = 0;
    const static uint32_t OUT = 1;

    static constexpr char REG[] = "reg";

    double init_pn_ = 10000;
    double pn_factor_ = 1.5;

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::shared_ptr<Node> &end);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::shared_ptr<Node> &end,
                 std::function<double(const std::shared_ptr<Node> &,
                                      const std::shared_ptr<Node> &)> cost_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::pair<uint32_t, uint32_t> &end,
                 std::function<double(const std::shared_ptr<Node> &,
                                      const std::shared_ptr<Node> &)> cost_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::pair<uint32_t, uint32_t> &end,
                 std::function<double(const std::shared_ptr<Node> &,
                                      const std::shared_ptr<Node> &)> cost_f,
                 std::function<double(const std::shared_ptr<Node> &)> h_f);

    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 const std::shared_ptr<Node> &end,
                 std::function<double(const std::shared_ptr<Node> &,
                                      const std::shared_ptr<Node> &)> cost_f,
                 std::function<double(const std::shared_ptr<Node> &)> h_f);

    // this is the actual routing engine shared by Dijkstra and A*
    // it's designed to be flexible
    std::vector<std::shared_ptr<Node>>
    route_a_star(const std::shared_ptr<Node> &start,
                 std::function<bool(const std::shared_ptr<Node> &)> end_f,
                 std::function<double(const std::shared_ptr<Node> &,
                                      const std::shared_ptr<Node> &)> cost_f,
                 std::function<double(const std::shared_ptr<Node> &)> h_f);

    std::shared_ptr<Node> get_port(const uint32_t &x,
                                   const uint32_t &y,
                                   const std::string &port);

    // group the nets to determine the relative net placement order
    // this is because we assign register locations on the fly
    void group_reg_nets();
    std::vector<uint32_t> reorder_reg_nets();


    void assign_connection(const std::shared_ptr<Node> &node,
                           const std::shared_ptr<Node> &pre_node);
    void assign_history(std::shared_ptr<Node> &node);

    uint32_t get_history_cost(const std::shared_ptr<Node> &node);

    double get_presence_cost(const std::shared_ptr<Node> &node,
                             const std::shared_ptr<Node> &pre_node);

    void rip_up_net(int net_id);
    bool node_owned_net(int net_id, std::shared_ptr<Node> node);

private:
    std::vector<int> squash_net(int src_id);
};

class UnableRouteException : public std::runtime_error {
public:
    explicit UnableRouteException(const std::string &msg)
        : std::runtime_error(msg) {}
};


#endif //CYCLONE_ROUTE_HH
