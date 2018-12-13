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

constexpr auto gsi = get_side_int;
constexpr auto gsv = get_side_value;

constexpr auto PORT_BEGIN = nullptr;
constexpr auto PORT_END = nullptr;


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

void Node::add_edge(const std::shared_ptr<Node> &from,
                    const std::shared_ptr<Node> &to, uint32_t wire_delay) {
    edges_[from].insert(to);

    edge_cost_.insert({{from, to}, wire_delay});
}

uint32_t Node::get_edge_cost(const std::shared_ptr<Node> &from,
                             const std::shared_ptr<Node> &to) {
    return edge_cost_.at({from, to});
}

const std::unordered_set<std::shared_ptr<Node>> Node::get_neighbor(
        std::shared_ptr<Node> pre_node) const {
    if (edges_.find(pre_node) == edges_.end())
        return {};
    else
        return edges_.at(pre_node);
}

std::string Node::to_string() const {
    return "NODE (" + std::to_string(track) + ", " +
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

std::string PortNode::to_string() const {
    return "PORT (" + std::to_string(track) + ", " +
           std::to_string(x) + ", " + std::to_string(y) + ")";
}


std::string RegisterNode::to_string() const {
    return "REG (" + std::to_string(track) + ", " +
           std::to_string(x) + ", " + std::to_string(y) + ")";
}

SwitchBoxNode::SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width,
                             uint32_t track, SwitchBoxSide side)
                             : Node(NodeType::SwitchBox, "", x, y,
                                    width, track), side(side) { }

SwitchBoxNode::SwitchBoxNode(const SwitchBoxNode &node) : Node(node),
                                                          side(node.side) {}

std::string SwitchBoxNode::to_string() const {
    return "REG (" + std::to_string(track) + ", " +
           std::to_string(x) + ", " + std::to_string(y) + " " +
           std::to_string(gsv(side)) + " )";
}

Switch::Switch(uint32_t x, uint32_t y, uint32_t num_track,
               uint32_t width, uint32_t switch_id,
               const std::set<std::tuple<uint32_t,
                              SwitchBoxSide, uint32_t,
                              SwitchBoxSide>> &internal_wires)
               : x(x), y(y), num_track(num_track), width(width), id(switch_id),
               internal_wires_(internal_wires) {
    for (uint32_t side = 0; side < SIDES; side++) {
        sbs_[side] = ::vector<shared_ptr<SwitchBoxNode>>(num_track);
        for (uint32_t i = 0; i < num_track; i++) {
            sbs_[side][i] = ::make_shared<SwitchBoxNode>(x, y, width, i,
                                                        gsi(side));
        }
    }
}

Switch::Switch(const Switch &switchbox) : Switch(switchbox.x, switchbox.y,
                                                 switchbox.num_track,
                                                 switchbox.width,
                                                 switchbox.id,
                                                 switchbox.internal_wires_)
{}

void Switch::add_edge(const std::shared_ptr<PortNode> &from,
                      const SwitchBoxNode &to,
                      uint32_t wire_delay) {
    // first locate the switch box specified by to
    auto side = to.side;
    auto track = to.track;
    auto sb = sbs_[gsv(side)][track];

    // based on the internal wiring, add all the edges
    // 1. found all sbs get's connected to
    auto const sides = get_from_sbs(side, track);
    // 2. add the edge link
    for (auto const &node : sides) {
        sb->add_edge(from, node);
    }

    // in port node nullptr is indicated as the from node
    from->add_edge(PORT_BEGIN, sb, wire_delay);
}

void Switch::add_edge(const SwitchBoxNode &from,
                      const std::shared_ptr<PortNode> &to,
                      uint32_t wire_delay) {
    // first locate the switch box specified by from
    auto side = from.side;
    auto track = from.track;
    auto sb = sbs_[gsv(side)][track];

    // based on the internal wiring, add all the edges
    // 1. found all sbs get's connected to
    auto const sides = get_to_sbs(side, track);
    // 2. add the edge link
    for (auto const &node : sides) {
        sb->add_edge(node, to, wire_delay);
    }
}

