#include "graph.hh"
#include <cassert>
#include <sstream>

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

Node::Node(const Node &node) {
    type = node.type;
    name = node.name;
    x = node.x;
    y = node.y;
    neighbors_ = node.neighbors_;
    edge_cost_ = node.edge_cost_;
}

void Node::add_edge(const std::shared_ptr<Node> &node, uint32_t cost) {
    neighbors_.insert(node);
    edge_cost_[node] = cost;
}

uint32_t Node::get_cost(const std::shared_ptr<Node> &node) {
    if (neighbors_.find(node) == neighbors_.end())
        return 0xFFFFFF;
    else
        return edge_cost_[node];
}

bool operator==(const Node &node1, const Node &node2) {
    return node1.x == node2.x && node1.y == node2.y &&
           node1.name == node2.name &&
           node1.type == node2.type;
}

bool operator==(const std::shared_ptr<Node> &ptr, const Node &node) {
    return (*ptr) == node;
}

SwitchBoxNode::SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width)
                             : Node(NodeType::SwitchBox, "", x, y) {
    // initialize the routing channels
    for (auto &channel : channels) {
        for (auto &route : channel) {
            route = ::vector<::set<shared_ptr<Node>>>(width);
        }
    }
}

SwitchBoxNode::SwitchBoxNode(const SwitchBoxNode &node) : Node(node) {
    // copy the channels over
    for (uint32_t i = 0; i < SIDES; i++) {
        for (uint32_t j = 0; j < IO; j++) {
            channels[i][j] = node.channels[i][j];
        }
    }
}

bool SwitchBoxNode::overflow() const {
    for (const auto &side : channels) {
        for (const auto &io : side) {
            for (auto const &chan : io) {
                if (chan.size() > 1)
                    return true;
            }
        }
    }
    return false;
}

Tile::Tile(uint32_t x, uint32_t y, uint32_t height)
        : x(x), y(y), height(height) {
}

std::ostream& operator<<(std::ostream &out, const Tile &tile) {
    out << "tile (" << tile.x << ", " << tile.y << ")";
    return out;
}

RoutingGraph::RoutingGraph(uint32_t width, uint32_t height,
                           const SwitchBoxNode &sb) {
    // pre allocate tiles
    for (uint32_t x = 0; x < width; x++) {
        for (uint32_t y = 0; y < height; y++) {
            grid_[{x, y}] = Tile(x, y);
            grid_[{x, y}].sb = ::make_shared<SwitchBoxNode>(sb);
        }
    }
}

void RoutingGraph::add_edge(const Node &node1, const Node &node2,
                            uint32_t cost) {
    // add node2 to
    // we don't use the nodes passed in, instead, we manage our own node
    // internally
    const Node node_list[2] = {node1, node2};
    ::shared_ptr<Node> ptr_list[2] = {nullptr, nullptr};
    for (int i = 0; i < 2; i++) {
        const auto node = node_list[i];
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
                                                            node.width);
                    ptr_list[i] = tile.ports[node.name];
                    break;
                case NodeType::Port:
                    if (tile.ports.find(node.name) == tile.ports.end())
                        tile.ports[node.name] =
                                ::make_shared<PortNode>(node.name, node.x,
                                                        node.y, node.width);
                    ptr_list[i] = tile.ports[node.name];
                    break;
                case NodeType::SwitchBox:
                    if (tile.sb == nullptr) {
                        tile.sb = ::make_shared<SwitchBoxNode>(node.x, node.y);
                    }
                    ptr_list[i] = tile.sb;
                    break;
                default:
                    throw ::runtime_error("unknown node type");
            }
        }
        if (ptr_list[i] == nullptr) {
            throw ::runtime_error("pointer list null");
        }
    }

    auto [n1, n2] = ptr_list;
    // notice that this is directional, that is, add n2 to n1's neighbor
    if (n1->width != n2->width)
        throw ::runtime_error("n2 width does not equal to n1");
    n1->add_edge(n2, cost);
}

void RoutingGraph::add_edge(const Node &node1, const Node &node2) {
    add_edge(node1, node2, 1);
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
                                                    const uint32_t &y) {
    auto pos = make_pair(x, y);
    if (grid_.find(pos) == grid_.end()) {
        throw ::runtime_error("unable to find tile");
    } else {
        const auto &tile = grid_[pos];
        if (tile.sb == nullptr) {
            ostringstream stream;
            stream << tile << " does not have a switchbox";
            throw ::runtime_error("tile ");
        }
    }
    return nullptr;
}