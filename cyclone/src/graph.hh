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
    // Note
    // copy constructor does not copy neighbors and edge_cost
    // due to the python interface
    Node(const Node &node);

    NodeType type = NodeType::Port;

    // can be either port name or
    std::string name;
    uint32_t width = 1;
    uint32_t track = 0;

    uint32_t x = 0;
    uint32_t y = 0;

    // used for delay calculation routing
    uint32_t delay = 1;

    virtual void add_edge(const std::shared_ptr<Node> &node);

    uint32_t get_edge_cost(const std::shared_ptr<Node> &node);

    // helper function to allow iteration
    std::set<std::shared_ptr<Node>>::iterator begin() const
    { return neighbors_.begin(); }
    std::set<std::shared_ptr<Node>>::iterator end() const
    { return neighbors_.end(); }
    std::set<std::shared_ptr<Node>>::iterator
    find(const std::shared_ptr<Node> &node) { return neighbors_.find(node); }

    virtual std::string to_string() const;
    friend std::ostream& operator<<(std::ostream &s, const Node &node) {
        return s << node.to_string();
    }

    const static int IO = 2;

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

// side illustration
//      3
//    -----
//  2 |   | 0
//    |   |
//    -----
//      1
class SwitchBoxNode : public Node {
public:
    SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width, uint32_t track);

    SwitchBoxNode(const SwitchBoxNode &node);

    const static int SIDES = 4;

    // Note:
    // because we need to indicate the side of switchbox,
    // we need to disable the parent method
    // throw an exception whenever they are called
    void add_edge(const std::shared_ptr<Node> &) override {
        static_assert("use add_edge with side instead");
    }

    void add_side_info(const std::shared_ptr<Node> &node, uint32_t side)
    { edge_to_side_.insert({node, side}); }

    // the actual one
    void add_edge(const std::shared_ptr<Node> &node, uint32_t side);

    uint32_t get_side(const std::shared_ptr<Node> &node) const;

private:
    std::map<std::shared_ptr<Node>, uint32_t> edge_to_side_;

};

// operators
bool operator==(const Node &node1, const Node &node2);
bool operator==(const std::shared_ptr<Node> &ptr, const Node &node);

struct Tile {
    // helper struct to holds the graph nodes
    uint32_t x = 0;
    uint32_t y = 0;
    uint32_t height = 1;

    // Note:
    // node name has to be unique within a tile otherwise it can't be located
    // through the tiles
    std::vector<std::shared_ptr<SwitchBoxNode>> sbs;
    std::map<std::string, std::shared_ptr<PortNode>> ports;
    std::map<std::string, std::shared_ptr<RegisterNode>> registers;

    uint32_t num_tracks() { return static_cast<uint32_t>(sbs.size()); }

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
    void remove_tile(const std::pair<uint32_t, uint32_t> &t) { grid_.erase(t); }

    // used to construct the routing graph.
    // called after tiles have been constructed.
    // concepts copied from networkx as it will create nodes along the way
    void add_edge(const Node &node1, const Node &node2);
    // side is relative to node1 if it is a switch box
    // otherwise it's relative to node2
    void add_edge(const Node &node1, const Node &node2, uint32_t side);

    // TODO
    // add remove edge functions

    std::shared_ptr<SwitchBoxNode> get_sb(const uint32_t &x, const uint32_t &y,
                                          const uint32_t &track);
    std::shared_ptr<Node> get_port(const uint32_t &x,
                                   const uint32_t &y,
                                   const std::string &port);

    // helper functions to iterate through the entire graph
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    begin() { return grid_.begin(); }
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    end() { return grid_.end(); }
    // and direct assess
    Tile &operator[](const std::pair<uint32_t, uint32_t> &tile)
    { return grid_.at(tile); };
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    find(const std::pair<uint32_t, uint32_t> &tile)
    { return grid_.find(tile); }

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>, Tile> grid_;

    std::shared_ptr<Node> search_create_node(const Node &node);
};

#endif //CYCLONE_GRAPH_H