void Switch::add_edge(const SwitchBoxNode &from,
                      const std::shared_ptr<RegisterNode> &to,
                      uint32_t wire_delay) {
    // first locate the switch box specified by from
    auto side = from.side;
    auto track = from.track;
    auto sb = sbs_[gsv(side)][track];

    // if the register already has something connected to
    ::shared_ptr<Node> reg_to = nullptr;
    auto reg_connected_to = to->get_neighbor(PORT_END);
    if (!reg_connected_to.empty()) {
        if (reg_connected_to.size() != 1)
            throw ::runtime_error("reg should only have one output connected"
                                  " to");
        reg_to = *reg_connected_to.begin();
    }
    // add that info so that we can connect this reg to a switch box
    to->add_edge(sb, reg_to, wire_delay);

    // based on the internal wiring, add all the edges
    // 1. found all sbs get's connected to
    auto const sides = get_to_sbs(side, track);
    // 2. add the edge link
    for (auto const &node : sides) {
        sb->add_edge(node, to);
    }

}

void Switch::add_edge(const std::shared_ptr<RegisterNode> &from,
                      const SwitchBoxNode &to,
                      uint32_t wire_delay) {
    // first locate the switch box specified by to
    auto side = to.side;
    auto track = to.track;
    auto sb = sbs_[gsv(side)][track];

    // find out everything it's connected to
    ::shared_ptr<Node> reg_from = nullptr;
    for(const auto &iter: *from) {
        reg_from = iter.first;
    }
    from->add_edge(reg_from, sb, wire_delay);

    // based on the internal wiring, add all the edges
    // 1. found all sbs get's connected to
    auto const sides = get_from_sbs(side, track);
    // 2. add the edge link
    for (auto const &node : sides) {
        sb->add_edge(from, node);
    }
}

std::set<std::shared_ptr<SwitchBoxNode>>
Switch::get_from_sbs(SwitchBoxSide side, uint32_t track) {
    std::set<std::shared_ptr<SwitchBoxNode>> result;
    for (auto const &iter : internal_wires_) {
        auto [track_from, side_from, track_to, side_to] = iter;
        if (track_from == track && side_from == side) {
            result.insert(sbs_[gsv(side_to)][track_to]);
        }
    }

    return result;
}

std::set<std::shared_ptr<SwitchBoxNode>>
Switch::get_to_sbs(SwitchBoxSide side, uint32_t track) {
    std::set<std::shared_ptr<SwitchBoxNode>> result;
    for (auto const &iter : internal_wires_) {
        auto [track_from, side_from, track_to, side_to] = iter;
        if (track_to == track && side_to == side) {
            result.insert(sbs_[gsv(side_from)][track_from]);
        }
    }

    return result;
}


const std::shared_ptr<SwitchBoxNode>& Switch::operator[](
        const std::pair<uint32_t, SwitchBoxSide> &track_side) const {
    auto const &[track, side] = track_side;
    return sbs_[gsv(side)][track];
}

const std::shared_ptr<SwitchBoxNode>& Switch::operator[](
        const std::pair<SwitchBoxSide, uint32_t> &side_track) const {
    auto const &[side, track] = side_track;
    return sbs_[gsv(side)][track];
}

const std::vector<std::shared_ptr<SwitchBoxNode>>& Switch::operator[](
        const SwitchBoxSide &side) const {
    return sbs_[gsv(side)];
}

Tile::Tile(uint32_t x, uint32_t y, uint32_t height, const Switch &switchbox)
        : x(x), y(y), height(height), switchbox(switchbox) {

}

std::ostream& operator<<(std::ostream &out, const Tile &tile) {
    out << "tile (" << tile.x << ", " << tile.y << ")";
    return out;
}

RoutingGraph::RoutingGraph(uint32_t width, uint32_t height,
                           const Switch &switchbox) {
    // pre allocate tiles
    for (uint32_t x = 0; x < width; x++) {
        for (uint32_t y = 0; y < height; y++) {
            grid_.insert({{x, y}, Tile(x, y, Switch(switchbox))});
        }
    }
}

