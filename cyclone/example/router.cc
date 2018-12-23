#include <iostream>
#include "../src/graph.hh"
#include "../src/io.hh"
#include "../src/global.hh"

using namespace std;

void print_help(const string &program_name) {
    cerr << "Usage: " << endl;
    cerr << "    " << program_name << " <packed_file>"
         << " <placement_file> <routing_graph_file> <bit_width> "
            "[routing_result.route]" << endl;
}

int main(int argc, char *argv[]) {
    if (argc < 5) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    string packed_filename = argv[1];
    string placement_filename = argv[2];
    string graph_filename = argv[3];
    uint32_t bit_width = static_cast<uint32_t>(stoi(argv[4]));
    cout << "using bit_width " << bit_width << endl;
    auto [netlist, track_mode] = load_netlist(packed_filename);
    auto placement = load_placement(placement_filename);
    auto graph = load_routing_graph(graph_filename);

    // set up the router
    GlobalRouter r(100, graph);
    for (auto const &it : placement) {
        auto [x, y] = it.second;
        r.add_placement(x, y, it.first);
    }

    for (const auto &iter: netlist) {
        // Note
        // we only route 1bit at this time
        if (track_mode.at(iter.first) == bit_width)
            r.add_net(iter.first, iter.second);
    }

    r.route();

    if (argc > 5) {
        cout << "saving routing result to " << argv[5] << endl;
        dump_routing_result(r, argv[5]);
    }

    return EXIT_SUCCESS;
}
