#include <iostream>
#include "../src/graph.hh"
#include "../src/io.hh"
#include "../src/global.hh"

using namespace std;

void print_help(const string &program_name) {
    cerr << "Usage: " << endl;
    cerr << "    " << program_name << " <packed_file>"
         << " <placement_file> <bit_width> <routing_graph_file> ... "
            "<routing_result.route>" << endl;
}

int main(int argc, char *argv[]) {
    if (argc < 6 || (argc - 4) % 2 != 0) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    string packed_filename = argv[1];
    string placement_filename = argv[2];

    auto [netlist, track_mode] = load_netlist(packed_filename);
    auto placement = load_placement(placement_filename);
    auto output_file = argv[argc - 1];

    for (int arg_index = 3; arg_index < argc - 1; arg_index += 2) {
        uint32_t bit_width = static_cast<uint32_t>(stoi(argv[arg_index]));
        string graph_filename = argv[arg_index + 1];
        cout << "using bit_width " << bit_width << endl;
        auto graph = load_routing_graph(graph_filename);

        // set up the router
        GlobalRouter r(100, graph);
        for (auto const &it : placement) {
            auto[x, y] = it.second;
            r.add_placement(x, y, it.first);
        }

        for (const auto &iter: netlist) {
            // Note
            // we only route 1bit at this time
            if (track_mode.at(iter.first) == bit_width)
                r.add_net(iter.first, iter.second);
        }

        r.route();

        dump_routing_result(r, output_file);

    }
    return EXIT_SUCCESS;
}
