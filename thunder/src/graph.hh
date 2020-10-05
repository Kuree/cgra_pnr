#ifndef THUNDER_GRAPH_HH
#define THUNDER_GRAPH_HH

#include <memory>
#include <map>
#include <string>
#include <vector>
#include <set>
#include <queue>
#include <unordered_map>
#include <unordered_set>


std::map<int, std::set<std::string>>
partition_netlist(const std::map<std::string,
                                 std::vector<std::string>> &netlists,
                  uint32_t num_iter = 15);

namespace graph {
    struct Edge;
    struct Node {
        int id;
        uint32_t size;
        std::unordered_set<Edge*> edges_to;
    };

    struct Edge {
        Node *from;
        Node *to;
        int weight;
    };

    class Graph {
    public:
        Graph() = default;
        Graph(std::map<int, std::set<std::string>> clusters,
              std::map<std::string, std::vector<std::pair<std::string, std::string>>> netlist);
        void merge(uint32_t max_size);
        void merge();
        void merge(int base, int target);
        Node *get_node();
        Edge *connect(Node *from, Node *to);
        void copy(Graph &g) const;
        bool has_loop() const;
        [[nodiscard]]
        const std::map<int, std::set<std::string>> &clusters() const { return clusters_; }
        [[nodiscard]]
        std::vector<int> topological_sort() const;

    private:
        std::vector<std::unique_ptr<Node>> nodes_;
        std::vector<std::unique_ptr<Edge>> edges_;

        std::map<int, std::set<std::string>> clusters_;
        std::map<std::string, std::vector<std::pair<std::string, std::string>>> netlist_;

        static std::vector<Node *> find_loop_path(Node *start);
        void update();
        void fix_cluster_id();
    };
}

#endif //THUNDER_GRAPH_HH