void RoutingGraph::add_edge(const Node &node1, const Node &node2,
                            uint32_t wire_delay) {
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

    // choose which function to call based on the node type
    if (n1->type == NodeType::Register && n2->type == NodeType::SwitchBox) {
        auto &switch_box = grid_.at({n2->x, n2->y}).switchbox;
        auto reg_node = std::reinterpret_pointer_cast<RegisterNode>(n1);
        auto const &sb = dynamic_cast<const SwitchBoxNode&>(node2);
        switch_box.add_edge(reg_node, sb, wire_delay);
    } else if (n1->type == NodeType::SwitchBox
               && n2->type == NodeType::Register) {
        auto &switch_box = grid_.at({n1->x, n1->y}).switchbox;
        auto reg_node = std::reinterpret_pointer_cast<RegisterNode>(n2);
        auto const &sb = dynamic_cast<const SwitchBoxNode&>(node1);
        switch_box.add_edge(sb, reg_node, wire_delay);
    } else if (n1->type == NodeType::Port && n2->type == NodeType::SwitchBox) {
        auto &switch_box = grid_.at({n2->x, n2->y}).switchbox;
        auto port_node = std::reinterpret_pointer_cast<PortNode>(n1);
        auto const &sb = dynamic_cast<const SwitchBoxNode&>(node2);
        switch_box.add_edge(port_node, sb, wire_delay);
    } else if (n1->type == NodeType::SwitchBox && n2->type == NodeType::Port) {
        auto &switch_box = grid_.at({n1->x, n1->y}).switchbox;
        auto port_node = std::reinterpret_pointer_cast<PortNode>(n2);
        auto const &sb = dynamic_cast<const SwitchBoxNode&>(node1);
        switch_box.add_edge(sb, port_node, wire_delay);
    } else if (n1->type == NodeType::SwitchBox
               && n2->type == NodeType::SwitchBox) {
        auto sb_from = std::reinterpret_pointer_cast<SwitchBoxNode>(n1);
        auto sb_to = std::reinterpret_pointer_cast<SwitchBoxNode>(n2);
        add_edge(sb_from, sb_to, wire_delay);
    } else {
        throw ::runtime_error("unable to connect nodes due to type conflicts");
    }
}

void RoutingGraph::add_edge(std::shared_ptr<SwitchBoxNode> &from,
                            std::shared_ptr<SwitchBoxNode> &to,
                            uint32_t wire_delay) {
    auto &switchbox_from = grid_.at({from->x, from->y}).switchbox;
    auto &switchbox_to = grid_.at({to->x, to->y}).switchbox;

    auto const &from_set = switchbox_from.get_from_sbs(from->side, from->track);
    auto const &to_set = switchbox_to.get_to_sbs(to->side, to->track);

    for (auto const &from_sb : from_set) {
        from->add_edge(from_sb, to, wire_delay);
    }

    for (auto const &to_sb : to_set) {
        to->add_edge(from, to_sb, wire_delay);
    }

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
        auto &tile = grid_.at({x, y});
        switch (node.type) {
            case NodeType::Register:
                if (tile.registers.find(node.name) == tile.registers.end())
                    tile.registers[node.name] =
                            ::make_shared<RegisterNode>(node.name,
                                                        node.x,
                                                        node.y,
                                                        node.width,
                                                        node.track);
                return tile.registers[node.name];
            case NodeType::Port:
                if (tile.ports.find(node.name) == tile.ports.end())
                    tile.ports[node.name] =
                            ::make_shared<PortNode>(node.name, node.x,
                                                    node.y, node.width);
                return tile.ports[node.name];
            case NodeType::SwitchBox:
                auto const &sb_node = dynamic_cast<const SwitchBoxNode&>(node);
                auto const &track = sb_node.track;
                auto const &side = sb_node.side;
                if (track > tile.switchbox.num_track)
                    throw ::runtime_error("node is on a track that doesn't "
                                          "exist in the switch box");

                return tile.switchbox[{track, side}];
                // default:
                //    throw ::runtime_error("unknown node type");
        }
    }
    return nullptr;
}

std::shared_ptr<Node> RoutingGraph::get_port(const uint32_t &x,
                                             const uint32_t &y,
                                             const std::string &port) {
    const Tile &t = grid_.at({x, y});
    if (t.ports.find(port) == t.ports.end())
        throw ::runtime_error("unable to find port " + port);
    return t.ports.at(port);
}

std::shared_ptr<SwitchBoxNode> RoutingGraph::get_sb(const uint32_t &x,
                                                    const uint32_t &y,
                                                    const uint32_t &track,
                                                    const SwitchBoxSide &side) {
    auto pos = make_pair(x, y);
    if (grid_.find(pos) == grid_.end()) {
        throw ::runtime_error("unable to find tile");
    } else {
        const auto &tile = grid_.at(pos);
        return tile.switchbox[{track, side}];
    }
}
