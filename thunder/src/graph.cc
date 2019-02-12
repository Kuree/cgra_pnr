#include "graph.hh"
#include "../lib/leidenalg/include/ModularityVertexPartition.h"
#include "../lib/leidenalg/include/GraphHelper.h"
#include "../lib/leidenalg/include/Optimiser.h"

std::map<uint32_t, std::string>
construct_igraph(igraph_t *graph,
                 const std::map<std::string,
                                std::vector<std::string>> &netlists) {
    std::map<std::string, uint32_t> blk_to_id;
    std::map<uint32_t, std::string> id_to_block;
    for (auto const &iter: netlists) {
        for (auto const &blk_id: iter.second) {
            if (blk_to_id.find(blk_id) == blk_to_id.end()) {
                auto node_id = static_cast<uint32_t>(blk_to_id.size());
                blk_to_id.insert({blk_id, node_id});
                id_to_block.insert({node_id, blk_id});
            }
        }
    }
    // construct the graph
    auto num_blks = static_cast<uint32_t >(blk_to_id.size());
    igraph_empty(graph, num_blks, true);
    // add edges
    for (auto const &iter: netlists) {
        auto const &net = iter.second;
        auto const &src_node = net[0];
        auto const src_id = blk_to_id.at(src_node);
        for (uint32_t i = 1; i < net.size(); i++) {
            auto const &dst_node = net[i];
            auto const dst_id = blk_to_id.at(dst_node);
            igraph_add_edge(graph, src_id, dst_id);
        }
    }

    return id_to_block;
}

std::map<int, std::set<std::string>>
get_cluster(igraph_t* graph,
            const std::map<uint32_t, std::string> &id_to_block,
            uint32_t num_iter,
            uint32_t seed) {

    auto g = Graph(graph, false);

    auto partition = ModularityVertexPartition(&g);
    auto opt = Optimiser();

    opt.set_rng_seed(seed);
    // we have to implement the optimizer (in python) here
    for (uint32_t i = 0; i < num_iter; i++) {
        opt.optimise_partition(&partition);
    }

    const auto &membership = partition.membership();
    std::map<int, std::set<std::string>> result;

    for (const auto &[g_id, blk_id]: id_to_block) {
        auto const cluster_id = membership[g_id];
        result[cluster_id].insert(blk_id);
    }

    return result;
}

std::map<int, std::set<std::string>>
partition_netlist(const std::map<std::string,
        std::vector<std::string>> &netlists) {
    igraph_t graph;
    auto const &id_to_blk = construct_igraph(&graph, netlists);
    const auto &result = get_cluster(&graph, id_to_blk, 15, 0);
    igraph_destroy(&graph);
    return result;
}