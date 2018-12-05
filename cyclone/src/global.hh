#ifndef CYCLONE_GLOBAL_HH
#define CYCLONE_GLOBAL_HH

#include "route.hh"

class GlobalRouter : public Router {
public:
    explicit GlobalRouter(uint32_t num_iteration);

    void route() override;

protected:
    virtual void route_net(Net &net, uint32_t it);

    virtual void compute_slack_ratio(std::map<std::pair<std::shared_ptr<Node>,
            std::shared_ptr<Node>>,
            double> &ratio, uint32_t current_iter);
    virtual std::function<uint32_t(const std::shared_ptr<Node> &)>
    create_cost_function();

private:
    uint32_t num_iteration_ = 40;

    // a list of routing segments indexed by net id
    std::map<int,
             std::map<std::shared_ptr<Node>,
                      std::vector<std::shared_ptr<Node>>>> current_routes;
    void update_cost_table();
    void assign_routes();

    uint32_t fail_count_ = 0;
};


#endif //CYCLONE_GLOBAL_HH
