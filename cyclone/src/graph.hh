#ifndef CYCLONE_GRAPH_H
#define CYCLONE_GRAPH_H

#include <set>
#include <memory>
#include <map>
#include <vector>
#include <iostream>
#include <unordered_map>

class Node;

enum NodeType {
    SwitchBox,
    Port,
    Register,
    Generic
};

enum class SwitchBoxSide {
    Right = 0,
    Bottom = 1,
    Left = 2,
    Top = 3
};

enum class SwitchBoxIO {
    SB_IN = 0,
    SB_OUT = 1
};

bool operator< (const std::weak_ptr<Node> &a,
                const std::weak_ptr<Node> &b);


class Node: public std::enable_shared_from_this<Node> {
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

    virtual void add_edge(const std::shared_ptr<Node> &node)
    { add_edge(node, DEFAULT_WIRE_DELAY); }
    virtual void add_edge(const std::shared_ptr<Node> &node,
                          uint32_t wire_delay);
    virtual void remove_edge(const std::shared_ptr<Node> &node);
    bool has_edge(const std::shared_ptr<Node> &node);

    uint32_t get_edge_cost(const std::shared_ptr<Node> &node);

    // helper function to allow iteration
    auto begin() const { return neighbors_.begin(); }
    auto end() const { return neighbors_.end(); }
    uint64_t size() { return neighbors_.size(); }

    // used in creating mux in hardware
    const std::vector<std::weak_ptr<Node>> &get_conn_in() const { return conn_in_; }

    virtual std::string to_string() const;
    friend std::ostream& operator<<(std::ostream &s, const Node &node) {
        return s << node.to_string();
    }

    virtual std::shared_ptr<Node> clone() const { return std::make_shared<Node>(*this); }

    const static int IO = 2;
    const static uint32_t DEFAULT_WIRE_DELAY = 0;

    virtual ~Node() = default;

protected:
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width);
    Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
         uint32_t width, uint32_t track);

    // TODO: change this to std::weak_ptr to avoid memory leak due to circular
    // TODO: reference.
    std::vector<std::weak_ptr<Node>> neighbors_;
    std::map<std::weak_ptr<Node>, uint32_t,
             std::owner_less<std::weak_ptr<Node>>> edge_cost_;

private:
    std::vector<std::weak_ptr<Node>>conn_in_;
};

class RegisterMuxNode : public Node {
public:
    RegisterMuxNode(const std::string &name, uint32_t x, uint32_t y,
             uint32_t width, uint32_t track) :
             Node(NodeType::Generic, name, x, y, width, track) {}
    RegisterMuxNode(const std::string &name, uint32_t x, uint32_t y)
            : Node(NodeType::Generic, name, x, y) {}
    std::string to_string() const override;

    static constexpr char TOKEN[] = "RMUX";
};

class PortNode : public Node {
public:
    PortNode(const std::string &name, uint32_t x, uint32_t y,
             uint32_t width) : Node(NodeType::Port, name, x, y, width) {}
    PortNode(const std::string &name, uint32_t x, uint32_t y)
        : Node(NodeType::Port, name, x, y) {}
    std::string to_string() const override;

    static constexpr char TOKEN[] = "PORT";
};

class RegisterNode : public Node {
public:
    RegisterNode(const std::string &name, uint32_t x, uint32_t y,
                 uint32_t width, uint32_t track)
        : Node(NodeType::Register, name, x, y, width, track) { }

    std::string to_string() const override;

    static constexpr char TOKEN[] = "REG";
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
    SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width, uint32_t track,
                  SwitchBoxSide side, SwitchBoxIO io);

    SwitchBoxNode(const SwitchBoxNode &node);

    std::string to_string() const override;

    SwitchBoxSide side;
    SwitchBoxIO io;

    std::shared_ptr<Node> clone() const override { return std::make_shared<SwitchBoxNode>(*this); }

    static constexpr char TOKEN[] = "SB";
};

// operators
bool operator==(const Node &node1, const Node &node2);
bool operator==(const std::shared_ptr<Node> &ptr, const Node &node);


class Switch {

public:
    Switch(uint32_t x, uint32_t y, uint32_t num_track,
           uint32_t width, uint32_t switch_id,
           const std::set<std::tuple<uint32_t,
                          SwitchBoxSide, uint32_t,
                          SwitchBoxSide>> &internal_wires);

    uint32_t x;
    uint32_t y;
    uint32_t num_track;
    uint32_t width;

    // it's the programmer's responsibility to ensure that each switch type
    // has unique ID
    uint32_t id;

    const static int SIDES = 4;
    const static int IOS = 2;

    const std::shared_ptr<SwitchBoxNode> &
    operator[](const std::tuple<uint32_t,
                                SwitchBoxSide,
                                SwitchBoxIO> &track_side) const;
    const std::shared_ptr<SwitchBoxNode> &
    operator[](const std::tuple<SwitchBoxSide,
                               uint32_t,
                               SwitchBoxIO> &track_side) const;

