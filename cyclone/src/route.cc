#include "route.hh"

void Router::add_net(const std::vector<std::pair<std::pair<uint32_t, uint32_t>,
                     std::string>> &net) {
    int net_id = static_cast<int>(netlist_.size());
    Net n(net);
    n.id = net_id;
    netlist_.emplace_back(n);
}