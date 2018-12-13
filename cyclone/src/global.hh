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
    virtual std::function<uint32_t(const std::shared_ptr<Node> &,
                                   const std::shared_ptr<Node> &,
                                   const std::shared_ptr<Node> &)>
    create_cost_function(const std::shared_ptr<Node> &node1,
                         const std::shared_ptr<Node> &node2,
                         int net_id, uint32_t seg_index);

    virtual std::function<bool(const std::shared_ptr<Node> &)>
    get_free_register(const std::pair<uint32_t, uint32_t> &p);

private:
    uint32_t num_iteration_ = 40;
    uint32_t reg_fix_iteration_ = 10;

    std::map<std::pair<int, uint32_t>,
             double> slack_ratio_;
    uint32_t pn_factor_ = 10;
};


#endif //CYCLONE_GLOBAL_HH
