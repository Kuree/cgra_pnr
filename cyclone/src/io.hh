#ifndef CYCLONE_IO_HH
#define CYCLONE_IO_HH

#include <string>
#include <map>
#include <vector>
#include "graph.hh"
#include "route.hh"

std::pair<std::map<std::string, std::vector<std::pair<std::string,
                                                      std::string>>>,
          std::map<std::string, uint32_t>>
load_netlist(const std::string &filename);

std::map<std::string, std::pair<uint32_t, uint32_t>>
load_placement(const std::string &filename);

void dump_routing_graph(RoutingGraph &graph, const std::string &filename);

RoutingGraph load_routing_graph(const std::string &filename);

void dump_routing_result(const Router &r, const std::string &filename);

void setup_router_input(Router &r, const std::string &packed_filename,
                        const std::string &placement_filename,
                        uint32_t bus_width);

#endif //CYCLONE_IO_HH
