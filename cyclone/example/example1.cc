#include <iostream>
#include "../src/global.hh"
#include "../src/util.hh"
#include "../src/io.hh"

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
using std::set;
using std::shared_ptr;

constexpr auto gsi = get_side_int;

::set<::pair<uint32_t, uint32_t>>
get_nearby_tiles(const Tile &t, RoutingGraph &g) {
    // brute force to compute the distance
    ::set<::pair<uint32_t, uint32_t>> tiles;
    for (const auto &tile_iter : g) {
        const auto &xy = tile_iter.first;
        int dist = abs(static_cast<int>(t.x) - static_cast<int>(xy.first)) +
                   abs(static_cast<int>(t.y) - static_cast<int>(xy.second));
        if (dist == 1)
            tiles.insert(xy);
    }
    return tiles;
}

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

            // out can go any sides, that is to the tiles nearby
            // so we wire the switch box as well
            for (uint32_t side = 0; side < SIDES; side++) {
                for (auto const xy : get_nearby_tiles(tile, g)) {
                    sb.x = xy.first;
                    sb.y = xy.second;
                    g.add_edge(out_port, sb, gsi(side));
                    for (auto const new_xy : get_nearby_tiles(g[xy], g)) {
                        auto new_sb = SwitchBoxNode(sb);
                        new_sb.x = new_xy.first;
                        new_sb.y = new_xy.second;

                        for (uint32_t chan = 0; chan < NUM_TRACK; chan++) {
                            sb.track = chan;
                            new_sb.track = chan;
                            g.add_edge(out_port, sb, new_sb, gsi(side));
                        }
                    }

                }
            }
            // only left or right can come in
            sb.x = tile.x;
            sb.y = tile.y;
            auto new_sb = SwitchBoxNode(sb);
            for (auto const xy : get_nearby_tiles(tile, g)) {
                new_sb.x = xy.first;
                new_sb.y = xy.second;

                g.add_edge(new_sb, sb, in_port, SwitchBoxSide::Left);
                g.add_edge(new_sb, sb, in_port, SwitchBoxSide::Right);
            }
        }
    }

    dump_routing_graph(g, "test.graph");

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
            {"n4", {{"p2", "out"}, {"p1", "in"}}}
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