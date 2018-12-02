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

    // only valid for ports. if a reg is placed on it, the name will be blk_id
    std::string name;
    // only valid for switch box and connection box
    uint32_t track;
    uint32_t width = 0;

    uint32_t x;
    uint32_t y;

    void assign_net(const int net_id) { nets.insert(net_id); }
    void rip_up(const int net_id) { nets.erase(net_id); }
    bool overflow() const { return nets.size() > 1; }
    void add_edge(const std::shared_ptr<Node> &node, uint32_t cost);
    void add_edge(const std::shared_ptr<Node> &node) { add_edge(node, 1); }
    uint32_t get_cost(const std::shared_ptr<Node> &node);

    // helper function to allow iteration
    std::set<std::shared_ptr<Node>>::iterator begin()
    { return neighbors_.begin(); }
    std::set<std::shared_ptr<Node>>::iterator end() { return neighbors_.end(); }

protected:
    std::set<std::shared_ptr<Node>> neighbors_;
    std::map<std::shared_ptr<Node>, uint32_t> edge_cost_;
};

// operators
bool operator==(const Node &node1, const Node &node2);
bool operator==(const std::shared_ptr<Node> &ptr, const Node &node);


class RoutingGraph {
public:
    RoutingGraph() : grid_() {}

    // used to construct the routing graph
    void add_edge(const Node &node1, const Node &node2);
    void add_edge(const Node &node1, const Node &node2, uint32_t cost);
    std::shared_ptr<Node> get_port_node(const uint32_t &x, const uint32_t &y,
                                        const std::string &name);

    const std::set<std::shared_ptr<Node>> get_nodes(const uint32_t &x,
                                                    const uint32_t &y);
    uint32_t overflow(const uint32_t &x, const uint32_t &y);

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>,
            std::set<std::shared_ptr<Node>>> grid_;
};


#endif //CYCLONE_GRAPH_H
