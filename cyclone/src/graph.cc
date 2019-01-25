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
using std::to_string;
using std::string;

constexpr auto gsi = get_side_int;
constexpr auto gsv = get_side_value;
constexpr auto gii = get_io_int;
constexpr auto giv = get_io_value;

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
    node->conn_in_.insert(this);
}

uint32_t Node::get_edge_cost(const std::shared_ptr<Node> &node) {
    if (neighbors_.find(node) == neighbors_.end())
        return 0xFFFFFF;
    else
        return edge_cost_[node];
}

void Node::remove_edge(const std::shared_ptr<Node> &node) {
    if (neighbors_.find(node) != neighbors_.end()) {
        neighbors_.erase(node);
        edge_cost_.erase(node);
    }
    if (node->conn_in_.find(this) != node->conn_in_.end()) {
        // remove the incoming connection as well
        node->conn_in_.erase(this);
    }
}

std::string Node::to_string() const {
    return "NODE " + name + " (" + ::to_string(track) + ", " +
           ::to_string(x) + ", " + ::to_string(y)  + ", " +
           ::to_string(width) + ")";
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
    return ::string(TOKEN) + " " + name + " (" + ::to_string(x) + ", "
           + ::to_string(y) + ", " + ::to_string(width) + ")";
}

std::string RegisterMuxNode::to_string() const {
    return ::string(TOKEN) + " " + name + " (" + ::to_string(x) + ", "
           + ::to_string(y) + ", " + ::to_string(width) + ")";
}

std::string RegisterNode::to_string() const {
    return ::string(TOKEN) + " " + name + " (" + ::to_string(track) + ", " +
           ::to_string(x) + ", " + ::to_string(y) + ", " +
           ::to_string(width) + ")";
}

SwitchBoxNode::SwitchBoxNode(uint32_t x, uint32_t y, uint32_t width,
                             uint32_t track, SwitchBoxSide side,
                             SwitchBoxIO io)
                             : Node(NodeType::SwitchBox, "", x, y,
                                    width, track), side(side), io(io) { }

std::string SwitchBoxNode::to_string() const {
    return ::string(TOKEN) + " (" + ::to_string(track) + ", " +
           ::to_string(x) + ", " + ::to_string(y) + ", " +
           ::to_string(gsv(side)) + ", " + ::to_string(giv(io)) + ", " +
           ::to_string(width) + ")";
}

Switch::Switch(uint32_t x, uint32_t y, uint32_t num_track,
               uint32_t width, uint32_t switch_id,
               const std::set<std::tuple<uint32_t,
                              SwitchBoxSide, uint32_t,
                              SwitchBoxSide>> &internal_wires)
               : x(x), y(y), num_track(num_track), width(width), id(switch_id),
               internal_wires_(internal_wires) {
    for (uint32_t side = 0; side < SIDES; side++) {
        for (uint32_t io = 0; io < IOS; io++) {
            sbs_[side][io] = ::vector<shared_ptr<SwitchBoxNode>>(num_track);
            for (uint32_t i = 0; i < num_track; i++) {
                sbs_[side][io][i] =
                        ::make_shared<SwitchBoxNode>(x, y, width, i,
                                                     gsi(side),
                                                     gii(io));
            }
        }
    }
    // assign internal wiring
    // the order is always in to out
    for (const auto &iter : internal_wires_) {
        auto [track_from, side_from, track_to, side_to] = iter;
        auto sb_from =
                sbs_[gsv(side_from)][giv(SwitchBoxIO::SB_IN)][track_from];
        auto sb_to =
                sbs_[gsv(side_to)][giv(SwitchBoxIO::SB_OUT)][track_to];
        sb_from->add_edge(sb_to, 0);
    }
}

const std::shared_ptr<SwitchBoxNode>&
Switch::operator[](const std::tuple<uint32_t,
                   SwitchBoxSide,
                   SwitchBoxIO> &track_side) const {
    auto const &[track, side, io] = track_side;
    return sbs_[gsv(side)][giv(io)][track];
}

const std::shared_ptr<SwitchBoxNode>&
Switch::operator[](const std::tuple<SwitchBoxSide,
                   uint32_t,
                   SwitchBoxIO > &side_track) const {
    auto const &[side, track, io] = side_track;
    return sbs_[gsv(side)][giv(io)][track];
}

const ::vector<::shared_ptr<SwitchBoxNode>>
Switch::get_sbs_by_side(const SwitchBoxSide &side) const {
    ::vector<::shared_ptr<SwitchBoxNode>> result;
    for (uint32_t io = 0; io< IOS; io++) {
        for (const auto &sb : sbs_[gsv(side)][io])
            result.emplace_back(sb);
    }
    return result;
}

