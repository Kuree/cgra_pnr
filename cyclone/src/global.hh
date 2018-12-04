#ifndef CYCLONE_GLOBAL_HH
#define CYCLONE_GLOBAL_HH

#include "route.hh"

class GlobalRouter : public Router {
public:
    explicit GlobalRouter(uint32_t num_iteration);

    void route() override;

protected:
    virtual uint32_t approximate_delay(const std::shared_ptr<Node> &node1,
                                       const std::shared_ptr<Node> &node2);
    void approximate_slack_ratio(std::map<std::pair<std::shared_ptr<Node>,
            std::shared_ptr<Node>>,
            double> &ratio);
    virtual void route_net(const Net &net);
private:
    uint32_t num_iteration = 40;
};


#endif //CYCLONE_GLOBAL_HH
