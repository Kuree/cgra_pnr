#include "../src/global.hh"
#include "../src/io.hh"
#include "../src/timing.hh"
#include <cstdio>
#include <fstream>
#include <iostream>
#include <filesystem>
#include "argparse/argparse.hpp"

using namespace std;

constexpr double power_domain_cost = 5;

inline bool exists(const std::string &filename) {
    std::ifstream in(filename);
    return in.good();
}

void setup_argparse(argparse::ArgumentParser &parser) {
    parser.add_argument("--pd").help("If set, will use PD-oriented routing strategy").default_value(
            false).implicit_value(true);
    parser.add_argument("-p", "--packed").help("Packed netlist file").required();
    parser.add_argument("-P", "--placement").help("Placement file").required();
    parser.add_argument("-o", "-r", "--route").help("Routing result").required();
    parser.add_argument("-g").help("Routing graph information").required().append();
    parser.add_argument("-l", "--layout").help("Chip layout").default_value("");
    parser.add_argument("-f", "--frequency").help("Minimum frequency in MHz").default_value<uint64_t>(100)
            .action([](const std::string &value) -> uint64_t { return std::stoull(value); });
    parser.add_argument("-w").help("Wave information file after retiming").default_value<std::string>("");
    parser.add_argument("-t", "--retime").help(
            "Set timing file. Default is none, which turns off re-timing. "
            "Set to default to use the default timing information, register just to shifting registers").default_value<std::string>(
            "none");
}

struct RouterInput {
    bool pd = false;
    std::string packed_filename;
    std::string placement_filename;
    std::string output_file;
    std::vector<std::pair<uint32_t, std::string>> graph_info;
    std::string timing_file;
    std::string chip_layout;
    std::string timing_result_filename;
    uint64_t min_frequency = 200;
};

std::optional<RouterInput> parse_args(int argc, char *argv[]) {
    argparse::ArgumentParser parser("CGRA Router");
    setup_argparse(parser);

    try {
        parser.parse_args(argc, argv);
    }
    catch (const std::runtime_error &err) {
        std::cerr << err.what() << std::endl;
        std::cerr << parser;
        return std::nullopt;
    }
    // fill out information
    RouterInput result;
    result.pd = parser["--pd"] == true;
    result.packed_filename = parser.get<std::string>("-p");
    result.placement_filename = parser.get<std::string>("-P");
    result.output_file = parser.get<std::string>("-o");
    auto values = parser.get<std::vector<std::string>>("-g");
    for (auto const &value: values) {
        std::string name = std::filesystem::path(value).filename();
        auto bit_width_str = name.substr(name.find_first_not_of('.'));
        auto bit_width = std::stoul(bit_width_str);
        result.graph_info.emplace_back(std::make_pair(bit_width, value));
    }

    auto timing_file = parser.get<std::string>("-t");
    if (timing_file != "none") {
        auto layout = parser.get<std::string>("-l");
        if (layout.empty()) {
            std::cerr << "When re-timing is specified, layout file is required" << std::endl;
            std::cerr << parser << std::endl;
            return std::nullopt;
        }
        result.chip_layout = layout;
    }
    result.timing_file = timing_file;
    result.min_frequency = parser.get<uint64_t>("-f");
    result.timing_result_filename = parser.get<std::string>("-w");

    return result;
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
                for (const auto &sb: sbs) {
                    sb->delay = power_domain_cost;
                }
            }
        }
    }
}

void retime_router(std::map<uint32_t, std::unique_ptr<Router>> &routers, const RouterInput &args) {
    const auto &timing_file = args.timing_file;
    if (timing_file == "none") {
        return;
    } else if (timing_file == "default" || timing_file == "register") {
        auto const &layout_file = args.chip_layout;
        TimingAnalysis timing(routers);
        timing.set_minimum_frequency(args.min_frequency);
        timing.set_timing_cost(get_default_timing_info());
        timing.set_layout(layout_file);
        if (timing_file == "register") {
            timing.adjust_pipeline_registers();
        } else {
            timing.retime();
            // whether to save the timing result or not
            auto const &filename = args.timing_result_filename;
            if (!filename.empty()) {
                timing.save_wave_info(filename);
            }
        }
    } else {
        throw std::runtime_error("Timing file not implemented");
    }
}

int main(int argc, char *argv[]) {
    auto args_opt = parse_args(argc, argv);
    if (!args_opt) {
        return EXIT_FAILURE;
    }
    auto const &args = *args_opt;

    bool power_domain = args.pd;
    const auto &packed_filename = args.packed_filename;
    auto const &placement_filename = args.placement_filename;

    auto[netlist, track_mode] = load_netlist(packed_filename);
    auto placement = load_placement(placement_filename);
    auto output_file = args.output_file;

    // delete the old file if exists
    if (exists(output_file)) {
        if (std::remove(output_file.c_str())) {
            cerr << "Unable to clear output file" << endl;
            return EXIT_FAILURE;
        }
    }

    std::map<uint32_t, std::unique_ptr<Router>> routers;
    for (auto const &[bit_width, graph_filename]: args.graph_info) {
        cout << "using bit_width " << bit_width << endl;
        auto graph = load_routing_graph(graph_filename);

        // adjust the node cost
        if (power_domain) {
            cout << "Adjusting power domain cost for bit_width " << bit_width << endl;
            adjust_node_cost_power_domain(&graph, placement);
        }

        // set up the router
        auto r = std::make_unique<GlobalRouter>(100, graph);
        for (auto const &it: placement) {
            auto[x, y] = it.second;
            r->add_placement(x, y, it.first);
        }

        for (const auto &iter: netlist) {
            // Note
            // we only route 1bit at this time
            if (track_mode.at(iter.first) == bit_width)
                r->add_net(iter.first, iter.second);
        }

        r->route();

        routers.emplace(bit_width, std::move(r));
    }

    retime_router(routers, args);

    for (auto const &iter: routers) {
        dump_routing_result(*iter.second, output_file);
    }

    return EXIT_SUCCESS;
}