void Switch::remove_sb_nodes(SwitchBoxSide side, SwitchBoxIO io) {
    // first remove the connections and nodes
    for (auto &sb : sbs_[gsv(side)][giv(io)]) {
        auto nodes_to_remove = ::set<::shared_ptr<Node>>(sb->begin(),
                                                         sb->end());
        for (const auto &node : nodes_to_remove) {
            sb->remove_edge(node);
        }
        auto conn_ins = sb->get_conn_in();
        for (const auto &node : conn_ins) {
            node->remove_edge(sb);
        }
    }
    sbs_[gsv(side)][giv(io)].clear();
    // then we clean up the internal wires that has reference to the side
    // and io. this is very useful to create a tall tiles that uses multiple
    // switches
    ::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
    wires_to_remove;
    for (auto const &conn : internal_wires_) {
        SwitchBoxSide side_from, side_to;
        std::tie(std::ignore, side_from, std::ignore, side_to) = conn;
        if (io == SwitchBoxIO::SB_IN && side_from == side)
            wires_to_remove.insert(conn);
        else if (io == SwitchBoxIO::SB_OUT && side_to == side)
            wires_to_remove.insert(conn);
    }
    // remove them
    for (auto const &conn : wires_to_remove)
        internal_wires_.erase(conn);
}

Tile::Tile(uint32_t x, uint32_t y, uint32_t height, const Switch &switchbox)
        : x(x), y(y), height(height), switchbox(x,
                                                y,
                                                switchbox.num_track,
                                                switchbox.width,
                                                switchbox.id,
                                                switchbox.internal_wires()) {

}

std::string Tile::to_string() const {
    return std::string(Tile::TOKEN) + " (" +  ::to_string(x) + ", "
           + ::to_string(y) + ", " + ::to_string(height) + ", "
           + ::to_string(switchbox.id) + ")";
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
            grid_.insert({{x, y},
                          Tile(x, y, Switch(x,
                                            y,
                                            switchbox.num_track,
                                            switchbox.width,
                                            switchbox.id,
                                            switchbox.internal_wires()))});
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
        throw ::runtime_error("node2 width does not equal to node1 "
                              "node1: " + ::to_string(n1->width) + " "
                              "node2: " + ::to_string(n2->width));
    n1->add_edge(n2, wire_delay);
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
                return tile.registers.at(node.name);
            case NodeType::Port:
                if (tile.ports.find(node.name) == tile.ports.end())
                    tile.ports[node.name] =
                            ::make_shared<PortNode>(node.name, node.x,
                                                    node.y, node.width);
                return tile.ports.at(node.name);
            case NodeType::SwitchBox: {
                auto const &sb_node = dynamic_cast<const SwitchBoxNode &>(node);
                auto const &track = sb_node.track;
                auto const &side = sb_node.side;
                auto const &io = sb_node.io;
                if (track > tile.switchbox.num_track)
                    throw ::runtime_error("node is on a track that doesn't "
                                          "exist in the switch box");

                return tile.switchbox[{track, side, io}];
            }
            case NodeType::Generic:
                // genetic node
                if (tile.rmux_nodes.find(node.name)
                    == tile.rmux_nodes.end())
                    tile.rmux_nodes[node.name] =
                            ::make_shared<RegisterMuxNode>(node.name,
                                                       node.x,
                                                       node.y,
                                                       node.width,
                                                       node.track);
                return tile.rmux_nodes.at(node.name);
        }
    }
    return nullptr;
}

std::shared_ptr<Node> RoutingGraph::get_port(const uint32_t &x,
                                             const uint32_t &y,
                                             const std::string &port) {
    if (grid_.find({x, y}) == grid_.end()) {
        std::stringstream ss;
        ss << "unable to find grid tile " << x << " " << y;
        throw ::runtime_error(ss.str());
    }
    const Tile &t = grid_.at({x, y});
    if (t.ports.find(port) == t.ports.end())
        throw ::runtime_error("unable to find port " + port);
    return t.ports.at(port);
}

std::shared_ptr<SwitchBoxNode>
RoutingGraph::get_sb(const uint32_t &x, const uint32_t &y,
                     const SwitchBoxSide &side,
                     const uint32_t &track, const SwitchBoxIO &io) {
    auto pos = make_pair(x, y);
    if (grid_.find(pos) == grid_.end()) {
        throw ::runtime_error("unable to find tile");
    } else {
        const auto &tile = grid_.at(pos);
        return tile.switchbox[{track, side, io}];
    }
}
