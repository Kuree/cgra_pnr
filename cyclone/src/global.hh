#ifndef CYCLONE_GLOBAL_HH
#define CYCLONE_GLOBAL_HH

#include "route.hh"

class GlobalRouter : public Router {
public:
    GlobalRouter(uint32_t num_iteration, const RoutingGraph &g);

    void route() override;

    double route_strategy_ratio = 1;

protected:
    virtual void
    route_net(int net_id, uint32_t it);

    virtual void compute_slack_ratio(uint32_t current_iter);
    virtual std::function<double(const std::shared_ptr<Node> &,
                                 const std::shared_ptr<Node> &)>
    create_cost_function(double an, uint32_t it, int net_id);

    virtual std::function<bool(const std::shared_ptr<Node> &)>
    get_free_switch(const std::pair<uint32_t, uint32_t> &p);

private:
    uint32_t num_iteration_ = 40;

    std::map<std::pair<int, uint32_t>,
             double> slack_ratio_;
    double hn_factor_ = 0.1;
    double slack_factor_ = 0.9;
    std::map<int, std::pair<int, uint32_t>> reg_net_table_;

    std::vector<uint32_t> reorder_pins(const Net &net);
    void fix_register_net(int net_id, Pin &pin);
};


#endif //CYCLONE_GLOBAL_HH
