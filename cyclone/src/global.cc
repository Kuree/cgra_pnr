#include <limits>
#include "global.hh"

using std::map;
using std::shared_ptr;
using std::vector;
using std::set;
using std::pair;
using std::runtime_error;
using std::string;
using std::function;
using std::move;

GlobalRouter::GlobalRouter(uint32_t num_iteration)
    : Router(), num_iteration(num_iteration) { }

void GlobalRouter::route() {
    // the actual routing part
    // algorithm based on PathFinder with modification for CGRA architecture
    // TODO:
    // make it domain-specific

    // 1. reorder the nets so that nets with register sinks are routed
    //    first to determine the register position at each iteration. this is
    //    fine since the relative ordering of these two groups (with and
    //    and without) doesn't matter
    // 2. calculate the slack ratio to determine what kind od routing algorithm
    //    to use. either RSMT or shortest-path for each pin pairs
    // 3. actually perform iterations (described in PathFiner)

    group_reg_nets();
    reorder_reg_nets();

    ::map<::pair<::shared_ptr<Node>, ::shared_ptr<Node>>, double> slack_ratio;
    approximate_slack_ratio(slack_ratio);

    for (uint32_t it = 0; it < num_iteration; it++) {
        for (auto const &net : netlist_) {
            route_net(net);
        }
        if (!overflow()) {
            return;
        }
    }
    if (overflow())
        throw ::runtime_error("unable to route. sorry!");
}

uint32_t GlobalRouter::approximate_delay(const std::shared_ptr<Node> &node1,
                                         const std::shared_ptr<Node> &node2) {
    // this is a simple pin to pin delay analysis, which is consistent
    // with the PathFinder paper
    // use the connected switch to node as a way to approximate the delay
    // on switchbox
    // TODO: improve this timing analysis
    uint32_t sb_delay = 0;
    for (const auto &node : *node1) {
        if (node->type == NodeType::SwitchBox)
            sb_delay = node->delay;
    }
    if (sb_delay == 0)
        throw ::runtime_error("unable to get switch box delay");
    int dist_x = node1->x - node2->x;
    int dist_y = node1->y - node2->y;
    auto dist = static_cast<uint32_t>(abs(dist_x) + abs(dist_y));
    return dist * sb_delay;
}

void
GlobalRouter::approximate_slack_ratio(::map<::pair<::shared_ptr<Node>,
        ::shared_ptr<Node>>,
        double> &ratio) {
    double max_delay = 0;
    double min_delay = std::numeric_limits<double>::max();
    for (auto &net : netlist_) {
        // FIXME
        // refactor the net to distinguish the source and sinks
        const auto &src = net[0].node;
        for (uint32_t i = 1; i < net.size(); i++) {
            auto const &sink = net[i].node;
            auto const delay = approximate_delay(src, sink);
            ratio[{src, sink}] = delay;
            if (delay > max_delay)
                max_delay = delay;
            if (delay < min_delay)
                min_delay = delay;
        }
    }
    // normalize
    for (auto &iter : ratio) {
        iter.second = (iter.second - min_delay) / max_delay;
    }
}

void GlobalRouter::route_net(const Net &) {

}
