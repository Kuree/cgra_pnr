#include "../src/global.hh"
#include "../src/graph.hh"
#include "../src/io.hh"
#include <cstdio>
#include <fstream>
#include <iostream>

using namespace std;

constexpr double power_domain_cost = 5;

inline bool exists(const std::string &filename) {
    std::ifstream in(filename);
    return in.good();
}

void print_help(const string &program_name) {
    cerr << "Usage: " << endl;
    cerr << "    " << program_name << " [--pd] <packed_file>"
         << " <placement_file> <bit_width> <routing_graph_file> ... "
            "<routing_result.route>"
         << endl;
}

bool process_args(int argc, char *argv[], ::vector<::string> &args) {
    bool pd_aware = false;
    args.reserve(argc - 1);
    for (int i = 0; i < argc; i++) {
        ::string value = argv[i];
        if (value != "--pd") {
            args.emplace_back(value);
        } else {
            pd_aware = true;
        }
    }

    return pd_aware;
}

void
adjust_node_cost_power_domain(RoutingGraph *graph,
                              const std::map<std::string, std::pair<int, int>> &placement_result) {
    ::set<std::pair<uint32_t, uint32_t>> locations;
    for (auto const &iter: placement_result) {
        locations.emplace(iter.second);
    }

    // adjust the nodes cost, if any node is not on the placed tiles, we increase the cost
    for (auto const &[loc, tile]: *graph) {
        if (locations.find(loc) == locations.end()) {
            // increase the cost for all nodes
            auto switchbox = tile.switchbox;
            for (uint32_t i = 0; i < 4; i++) {
                auto sbs = switchbox.get_sbs_by_side(SwitchBoxSide(i));
                for (const auto& sb: sbs) {
                    sb->delay = power_domain_cost;
                }
            }
        }
    }
}

int main(int argc, char *argv[]) {
    if (argc < 6) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    ::vector<::string> args;
    bool power_domain = process_args(argc, argv, args);

    string packed_filename = args[1];
    string placement_filename = args[2];
    // reassign the size
    argc = args.size();

    auto[netlist, track_mode] = load_netlist(packed_filename);
    auto placement = load_placement(placement_filename);
    auto output_file = args[argc - 1];

    // delete the old file if exists
    if (exists(output_file)) {
        if (std::remove(output_file.c_str())) {
            cerr << "Unable to clear output file" << endl;
            return EXIT_FAILURE;
        }
    }

    for (int arg_index = 3; arg_index < argc - 1; arg_index += 2) {
        auto bit_width = static_cast<uint32_t>(stoi(args[arg_index]));
        string graph_filename = args[arg_index + 1];
        cout << "using bit_width " << bit_width << endl;
        auto graph = load_routing_graph(graph_filename);

        // adjust the node cost
        if (power_domain) {
            cout << "Adjusting power domain cost for bit_width " << bit_width << endl;
            adjust_node_cost_power_domain(&graph, placement);
        }

        // set up the router
        GlobalRouter r(100, graph);
        for (auto const &it : placement) {
            auto[x, y] = it.second;
            r.add_placement(x, y, it.first);
        }

        for (const auto &iter : netlist) {
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
