#include "graph.hh"
#include <cassert>

using std::make_pair;
using std::make_shared;
using std::shared_ptr;
using std::vector;
using std::runtime_error;


Node::Node(NodeType type, uint32_t track, uint32_t x, uint32_t y)
           : type(type), nets(), name(), track(track), x(x), y(y),
             neighbors_() { }

Node::Node(NodeType type, uint32_t x, uint32_t y) : Node(type, 0, x, y) { }

Node::Node(const std::string &name, uint32_t x, uint32_t y)
           : Node(NodeType::Port, x, y) {
    this->name = name;
}

Node::Node(const Node &node) {
    type = node.type;
    nets = node.nets;
    name = node.name;
    track = node.track;
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
           node1.track == node2.track && node1.name == node2.name &&
           node1.type == node2.type;
}

bool operator==(const std::shared_ptr<Node> &ptr, const Node &node) {
    return (*ptr) == node;
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

        auto point = ::make_pair(x, y);
        if (grid_.find(point) == grid_.end()) {
            ptr_list[i] = ::make_shared<Node>(Node(node));
            grid_[{x, y}] = {};
            grid_[{x, y}].insert(ptr_list[i]);
        } else {
            // we have this location, but may not be the exact same node;
            auto &nodes = grid_[{x, y}];
            bool found = false;
            for (const auto &n : nodes) {
                if (n == node) {
                    ptr_list[i] = n;
                    found = true;
                    break;
                }
            }
            if (!found) {
                // we need to create a new one
                ptr_list[i] = ::make_shared<Node>(Node(node));
                nodes.insert(ptr_list[i]);
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

std::shared_ptr<Node> RoutingGraph::get_port_node(const uint32_t &x,
                                                  const uint32_t &y,
                                                  const std::string &name) {
    auto pos = make_pair(x, y);
    if (grid_.find(pos) == grid_.end())
        return nullptr;
    const auto &nodes = grid_[pos];
    for (const auto &node : nodes) {
        if (node->name == name)
            return node;
    }
    return nullptr;
}

const std::set<std::shared_ptr<Node>>
RoutingGraph::get_nodes(const uint32_t &x, const uint32_t &y) {
    auto pos = make_pair(x, y);
    if (grid_.find(pos) == grid_.end())
        return {};
    else
        return grid_[pos];
}

uint32_t RoutingGraph::overflow(const uint32_t &x, const uint32_t &y) {
    uint32_t count = 0;
    auto nodes = get_nodes(x, y);
    for (const auto &node : nodes) {
        if (node->type == NodeType::SwitchBox) {
            if (node->overflow())
                count++;
        }
    }
    return count;
}