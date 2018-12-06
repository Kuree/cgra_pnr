#include <iostream>
#include "src/global.hh"

#define WIDTH 1
#define NUM_TRACK 2
#define SIDES 4
#define SIZE 2

using std::map;
using std::pair;
using std::string;
using std::vector;

int main(int, char **) {
    // just some example on how to use it
    // 1. construct routing graph with standard switch box
    SwitchBoxNode sb(0, 0, WIDTH, 0);
    // 2 x 2 board with 2 routing tracks
    RoutingGraph g(SIZE, SIZE, NUM_TRACK, sb);
    // each tile has 2 ports, "in" and "out"
    // notice that we need to be careful about side
    // side illustration
    //      3
    //    -----
    //  2 |   | 0
    //    |   |
    //    -----
    //      1
    PortNode in_port("in", 0, 0, WIDTH);
    PortNode out_port("out", 0, 0, WIDTH);
    for (auto const &it : g) {
        const auto &tile = it.second;
        // point to that tile's sb
        in_port.x = tile.x;
        in_port.y = tile.y;
        out_port.x = tile.x;
        out_port.y = tile.y;
        for (uint32_t i = 0; i < NUM_TRACK; i++) {
            sb.track = i;
            sb.x = tile.x;
            sb.y = tile.y;

            // out can go any sides
            for (uint32_t side = 0; side < SIDES; side++) {
                g.add_edge(out_port, sb, side);
            }
            // only left or right can come in
            g.add_edge(sb, in_port, 0);
            g.add_edge(sb, in_port, 2);
        }
    }
    // 2. create a global router and do the configuration in order
    GlobalRouter r(20, g);
    // add placement
    map<string, pair<uint32_t, uint32_t >> placement =
            {{"p0", {0, 0}}, {"p1", {0, 1}}, {"p2", {1, 0}}, {"p3", {1, 1}} };
    for (auto const &it : placement) {
        auto [x, y] = it.second;
        r.add_placement(x, y, it.first);
    }

    map<string, vector<pair<string, string>>> netlist =
            {
            {"n1", {{"p0", "out"}, {"p3", "in"}}},
            {"n2", {{"p1", "out"}, {"p2", "in"}}}
            };

    for (const auto &iter: netlist) {
        r.add_net(iter.first, iter.second);
    }

    // route!
    r.route();

    return 0;
}