#ifndef THUNDER_GRAPH_HH
#define THUNDER_GRAPH_HH

#include <memory>
#include <map>
#include <string>
#include <vector>
#include <set>
#include <igraph/igraph.h>

std::map<uint32_t, std::string>
construct_igraph(igraph_t *graph,
                 const std::map<std::string,
                                std::vector<std::string>> &netlists);

std::map<int, std::set<std::string>>
get_cluster(igraph_t*,
            const std::map<uint32_t, std::string> &id_to_block,
            uint32_t num_iter,
            uint32_t seed);

std::map<int, std::set<std::string>>
partition_netlist(const std::map<std::string,
                                 std::vector<std::string>> &netlists);

#endif //THUNDER_GRAPH_HH
