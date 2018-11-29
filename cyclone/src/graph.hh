#ifndef CYCLONE_GRAPH_H
#define CYCLONE_GRAPH_H

#include <set>
#include <memory>
#include <map>
#include <vector>

enum NodeType {
    SwitchBox,
    ConnectionBox,
    Port
};

class Node {
public:
    Node(NodeType type, uint32_t x, uint32_t y);
    Node(NodeType type, uint32_t track, uint32_t x, uint32_t y);
    Node(const std::string &name, uint32_t x, uint32_t y);
    Node(const Node &node);

    NodeType type;
    std::set<int> nets;

    // only valid for ports
    std::string name;
    // only valid for
    uint32_t track;

    uint32_t x;
    uint32_t y;

    std::set<std::shared_ptr<Node>> neighbors;

    void assign_net(const int net_id) { nets.insert(net_id); }
    void rip_up(const int net_id) { nets.erase(net_id); }
};

// operators
bool operator==(const Node &node1, const Node &node2);
bool operator==(const std::shared_ptr<Node> &ptr, const Node &node);


class RoutingGraph {
public:
    RoutingGraph() : grid_() {}

    // used to construct the routing graph
    void add_edge(const Node &node1, const Node &node2);
    std::shared_ptr<Node> get_port_node(const uint32_t &x, const uint32_t &y,
                                        const std::string &name);

    const std::set<std::shared_ptr<Node>> get_nodes(const uint32_t &x,
                                                    const uint32_t &y);

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>,
            std::set<std::shared_ptr<Node>>> grid_;
};


#endif //CYCLONE_GRAPH_H
