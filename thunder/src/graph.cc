#include "graph.hh"
#include <igraph/igraph.h>
#include <stack>

#include <utility>
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
get_cluster(igraph_t *graph,
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

    Edge *Graph::connect(Node *from, Node *to) {
        edges_.emplace_back(std::make_unique<Edge>());
        auto edge = edges_.back().get();
        edge->weight = 0;
        edge->from = from;
        edge->to = to;
        from->edges_to.emplace(edge);
        return edge;
    }

    void Graph::copy(Graph &g) const {
        std::unordered_map<Node *, Node *> map;
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


    Graph::Graph(std::map<int, std::set<std::string>> clusters,
                 std::map<std::string, std::vector<std::pair<std::string, std::string>>> netlist) : clusters_(std::move(
            clusters)), netlist_(std::move(netlist)) {
        update();
    }

    void Graph::update() {
        edges_.clear();
        nodes_.clear();

        std::unordered_map<std::string, Node *> node_map;
        for (auto const &[cluster_id, cluster]: clusters_) {
            auto n = get_node();
            n->id = cluster_id;
            for (auto const &blk: cluster) {
                node_map.emplace(blk, n);
            }
            n->size = cluster.size();
        }

        // construct connections
        std::map<std::pair<Node *, Node *>, Edge *> edge_map;
        for (auto const &iter: netlist_) {
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
        for (auto &node: nodes_) {
            auto src = node.get();
            std::queue<Node *> working_set;
            std::unordered_set<Node *> visited;

            working_set.emplace(src);

            while (!working_set.empty()) {
                auto n = working_set.front();
                working_set.pop();
                if (visited.find(n) != visited.end())
                    continue;
                visited.emplace(n);
                for (auto const &e: n->edges_to) {
                    if (e->to == src)
                        return true;
                    working_set.emplace(e->to);
                }
            }
        }

        return false;
    }

    void topological_sort_(Node *node, std::unordered_set<Node*> &visited, std::stack<Node*> &stack) {
        visited.emplace(node);
        for (auto *edge: node->edges_to) {
            auto *to = edge->to;
            if (visited.find(to) == visited.end()) {
                topological_sort_(to, visited, stack);
            }
        }
        stack.emplace(node);
    }

    int Graph::total_weight() const {
        int result = 0;
        for (auto const &edge: edges_) {
            result += edge->weight;
        }
        return result;
    }

    std::vector<int> Graph::topological_sort() const {
        std::unordered_set<Node*> visited;
        std::stack<Node*> stack;

        for (auto const &n: nodes_) {
            if (visited.find(n.get()) == visited.end()) {
                topological_sort_(n.get(), visited, stack);
            }
        }
        std::vector<int> result;
        result.reserve(stack.size());
        while (!stack.empty()) {
            auto n = stack.top();
            result.emplace_back(n->id);
            stack.pop();
        }
        return result;
    }

    std::vector<Node *> Graph::find_loop_path(Node *start) {
        // this is brute-force
        // which is fine since the graph is always small
        std::unordered_map<Node *, Node *> path;
        std::unordered_set<Node *> visited;
        std::queue<Node *> working_set;
        working_set.emplace(start);

        while (!working_set.empty()) {
            auto node = working_set.front();
            working_set.pop();
            if (visited.find(node) != visited.end()) {
                if (node == start) {
                    // that is the path
                    std::vector<Node *> result = {node};
                    Node *n = start;
                    while (path.find(n) != path.end()) {
                        n = path.at(n);
                        if (n == start) break;
                        result.emplace_back(n);
                    }
                    return result;
                } else {
                    continue;
                }
            } else {
                visited.emplace(node);
                for (auto *e: node->edges_to) {
                    auto *n = e->to;
                    path.emplace(n, node);
                    working_set.emplace(n);
                }
            }
        }
        return {};
    }

    void Graph::merge(int base, int target) {
        for (auto &blk: clusters_.at(target)) {
            clusters_.at(base).emplace(blk);
        }
        clusters_.erase(target);
    }

    void Graph::merge() {
        // need to find a loop
        while (has_loop()) {
            for (auto &n: nodes_) {
                auto path = find_loop_path(n.get());
                if (!path.empty()) {
                    // need to merge all the nodes along the path
                    auto src = path[0];
                    for (uint64_t i = 1; i < path.size(); i++) {
                        auto dst = path[i];
                        merge(src->id, dst->id);
                    }
                    update();
                    break;
                }
            }
        }

        fix_cluster_id();
    }

    void Graph::merge(uint32_t max_size) {
        while (true) {
            uint64_t old_cluster_size = clusters_.size();
            // need to make sure that each cluster is within the max size
            for (auto const &cluster: clusters_) {
                if (cluster.second.size() > max_size)
                    throw std::runtime_error(
                            "Unable to partition the graph that fits the max size " + std::to_string(max_size));
            }
            // now we pick the edge with highest connection count
            // if it legal to merge
            //     1. no loop introduced
            //     2. the new size does not exceed the max size
            // sort the edges by their weight (num of connections)
            std::vector<Edge *> edges;
            edges.reserve(edges_.size());
            for (auto &edge: edges_) edges.emplace_back(edge.get());

            // from hi to lo
            std::sort(edges.begin(), edges.end(), [](auto a, auto b) { return a->weight > b->weight; });

            for (auto *edge: edges) {
                // cannot exceed max size
                if (clusters_.at(edge->from->id).size() + clusters_.at(edge->to->id).size() > max_size)
                    continue;
                // only merge if it can decrease the total number of edge weights
                int total_weights_before = 0;
                for (auto const &e: edges_) {
                    total_weights_before += e->weight;
                }
                // need to create a new graph and then merge these two, then see if it's valid
                Graph g(clusters_, netlist_);
                g.merge(edge->from->id, edge->to->id);
                g.update();
                int total_weights_after = 0;
                for (auto const &e: g.edges_) {
                    total_weights_after += e->weight;
                }
                if (!g.has_loop() && total_weights_after <= total_weights_before) {
                    clusters_ = g.clusters_;
                    update();
                    break;
                }

            }
            if (old_cluster_size == clusters_.size())
                break;
        }
        fix_cluster_id();
        update();
    }

    void Graph::fix_cluster_id() {
        std::map<int, std::set<std::string>> result;
        for (auto const &iter: clusters_) {
            result.emplace(result.size(), iter.second);
        }

        clusters_ = result;
        update();
    }

    std::map<int, std::set<std::string>> copy_cluster(const std::map<int, std::set<std::string>> &cluster) {
        std::map<int, std::set<std::string>> result;
        for (auto const &[id, c]: cluster) {
            std::set<std::string> c_copy;
            for (auto const &blk: c) c_copy.emplace(blk);
            result.emplace(id, c_copy);
        }
        return result;
    }

    void Graph::optimize(uint32_t max_partition_size) {
        // if max_size not set, set it to maximum
        if (max_partition_size == 0) max_partition_size = 0xFFFFFFFF;
        // move nodes around to see if it can actually reduce the number of virtualized IOs
        while (true) {
            auto old_clusters = copy_cluster(clusters_);

            // need to find out all the edges
            int total_weights = total_weight();
            // find interested pairs
            // notice that
            std::vector<std::pair<std::string, std::map<int, int>>> blks;
            for (auto const &iter: netlist_) {
                auto const &net = iter.second;
                auto const &src_blk = net[0].first;
                int src_id = 0;
                for (auto const &[c_id, cluster]: clusters_) {
                    if (cluster.find(src_blk) != cluster.end()) {
                        src_id = c_id;
                        break;
                    }
                }
                std::map<int, int> targets;
                for (uint64_t i = 1; i < net.size(); i++) {
                    auto const &sink_blk = net[i].first;
                    int sink_id = 0;
                    for (auto const &[c_id, cluster]: clusters_) {
                        if (cluster.find(sink_blk) != cluster.end()) {
                            sink_id = c_id;
                            break;
                        }
                    }
                    if (sink_id != src_id) {
                        // need to add it to the
                        if (targets.find(sink_id) != targets.end())
                            targets.emplace(sink_id, 0);
                        targets[sink_id] += 1;
                    }
                }
                if (!targets.empty()) {
                    // we only interested in connection that has more than 1
                    for (auto const &count: targets) {
                        if (count.second > 1) {
                            blks.emplace_back(std::make_pair(src_blk, targets));
                            break;
                        }
                    }

                }
            }
            // sort the blks based on the number of clusters
            std::sort(blks.begin(), blks.end(), [](const auto &a, const auto &b) {
                auto const &a_edges = a.second;
                auto const &b_edges = b.second;
                int a_sum = 0, b_sum = 0;
                for (auto const &iter: a_edges) {
                    a_sum += iter.second;
                }
                for (auto const &iter: b_edges) {
                    b_sum += iter.second;
                }
                return a_sum > b_sum;
            });
            for (auto const &[blk, edges]: blks) {
                // figure out which target to merge into
                int c_id = -1, max_size = -1;
                for (auto const &[c, count]: edges) {
                    if (count > max_size) {
                        max_size = count;
                        c_id = c;
                    }
                }
                if (c_id < 0) throw std::runtime_error("Incorrect state in merging");

                // try to move the blk to the target cluster
                auto temp = copy_cluster(clusters_);
                for (auto &iter: temp) {
                    auto &cluster = iter.second;
                    if (cluster.find(blk) != cluster.end()) {
                        cluster.erase(blk);
                        break;
                    }
                }
                auto &target_c = temp.at(c_id);
                target_c.emplace(blk);
                Graph g(temp, netlist_);
                auto new_weight = g.total_weight();
                if (new_weight < total_weights && target_c.size() < max_partition_size) {
                    clusters_ = temp;
                    update();
                }
            }

            // logic to detect if we have made any changes
            bool changed = false;
            for (auto const &[c_id, cluster]: clusters_) {
                if (changed) break;
                if (old_clusters.find(c_id) != old_clusters.end()) {
                    auto const &new_cluster = clusters_.at(c_id);
                    auto const &old_cluster = old_clusters.at(c_id);
                    if (new_cluster.size() != old_cluster.size()) {
                        changed = true;
                    } else {
                        for (auto const &blk: cluster) {
                            if (new_cluster.find(blk) == old_cluster.end()) {
                                changed = true;
                                break;
                            }
                        }
                    }
                }
            }

            if (!changed) {
                break;
            }
        }
    }
}