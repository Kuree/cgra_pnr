#ifndef CYCLONE_GRAPH_H
#define CYCLONE_GRAPH_H

#include <set>
#include <memory>
#include <map>
#include <vector>
#include <iostream>

enum NodeType {
    SwitchBox,
    Port,
    Register
};

class Node {
public:
    Node() = default;
    Node(const Node &node);

public:
    NodeType type = NodeType::Port;

    // can be either port name or
    std::string name;
    uint32_t width = 1;

    uint32_t x = 0;
    uint32_t y = 0;

    void add_edge(const std::shared_ptr<Node> &node, uint32_t cost);
    void add_edge(const std::shared_ptr<Node> &node) { add_edge(node, 1); }
    uint32_t get_cost(const std::shared_ptr<Node> &node);

    // helper function to allow iteration
    std::set<std::shared_ptr<Node>>::iterator begin()
    { return neighbors_.begin(); }
    std::set<std::shared_ptr<Node>>::iterator end() { return neighbors_.end(); }

protected:
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width);
    std::set<std::shared_ptr<Node>> neighbors_;
    std::map<std::shared_ptr<Node>, uint32_t> edge_cost_;
};

class PortNode : public Node {
public:
    PortNode(const std::string &name, uint32_t x, uint32_t y,
             uint32_t width) : Node(NodeType::Port, name, x, y, width) {}
    PortNode(const std::string &name, uint32_t x, uint32_t y)
        : Node(NodeType::Port, name, x, y) {}
};

class RegisterNode : public Node {
public:
    RegisterNode(const std::string &name, uint32_t x, uint32_t y,
                 uint32_t width)
        : Node(NodeType::Register, name, x, y, width) { }
    RegisterNode(const std::string &name, uint32_t x, uint32_t y)
        : Node(NodeType::Register, name, x, y) { }
};

class SwitchBoxNode : public Node {
private:
    const static int SIDES = 4;
    const static int IO = 2;
public:
    SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width);

    SwitchBoxNode(uint32_t x, uint32_t y)
                  : SwitchBoxNode(x, y, 1) { }
    SwitchBoxNode(const SwitchBoxNode &node);

    std::vector<std::set<std::shared_ptr<Node>>> channels[SIDES][IO];
};

// operators
bool operator==(const Node &node1, const Node &node2);
bool operator==(const std::shared_ptr<Node> &ptr, const Node &node);

struct Tile {
    // helper struct to holds the graph nodes
    uint32_t x = 0;
    uint32_t y = 0;
    uint32_t height = 0;

    // Note:
    // node name has to be unique within a tile otherwise it can't be located
    // through the tiles
    std::shared_ptr<SwitchBoxNode> sb;
    std::map<std::string, std::shared_ptr<PortNode>> ports;
    std::map<std::string, std::shared_ptr<RegisterNode>> registers;

    Tile() = default;
    Tile(uint32_t x, uint32_t y) : Tile(x, y, 1) { };
    Tile(uint32_t x, uint32_t y, uint32_t height);
};

std::ostream& operator<<(std::ostream &out, const Tile &tile);

class RoutingGraph {
public:
    RoutingGraph() : grid_() {}
    // helper class to create the grid efficiently
    RoutingGraph(uint32_t width, uint32_t height, const SwitchBoxNode &sb,
                 uint32_t num_register_tile);
    // manually add tiles
    void add_tile(const Tile &tile) { grid_.insert({{tile.x, tile.y}, tile}); }

    // used to construct the routing graph.
    // called after tiles have been constructed.
    void add_edge(const Node &node1, const Node &node2);
    void add_edge(const Node &node1, const Node &node2, uint32_t cost);

    std::shared_ptr<SwitchBoxNode> get_sb(const uint32_t &x, const uint32_t &y);
    std::shared_ptr<Node> get_port(const uint32_t &x,
                                   const uint32_t &y,
                                   const std::string &port);

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>, Tile> grid_;
};

#endif //CYCLONE_GRAPH_H
