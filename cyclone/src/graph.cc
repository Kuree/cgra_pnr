#include "graph.hh"
#include "util.hh"
#include <cassert>
#include <sstream>
#include <string>

using std::make_pair;
using std::make_shared;
using std::shared_ptr;
using std::vector;
using std::runtime_error;
using std::set;
using std::ostringstream;


Node::Node(NodeType type, const std::string &name, uint32_t x, uint32_t y)
    : type(type), name(name), x(x), y(y) { }

Node::Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
           uint32_t width)
        : type(type), name(name), width(width), x(x), y(y) { }

Node::Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
           uint32_t width, uint32_t track)
        : type(type), name(name), width(width), track(track), x(x), y(y) { }

Node::Node(const Node &node) {
    type = node.type;
    name = node.name;
    x = node.x;
    y = node.y;
    track = node.track;
}

void Node::add_edge(const std::shared_ptr<Node> &node, uint32_t wire_delay) {
    neighbors_.insert(node);
    edge_cost_[node] = node->delay + wire_delay;
}

uint32_t Node::get_edge_cost(const std::shared_ptr<Node> &node) {
    if (neighbors_.find(node) == neighbors_.end())
        return 0xFFFFFF;
    else
        return edge_cost_[node];
}

std::string Node::to_string() const {
    std::string node_type;
    switch (type) {
        case NodeType::SwitchBox:
            node_type = "SB";
            break;
        case NodeType::Register:
            node_type = "Reg";
            break;
        case NodeType::Port:
            node_type = "Port-" + name;
            break;
    }
    return node_type + " (" + std::to_string(track) + ", " +
           std::to_string(x) + ", " + std::to_string(y) + ")";
}

bool operator==(const Node &node1, const Node &node2) {
    return node1.x == node2.x && node1.y == node2.y &&
           node1.name == node2.name &&
           node1.type == node2.type;
}

bool operator==(const std::shared_ptr<Node> &ptr, const Node &node) {
    return (*ptr) == node;
}

SwitchBoxNode::SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width,
                             uint32_t track)
                             : Node(NodeType::SwitchBox, "", x, y,
                                    width, track) { }

SwitchBoxNode::SwitchBoxNode(const SwitchBoxNode &node) : Node(node) {}

void SwitchBoxNode::add_edge(const std::shared_ptr<Node> &node,
                             SwitchBoxSide side) {
    Node::add_edge(node);
    // add to side index table
    edge_to_side_.insert({node, side});
}

void SwitchBoxNode::add_edge(const std::shared_ptr<Node> &node,
                             SwitchBoxSide side, uint32_t wire_delay) {
    Node::add_edge(node, wire_delay);
    // add to side index table
    edge_to_side_.insert({node, side});
}

SwitchBoxSide SwitchBoxNode::get_side(const ::shared_ptr<Node> &node) const {
    if (edge_to_side_.find(node) == edge_to_side_.end())
        throw ::runtime_error("unable to find node when assigning"
                              "connections");
    return edge_to_side_.at(node);
}

Tile::Tile(uint32_t x, uint32_t y, uint32_t height, uint32_t num_tracks)
        : x(x), y(y), height(height), sbs(num_tracks) {

}

std::ostream& operator<<(std::ostream &out, const Tile &tile) {
    out << "tile (" << tile.x << ", " << tile.y << ")";
    return out;
}

RoutingGraph::RoutingGraph(uint32_t width, uint32_t height,
                           uint32_t num_tracks, const SwitchBoxNode &sb) {
    // pre allocate tiles
    for (uint32_t x = 0; x < width; x++) {
        for (uint32_t y = 0; y < height; y++) {
            grid_[{x, y}] = Tile(x, y, num_tracks);
            for (uint32_t i = 0; i < num_tracks; i++) {
                auto const & sb_instance = ::make_shared<SwitchBoxNode>(sb);
                sb_instance->track = i;
                sb_instance->x = x;
                sb_instance->y = y;
                grid_[{x, y}].sbs[i] = sb_instance;
            }
        }
    }
}

void RoutingGraph::add_edge(const Node &node1, const Node &node2) {
    if (node1.type == NodeType::SwitchBox || node2.type == NodeType::SwitchBox)
        throw ::runtime_error("switch box uses add_edge(node, node, side)");
    // we don't use the nodes passed in, instead, we manage our own node
    // internally
    auto n1 = search_create_node(node1);
    auto n2 = search_create_node(node2);
    if (n1 == nullptr)
        throw ::runtime_error("cannot find node1");
    if (n2 == nullptr)
        throw ::runtime_error("cannot find node2");

    // notice that this is directional, that is, add n2 to n1's neighbor
    if (n1->width != n2->width)
        throw ::runtime_error("node2 width does not equal to node1");
    n1->add_edge(n2);
}

