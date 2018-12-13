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
using std::cerr;
using std::endl;


int main(int argc, char *argv[]) {
    // load the graph from command line
    if (argc < 1) {
        cerr << "Usage: " << argv[0] << " <routing.graph>" << endl;
        return EXIT_FAILURE;
    }

    cout << "load routing graph from " << argv[1] << endl;
    auto g = load_routing_graph(argv[1]);

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