    const std::vector<std::shared_ptr<SwitchBoxNode>>
    get_sbs_by_side(const SwitchBoxSide &side) const;

    const std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
    internal_wires() const { return internal_wires_; }

    void remove_sb_nodes(SwitchBoxSide side, SwitchBoxIO io);

    static constexpr char TOKEN[] = "SWITCH";

private:
    // this is used to construct internal connection of switch boxes
    std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
    internal_wires_;

    std::vector<std::shared_ptr<SwitchBoxNode>> sbs_[SIDES][IOS];

};

struct Tile {
    // helper struct to holds the graph nodes
    uint32_t x = 0;
    uint32_t y = 0;
    uint32_t height = 1;

    Switch switchbox;
    // Note:
    // node name has to be unique within a tile otherwise it can't be located
    // through the tiles
    std::map<std::string, std::shared_ptr<PortNode>> ports;
    std::map<std::string, std::shared_ptr<RegisterNode>> registers;
    std::map<std::string, std::shared_ptr<RegisterMuxNode>> rmux_nodes;

    uint32_t num_tracks() { return static_cast<uint32_t>(switchbox.num_track); }

    Tile(uint32_t x, uint32_t y, const Switch &switchbox)
        : Tile(x, y, 1, switchbox) { };
    Tile(uint32_t x, uint32_t y, uint32_t height, const Switch &switchbox);

    static constexpr char TOKEN[] = "TILE";
    std::string to_string() const;
};

std::ostream& operator<<(std::ostream &out, const Tile &tile);



class RoutingGraph {
public:
    RoutingGraph() : grid_() {}
    // helper constructors to create the grid efficiently
    RoutingGraph(uint32_t width, uint32_t height,
                 const Switch &switchbox);

    // manually add tiles
    void add_tile(const Tile &tile) { grid_.insert({{tile.x, tile.y}, tile}); }
    void remove_tile(const std::pair<uint32_t, uint32_t> &t) { grid_.erase(t); }

    // used to construct the routing graph.
    // called after tiles have been constructed.
    // concepts copied from networkx as it will create nodes along the way
    void add_edge(const Node &node1, const Node &node2)
    { add_edge(node1, node2, Node::DEFAULT_WIRE_DELAY); }
    void add_edge(const Node &node1, const Node &node2, uint32_t wire_delay);

    // TODO
    // add remove edge functions

    std::shared_ptr<SwitchBoxNode>
    get_sb(const uint32_t &x, const uint32_t &y,
           const SwitchBoxSide &side,
           const uint32_t &track,
           const SwitchBoxIO &io);
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

    bool has_tile(const std::pair<uint32_t, uint32_t> &coord)
    { return grid_.find(coord) != grid_.end(); }
    bool has_tile(uint32_t x, uint32_t y) { return has_tile({x, y}); };

private:
    // grid is for fast locating the nodes. no longer used for routing
    std::map<std::pair<uint32_t, uint32_t>, Tile> grid_;

    std::shared_ptr<Node> search_create_node(const Node &node);
};

// hold information for routed graph
// all nodes are cloned from the original routing graph
struct Pin;
class RoutedGraph {
public:
    explicit RoutedGraph(const std::map<const Pin*,
                         std::vector<std::shared_ptr<Node>>>& route);

    std::map<uint32_t, std::vector<std::shared_ptr<Node>>> get_route() const;

    std::vector<uint32_t> pin_order(const std::map<uint32_t, std::vector<std::shared_ptr<Node>>> &routes) const;

    [[nodiscard]] std::set<const Pin *> insert_pipeline_reg(const Pin * pin);

    [[nodiscard]] std::set<const Pin *> insert_reg_output(std::shared_ptr<Node> src_node, bool reverse = false);

    [[nodiscard]] std::vector<std::shared_ptr<Node>> get_sink_to_src_route(const Pin *pin) const;

    [[nodiscard]] std::shared_ptr<Node> get_internal_node(const std::shared_ptr<Node> &normal) const;

    void connect(const std::shared_ptr<Node> &src, const std::shared_ptr<Node> &sink);
    void remove_connection(const std::shared_ptr<Node> &src, const std::shared_ptr<Node> &sink);

private:
    // our node to the actual routing graph node
    std::unordered_map<std::shared_ptr<Node>, std::shared_ptr<Node>> normal_to_internal_;
    std::unordered_map<std::shared_ptr<Node>, std::shared_ptr<Node>> internal_to_normal_;
    std::map<const Pin *, std::shared_ptr<Node>> pins_;
    std::shared_ptr<Node> src_node_;

    std::shared_ptr<Node> get_node(const std::shared_ptr<Node> &node);
};

#endif //CYCLONE_GRAPH_H
