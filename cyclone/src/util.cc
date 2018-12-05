#include <cstdlib>
#include "util.hh"

using std::shared_ptr;

uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::shared_ptr<Node> &node2) {
    int dx = node1->x - node2->x;
    int dy = node1->y - node2->y;

    return static_cast<uint32_t>(abs(dx) + abs(dy));
}

uint32_t zero_cost(const ::shared_ptr<Node> &, const ::shared_ptr<Node> &)
{ return 0; }

uint32_t zero_estimate(const std::shared_ptr<Node> &,
                       const std::shared_ptr<Node> &) { return 0; }

std::function<bool(const std::shared_ptr<Node> &)>
same_loc(const std::pair<uint32_t, uint32_t> &p) {
    return [&](const std::shared_ptr<Node> &node) -> bool {
        return node->x == p.first && node->y == p.second;
    };;
}

std::function<bool(const std::shared_ptr<Node> &)>
same_node(const std::shared_ptr<Node> &node1) {
    return [&](const ::shared_ptr<Node> &node2) -> bool {
        return node1 == node2;
    };;
}