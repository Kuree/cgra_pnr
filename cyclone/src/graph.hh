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
    std::set<std::shared_ptr<Node>>::iterator begin()
    { return neighbors_.begin(); }
    std::set<std::shared_ptr<Node>>::iterator end() { return neighbors_.end(); }
    std::set<std::shared_ptr<Node>>::iterator
    find(const std::shared_ptr<Node> &node) { return neighbors_.find(node); }

    /* ---- functions related to routing algorithm ---- */
    virtual void assign_connection(const std::shared_ptr<Node> &, uint32_t) = 0;
    // how many times it's been used that way
    virtual uint32_t get_history_cost(const std::shared_ptr<Node> &) = 0;
    virtual void clear() = 0;
    virtual uint32_t get_presence_cost(const std::shared_ptr<Node> &,
                                       uint32_t) = 0;

protected:
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width, uint32_t track);
    std::set<std::shared_ptr<Node>> neighbors_;
    std::map<std::shared_ptr<Node>, uint32_t> edge_cost_;

    const static int IO = 2;
};

class PortNode : public Node {
public:
    PortNode(const std::string &name, uint32_t x, uint32_t y,
             uint32_t width) : Node(NodeType::Port, name, x, y, width) {}
    PortNode(const std::string &name, uint32_t x, uint32_t y)
        : Node(NodeType::Port, name, x, y) {}

    /* ---- functions related to routing algorithm ---- */
    std::set<std::shared_ptr<Node>> connections[IO];

    void clear() override;
    void assign_connection(const std::shared_ptr<Node> & node,
                           uint32_t io) override;
    uint32_t get_history_cost(const std::shared_ptr<Node> & node) override;
    uint32_t
    get_presence_cost(const std::shared_ptr<Node> &node, uint32_t io) override;

private:
    uint32_t history_count_ = 0;
};

class RegisterNode : public Node {
public:
    RegisterNode(const std::string &name, uint32_t x, uint32_t y,
                 uint32_t width, uint32_t track)
        : Node(NodeType::Register, name, x, y, width, track) { }

    /* ---- functions related to routing algorithm ---- */
    std::set<std::shared_ptr<Node>> connections[IO];

    void clear() override;
    void assign_connection(const std::shared_ptr<Node> & node,
                           uint32_t io) override;
    uint32_t get_history_cost(const std::shared_ptr<Node> &node) override;
    uint32_t
    get_presence_cost(const std::shared_ptr<Node> & node, uint32_t io) override;

private:
    uint32_t history_count_ = 0;
};

// side illustration
//      3
//    -----
//  2 |   | 0
//    |   |
//    -----
//      1
class SwitchBoxNode : public Node {
private:
    const static int SIDES = 4;
    std::map<std::shared_ptr<Node>, uint32_t> edge_to_side_;
    uint32_t side_history_count_[SIDES][IO] = {};

    uint32_t get_side(const std::shared_ptr<Node> &node);

public:
    SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width, uint32_t track);

    SwitchBoxNode(const SwitchBoxNode &node);

    std::set<std::shared_ptr<Node>> channels[SIDES][IO];

    bool overflow() const;
    void clear() override;

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
    void assign_connection(const std::shared_ptr<Node> & node,
                           uint32_t io) override;
    uint32_t get_history_cost(const std::shared_ptr<Node> &node) override;
    uint32_t
    get_presence_cost(const std::shared_ptr<Node> & node, uint32_t io) override;
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

    void clear_connections();

    // helper functions to iterate through the entire graph
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    begin() { return grid_.begin(); }
    std::map<std::pair<uint32_t, uint32_t>, Tile>::iterator
    end() { return grid_.end(); }

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>, Tile> grid_;

    std::shared_ptr<Node> search_create_node(const Node &node);
};

#endif //CYCLONE_GRAPH_H
