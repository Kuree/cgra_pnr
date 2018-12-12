#include <iostream>
#include "../src/global.hh"
#include "../src/util.hh"

#define WIDTH 1
#define NUM_TRACK 2
#define SIDES 4
#define SIZE 2

using std::map;
using std::pair;
using std::string;
using std::vector;
using std::cout;
using std::endl;

constexpr auto gsi = get_side_int;

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
                g.add_edge(out_port, sb, gsi(side));
            }
            // only left or right can come in
            g.add_edge(sb, in_port, SwitchBoxSide::Left);
            g.add_edge(sb, in_port, SwitchBoxSide::Right);
        }
    }

    // wire these switch boxes together
    for (uint32_t chan = 0; chan < NUM_TRACK; chan++) {
        auto sb0 = g[{0, 0}].sbs[chan];
        auto sb1 = g[{0, 1}].sbs[chan];
        auto sb2 = g[{1, 0}].sbs[chan];
        auto sb3 = g[{1, 1}].sbs[chan];

        g.add_edge(*sb0, *sb1, SwitchBoxSide::Left);
        g.add_edge(*sb1, *sb0, SwitchBoxSide::Right);

        g.add_edge(*sb0, *sb2, SwitchBoxSide::Bottom);
        g.add_edge(*sb2, *sb0, SwitchBoxSide::Top);

        g.add_edge(*sb3, *sb1, SwitchBoxSide::Top);
        g.add_edge(*sb1, *sb3, SwitchBoxSide::Bottom);

        g.add_edge(*sb3, *sb2, SwitchBoxSide::Right);
        g.add_edge(*sb2, *sb3, SwitchBoxSide::Left);
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
            {"n2", {{"p1", "out"}, {"p0", "in"}}},
            {"n3", {{"p3", "out"}, {"p2", "in"}}},
            };

    for (const auto &iter: netlist) {
        r.add_net(iter.first, iter.second);
    }

    // route!
    r.route();

    auto result = r.realize();
    for (auto const &iter: result) {
        cout << "Net: " << iter.first << endl;
        for (auto const &seg : iter.second) {
            for (uint32_t i = 0; i < seg.size(); i++) {
                cout << *seg[i] << (i == seg.size() - 1 ? "" : " -> ");
            }
            cout << endl;
        }
        cout << endl;
    }

    return 0;
}