void RoutingGraph::add_edge(const Node &node1, const Node &node2,
                            SwitchBoxSide side) {
    if (node1.type != NodeType::SwitchBox && node2.type != NodeType::SwitchBox)
        throw ::runtime_error("only switch box uses "
                              "add_edge(node, node, side)");
    auto n1 = search_create_node(node1);
    auto n2 = search_create_node(node2);
    if (n1 == nullptr)
        throw ::runtime_error("cannot find node1");
    if (n2 == nullptr)
        throw ::runtime_error("cannot find node2");

    if (node1.type == NodeType::SwitchBox) {
        auto sb1 = std::reinterpret_pointer_cast<SwitchBoxNode>(n1);
        sb1->add_edge(n2, side);
        if (node2.type == NodeType::SwitchBox) {
            auto sb2 = std::reinterpret_pointer_cast<SwitchBoxNode>(n2);
            auto new_side = get_opposite_side(side);
            sb2->add_side_info(n1, new_side);
        }
    } else {
        auto sb2 = std::reinterpret_pointer_cast<SwitchBoxNode>(n2);
        sb2->add_side_info(n1, side);
        n1->add_edge(sb2);
    }
}

void RoutingGraph::add_edge(const SwitchBoxNode &node1,
                            const SwitchBoxNode &node2,
                            SwitchBoxSide side1,
                            SwitchBoxSide side2) {
    auto n1 = search_create_node(node1);
    auto n2 = search_create_node(node2);
    if (n1->type != NodeType::Register || n2->type != NodeType::Register)
        throw ::runtime_error("it has to be switch box");
    auto sb1 = std::reinterpret_pointer_cast<SwitchBoxNode>(n1);
    auto sb2 = std::reinterpret_pointer_cast<SwitchBoxNode>(n2);
    sb1->add_edge(n2, side1);
    sb2->add_edge(n1, side2);
}

std::shared_ptr<Node> RoutingGraph::search_create_node(const Node &node) {
    uint32_t x = node.x;
    uint32_t y = node.y;

    if (grid_.find({x, y}) == grid_.end()) {
        // a new tile. creating on the fly not supported any more
        ostringstream stream;
        stream << "unable to find tile at (" << x << ", " << y << ")";
        throw ::runtime_error(stream.str());
    } else {
        // depends on which type the nodes is. we need to
        // treat differently
        auto &tile = grid_[{x, y}];
        switch (node.type) {
            case NodeType::Register:
                if (tile.registers.find(node.name) == tile.registers.end())
                    tile.registers[node.name] =
                            ::make_shared<RegisterNode>(node.name,
                                                        node.x,
                                                        node.y,
                                                        node.width,
                                                        node.track);
                return tile.ports[node.name];
            case NodeType::Port:
                if (tile.ports.find(node.name) == tile.ports.end())
                    tile.ports[node.name] =
                            ::make_shared<PortNode>(node.name, node.x,
                                                    node.y, node.width);
                return tile.ports[node.name];
            case NodeType::SwitchBox:
                auto const &track = node.track;
                if (tile.sbs[track] == nullptr) {
                    tile.sbs[track] =
                            ::make_shared<SwitchBoxNode>(node.x, node.y,
                                                         node.width,
                                                         node.track);
                }
                return tile.sbs[track];
                // default:
                //    throw ::runtime_error("unknown node type");
        }
    }
    return nullptr;
}

std::shared_ptr<Node> RoutingGraph::get_port(const uint32_t &x,
                                             const uint32_t &y,
                                             const std::string &port) {
    const Tile &t = grid_[{x, y}];
    if (t.ports.find(port) == t.ports.end())
        throw ::runtime_error("unable to find port " + port);
    return t.ports.at(port);
}

std::shared_ptr<SwitchBoxNode> RoutingGraph::get_sb(const uint32_t &x,
                                                    const uint32_t &y,
                                                    const uint32_t &track) {
    auto pos = make_pair(x, y);
    if (grid_.find(pos) == grid_.end()) {
        throw ::runtime_error("unable to find tile");
    } else {
        const auto &tile = grid_[pos];
        if (tile.sbs[track] == nullptr) {
            ostringstream stream;
            stream << tile << " does not have a switchbox";
            throw ::runtime_error("tile ");
        }
        return tile.sbs[track];
    }
}