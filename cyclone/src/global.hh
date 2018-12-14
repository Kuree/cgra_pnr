#ifndef CYCLONE_GLOBAL_HH
#define CYCLONE_GLOBAL_HH

#include "route.hh"

class GlobalRouter : public Router {
public:
    GlobalRouter(uint32_t num_iteration, const RoutingGraph &g);

    void route() override;

    double route_strategy_ratio = 0.5;

protected:
    virtual void
    route_net(Net &net, uint32_t it);

    virtual void compute_slack_ratio(uint32_t current_iter);
    virtual std::function<double(const std::shared_ptr<Node> &,
                                   const std::shared_ptr<Node> &)>
    create_cost_function(int net_id, double an, uint32_t it);

    virtual std::function<bool(const std::shared_ptr<Node> &)>
    get_free_register(const std::pair<uint32_t, uint32_t> &p);

private:
    uint32_t num_iteration_ = 40;

    std::map<std::pair<int, uint32_t>,
             double> slack_ratio_;
    uint32_t hn_factor_ = 1;
    double slack_factor_ = 0.01;
};


#endif //CYCLONE_GLOBAL_HH
