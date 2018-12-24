#include <iostream>
#include "../src/global.hh"
#include "../src/util.hh"
#include "../src/io.hh"

#define WIDTH 1
#define NUM_TRACK 2
#define SIDES 4
#define SIZE 2
#define SWITCH_ID 0

using std::map;
using std::pair;
using std::string;
using std::vector;
using std::cout;
using std::endl;

constexpr auto gsi = get_side_int;
constexpr auto gii = get_io_int;

int main(int argc, char *argv[]) {
    // 1. construct routing graph with standard switch box
    Switch switchbox(0, 0, NUM_TRACK, WIDTH, SWITCH_ID,
                     get_disjoint_sb_wires(NUM_TRACK));
    // 2 x 2 board with 2 routing tracks
    RoutingGraph g(SIZE, SIZE, switchbox);
    // each tile has 2 ports, "in" and "out"
    PortNode in_port("in", 0, 0, WIDTH);
    PortNode out_port("out", 0, 0, WIDTH);
    // placeholder for sb
    SwitchBoxNode sb(0, 0, WIDTH, 0, SwitchBoxSide::Bottom,
                     SwitchBoxIO::SB_IN);
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
                sb.side = gsi(side);
                sb.io = SwitchBoxIO::SB_OUT;
                g.add_edge(out_port, sb);
            }
            // only left or right can come in
            for (uint32_t io = 0; io < Switch::IOS; io++) {
                sb.io = gii(io);
                sb.side = SwitchBoxSide::Left;
                g.add_edge(sb, in_port);
                sb.side = SwitchBoxSide::Right;
                g.add_edge(sb, in_port);
            }
        }
    }

    // wire these switch boxes together
    for (uint32_t y = 0; y < SIZE - 1; y++) {
        // connect from top to bottom and bottom to top
        for (uint32_t x = 0; x < SIZE; x++) {
            for (uint32_t track = 0; track < NUM_TRACK; track++) {
                SwitchBoxNode sb_top(x, y, WIDTH, track,
                                     SwitchBoxSide::Bottom,
                                     SwitchBoxIO::SB_OUT);
                SwitchBoxNode sb_bottom(x, y + 1, WIDTH, track,
                                        SwitchBoxSide::Top,
                                        SwitchBoxIO::SB_IN);
                g.add_edge(sb_top, sb_bottom);

                sb_bottom.io = SwitchBoxIO::SB_OUT;
                sb_top.io = SwitchBoxIO::SB_IN;
                g.add_edge(sb_bottom, sb_top);
            }
        }
    }

    for (uint32_t y = 0; y < SIZE; y++) {
        // connect from left to right and right to left
        for (uint32_t x = 0; x < SIZE - 1; x++) {
            for (uint32_t track = 0; track < NUM_TRACK; track++) {
                SwitchBoxNode sb_left(x, y, WIDTH, track,
                                      SwitchBoxSide::Right,
                                      SwitchBoxIO::SB_OUT);
                SwitchBoxNode sb_right(x + 1, y, WIDTH, track,
                                       SwitchBoxSide::Left,
                                       SwitchBoxIO::SB_IN);
                g.add_edge(sb_left, sb_right);

                sb_right.io = SwitchBoxIO::SB_OUT;
                sb_left.io = SwitchBoxIO::SB_IN;
                g.add_edge(sb_right, sb_left);
            }
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

    // save the routing graph
    if (argc > 1) {
        cout << "dump routing graph to " << argv[1] << endl;
        dump_routing_graph(g, argv[1]);
    }

    return 0;
}