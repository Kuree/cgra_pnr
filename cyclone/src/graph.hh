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
    uint32_t track = 0;

    uint32_t x = 0;
    uint32_t y = 0;

    // used for delay calculation routing
    uint32_t delay = 1;

    void add_edge(const std::shared_ptr<Node> &node, uint32_t cost);
    void add_edge(const std::shared_ptr<Node> &node) { add_edge(node, 1); }
    uint32_t get_cost(const std::shared_ptr<Node> &node);

    // helper function to allow iteration
    std::set<std::shared_ptr<Node>>::iterator begin()
    { return neighbors_.begin(); }
    std::set<std::shared_ptr<Node>>::iterator end() { return neighbors_.end(); }
    std::set<std::shared_ptr<Node>>::iterator
    find(const std::shared_ptr<Node> &node) { return neighbors_.find(node); }

protected:
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width, uint32_t track);
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
                 uint32_t width, uint32_t track)
        : Node(NodeType::Register, name, x, y, width, track) { }
};

class SwitchBoxNode : public Node {
private:
    const static int SIDES = 4;
    const static int IO = 2;
public:
    SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width, uint32_t track);

    SwitchBoxNode(const SwitchBoxNode &node);

    std::set<std::shared_ptr<Node>> channels[SIDES][IO];

    bool overflow() const;
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
    std::vector<std::shared_ptr<SwitchBoxNode>> sbs;
    std::map<std::string, std::shared_ptr<PortNode>> ports;
    std::map<std::string, std::shared_ptr<RegisterNode>> registers;

    Tile() = default;
    Tile(uint32_t x, uint32_t y, uint32_t num_tracks)
        : Tile(x, y, 1, num_tracks) { };
    Tile(uint32_t x, uint32_t y, uint32_t height, uint32_t num_tracks);
};

std::ostream& operator<<(std::ostream &out, const Tile &tile);

class RoutingGraph {
public:
    RoutingGraph() : grid_() {}
    // helper class to create the grid efficiently
    RoutingGraph(uint32_t width, uint32_t height, uint32_t num_tracks,
                 const SwitchBoxNode &sb);
    // manually add tiles
    void add_tile(const Tile &tile) { grid_.insert({{tile.x, tile.y}, tile}); }

    // used to construct the routing graph.
    // called after tiles have been constructed.
    void add_edge(const Node &node1, const Node &node2);
    void add_edge(const Node &node1, const Node &node2, uint32_t cost);

    std::shared_ptr<SwitchBoxNode> get_sb(const uint32_t &x, const uint32_t &y,
                                          const uint32_t &track);
    std::shared_ptr<Node> get_port(const uint32_t &x,
                                   const uint32_t &y,
                                   const std::string &port);
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    begin() { return grid_.begin(); }
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    end() { return grid_.end(); }

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>, Tile> grid_;
};

#endif //CYCLONE_GRAPH_H
