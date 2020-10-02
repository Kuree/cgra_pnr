#include "graph.hh"
#include <igraph/igraph.h>
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
                                 std::vector<std::string>> &netlists,
                  uint32_t num_iter) {
    igraph_t graph;
    auto const &id_to_blk = construct_igraph(&graph, netlists);
    const auto &result = get_cluster(&graph, id_to_blk, num_iter, 0);
    igraph_destroy(&graph);
    return result;
}

namespace graph {
    Node *Graph::get_node() {
        nodes_.emplace_back(std::make_unique<Node>());
        auto node = nodes_.back().get();
        node->id = 0;
        node->size = 0;
        return node;
    }

    Edge * Graph::connect(Node *from, Node *to) {
        edges_.emplace_back(std::make_unique<Edge>());
        auto edge = edges_.back().get();
        edge->weight = 0;
        edge->from = from;
        edge->to = to;
        from->edges_to.emplace(edge);
        return edge;
    }

    void Graph::copy(Graph &g) const {
        std::unordered_map<Node*, Node*> map;
        for (auto const &n: nodes_) {
            auto nn = g.get_node();
            map.emplace(n.get(), nn);
        }
        for (auto const &e: edges_) {
            auto from = map.at(e->from);
            auto to = map.at(e->to);
            auto ee = g.connect(from, to);
            ee->weight = e->weight;
        }
    }


    Graph::Graph(const std::map<int, std::set<std::string>> &clusters,
                 const std::map<std::string, std::vector<std::pair<std::string, std::string>>> &netlist) {
        std::unordered_map<std::string, Node*> node_map;
        for (auto const &[cluster_id, cluster]: clusters) {
            auto n = get_node();
            n->id = cluster_id;
            for (auto const &blk: cluster) {
                node_map.emplace(blk, n);
            }
            n->size = cluster.size();
        }

        // construct connections
        std::map<std::pair<Node *, Node*>, Edge*> edge_map;
        for (auto const &iter: netlist) {
            auto const &net = iter.second;
            auto const &src = net[0].first;
            auto src_node = node_map.at(src);
            for (uint64_t i = 1; i < net.size(); i++) {
                auto const &sink = net[i].first;
                if (node_map.at(sink) == node_map.at(src))
                    continue;
                auto sink_node = node_map.at(sink);
                Edge *edge;
                auto src_sink = std::make_pair(src_node, sink_node);
                if (edge_map.find(src_sink) == edge_map.end()) {
                    edge = connect(src_node, sink_node);
                    edge_map.emplace(src_sink, edge);
                } else {
                    edge = edge_map.at(src_sink);
                }
                edge->weight += 1;
            }
        }
        // make sure it is correct
        for (auto const &n: nodes_) {
            for (auto const &e: n->edges_to) {
                if (e->to == n.get()) {
                    throw std::runtime_error("Invalid graph for reduction");
                }
            }
        }
    }

    bool Graph::has_loop() const {
        std::unordered_set<Node*> srcs;
        // since we don't keep track of edges from
        // need to figure out where it starts
        std::unordered_set<Node*> sinks;
        for (auto const &e: edges_) {
            sinks.emplace(e->to);
        }
        for (auto const &n: nodes_) {
            if (sinks.find(n.get()) == sinks.end()) {
                srcs.emplace(n.get());
            }
        }
        if (srcs.empty())
            throw std::runtime_error("Graph doesn't not have an input");

        for (auto *src: srcs) {
            std::queue<Node*> working_set;
            std::unordered_set<Node*> visited;

            working_set.emplace(src);

            while (!working_set.empty()) {
                auto n = working_set.front();
                working_set.pop();
                if (visited.find(n) != visited.end())
                    return true;
                visited.emplace(n);
                for (auto const &e: n->edges_to) {
                    working_set.emplace(e->to);
                }
            }
        }

        return false;
    }
}