#ifndef CYCLONE_GLOBAL_HH
#define CYCLONE_GLOBAL_HH

#include "route.hh"

class GlobalRouter : public Router {
public:
    GlobalRouter(uint32_t num_iteration, const RoutingGraph &g);

    void route() override;

protected:
    virtual void
    route_net(Net &net, uint32_t it,
              const std::map<std::pair<std::shared_ptr<Node>,
                                       std::shared_ptr<Node>>,
                             double> &slack_ratio);

    virtual void compute_slack_ratio(std::map<std::pair<std::shared_ptr<Node>,
            std::shared_ptr<Node>>,
            double> &ratio, uint32_t current_iter);
    virtual std::function<uint32_t(const std::shared_ptr<Node> &,
                                   const std::shared_ptr<Node> &)>
    create_cost_function(uint32_t slack);

private:
    uint32_t num_iteration_ = 40;
    uint32_t fail_count_ = 0;

    std::map<std::shared_ptr<Node>, uint32_t> per_node_cost_;

};


#endif //CYCLONE_GLOBAL_HH
