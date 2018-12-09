#include <iostream>
#include "../src/graph.hh"
#include "../src/io.hh"

using namespace std;

void print_help(const string &program_name) {
    cerr << "Usage: " << endl;
    cerr << "    " << program_name << " <packed_file>"
         << " <placement_file> <routing_graph_file>" << endl;
}

int main(int argc, char *argv[]) {
    if (argc != 4) {
        print_help(argv[0]);
        return EXIT_FAILURE;
    }
    string packed_filename = argv[1];
    string placement_filename = argv[2];
    string graph_filename = argv[3];
    auto [netlist, track_mode] = load_netlist(packed_filename);
    (void)netlist;
    (void)track_mode;
    auto placement = load_placement(placement_filename);
    (void)placement;
    auto graph = load_routing_graph(graph_filename);
    (void)graph;
    return EXIT_SUCCESS;
}
