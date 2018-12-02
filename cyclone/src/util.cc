#include <cstdlib>
#include "util.hh"

using std::shared_ptr;

uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::shared_ptr<Node> &node2) {
    int dx = node1->x - node2->x;
    int dy = node1->y - node2->y;

    return static_cast<uint32_t>(abs(dx) + abs(dy));
}