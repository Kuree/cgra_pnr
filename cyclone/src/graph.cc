#include "graph.hh"
#include "net.hh"
#include "util.hh"
#include <cassert>
#include <sstream>
#include <string>
#include <unordered_set>
#include <queue>

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

bool operator<(const std::weak_ptr<Node> &a,
               const std::weak_ptr<Node> &b) {
    return a.lock() < b.lock();
};

bool operator==(std::weak_ptr<Node> &a, const std::weak_ptr<Node> &b) {
    return a.lock() == b.lock();
}

Node::Node(NodeType type, const std::string &name, uint32_t x, uint32_t y)
        : type(type), name(name), x(x), y(y) {}

Node::Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
           uint32_t width)
        : type(type), name(name), width(width), x(x), y(y) {}

Node::Node(NodeType type, const std::string &name, uint32_t x, uint32_t y,
           uint32_t width, uint32_t track)
        : type(type), name(name), width(width), track(track), x(x), y(y) {}

Node::Node(const Node &node) : enable_shared_from_this() {
    type = node.type;
    name = node.name;
    x = node.x;
    y = node.y;
    track = node.track;
}

void Node::add_edge(const std::shared_ptr<Node> &node, uint32_t wire_delay) {
    std::weak_ptr<Node> n = node;
    auto n_pos = std::find(neighbors_.begin(), neighbors_.end(), node);
    if (n_pos != neighbors_.end()) {
        throw std::runtime_error("Adding duplicated edge");
    }
    neighbors_.emplace_back(n);
    edge_cost_[n] = node->delay + wire_delay;
    node->conn_in_.emplace_back(weak_from_this());
}

bool Node::has_edge(const std::shared_ptr<Node> &node) {
    return std::any_of(neighbors_.begin(), neighbors_.end(), [node](const auto &n) {
        return n.lock() == node;
    });
}

uint32_t Node::get_edge_cost(const std::shared_ptr<Node> &node) {
    std::weak_ptr<Node> n = node;
    if (std::find(neighbors_.begin(), neighbors_.end(), n) != neighbors_.end())
        return 0xFFFFFF;
    else
        return edge_cost_[node];
}

void Node::remove_edge(const std::shared_ptr<Node> &node) {
    auto n_pos = std::find(neighbors_.begin(), neighbors_.end(), node);
    if (n_pos != neighbors_.end()) {
        neighbors_.erase(n_pos);
        edge_cost_.erase(node);
    } else {
        throw std::runtime_error("Removing non-existing edge");
    }
    auto c_pos = std::find(node->conn_in_.begin(), node->conn_in_.end(), weak_from_this());
    if (c_pos != node->conn_in_.end()) {
        // remove the incoming connection as well
        node->conn_in_.erase(c_pos);
    }
}

std::string Node::to_string() const {
    return "NODE " + name + " (" + ::to_string(track) + ", " +
           ::to_string(x) + ", " + ::to_string(y) + ", " +
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
               width, track), side(side), io(io) {}

SwitchBoxNode::SwitchBoxNode(const SwitchBoxNode &node) :
        SwitchBoxNode(node.x, node.y, node.width, node.track, node.side, node.io) {}

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
        auto[track_from, side_from, track_to, side_to] = iter;
        auto sb_from =
                sbs_[gsv(side_from)][giv(SwitchBoxIO::SB_IN)][track_from];
        auto sb_to =
                sbs_[gsv(side_to)][giv(SwitchBoxIO::SB_OUT)][track_to];
        sb_from->add_edge(sb_to, 0);
    }
}

const std::shared_ptr<SwitchBoxNode> &
Switch::operator[](const std::tuple<uint32_t,
        SwitchBoxSide,
        SwitchBoxIO> &track_side) const {
    auto const &[track, side, io] = track_side;
    return sbs_[gsv(side)][giv(io)][track];
}

const std::shared_ptr<SwitchBoxNode> &
Switch::operator[](const std::tuple<SwitchBoxSide,
        uint32_t,
        SwitchBoxIO> &side_track) const {
    auto const &[side, track, io] = side_track;
    return sbs_[gsv(side)][giv(io)][track];
}

const ::vector<::shared_ptr<SwitchBoxNode>>
Switch::get_sbs_by_side(const SwitchBoxSide &side) const {
    ::vector<::shared_ptr<SwitchBoxNode>> result;
    for (uint32_t io = 0; io < IOS; io++) {
        for (const auto &sb : sbs_[gsv(side)][io])
            result.emplace_back(sb);
    }
    return result;
}

void Switch::remove_sb_nodes(SwitchBoxSide side, SwitchBoxIO io) {
    // first remove the connections and nodes
    for (auto &sb : sbs_[gsv(side)][giv(io)]) {
        auto nodes_to_remove = ::set<std::weak_ptr<Node>>(sb->begin(),
                                                          sb->end());
        for (const auto &node : nodes_to_remove) {
            sb->remove_edge(node.lock());
        }
        auto conn_ins = sb->get_conn_in();
        for (const auto &node : conn_ins) {
            node.lock()->remove_edge(sb);
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
    return std::string(Tile::TOKEN) + " (" + ::to_string(x) + ", "
           + ::to_string(y) + ", " + ::to_string(height) + ", "
           + ::to_string(switchbox.id) + ")";
}

std::ostream &operator<<(std::ostream &out, const Tile &tile) {
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

RoutedGraph::RoutedGraph(const std::map<const Pin *, std::vector<std::shared_ptr<Node>>> &route) {
    std::set<std::pair<const Node *, const Node *>> visited;
    for (auto const &[pin, segment]: route) {
        for (uint64_t i = 1; i < segment.size(); i++) {
            auto const &pre_node_ = segment[i - 1];
            auto const &current_node_ = segment[i];
            auto pre_node = get_node(pre_node_);
            auto current_node = get_node(current_node_);

            // add edge
            auto connection = std::make_pair(pre_node.get(), current_node.get());
            if (visited.find(connection) == visited.end()) {
                visited.emplace(connection);
                pre_node->add_edge(current_node);
            }

        }
        pins_.emplace(pin, get_node(segment.back()));
    }
    // src node has to be the one that doesn't have src
    for (auto const &iter: internal_to_normal_) {
        auto const &n = iter.first;
        if (n->get_conn_in().empty()) {
            src_node_ = n;
            break;
        }
    }
}

std::shared_ptr<Node> RoutedGraph::get_node(const std::shared_ptr<Node> &node) {
    if (normal_to_internal_.find(node) == normal_to_internal_.end()) {
        auto n = node->clone();
        normal_to_internal_.emplace(node, n);
        internal_to_normal_.emplace(n, node);
    }
    return normal_to_internal_.at(node);
}

std::map<uint32_t, std::vector<std::shared_ptr<Node>>> RoutedGraph::get_route() const {
    std::map<uint32_t, std::vector<std::shared_ptr<Node>>> result;
    std::unordered_set<const Node *> visited;

    for (auto const &[pin, pin_node]: pins_) {
        std::vector<std::shared_ptr<Node>> segment;
        std::shared_ptr<Node> n = pin_node;

        while (n) {
            segment.emplace_back(internal_to_normal_.at(n));

            if (visited.find(n.get()) != visited.end()) {
                // fan-out net
                break;
            }
            visited.emplace(n.get());

            auto const &conn_to = n->get_conn_in();
            if (conn_to.size() == 1) {
                auto w_n = conn_to[0];
                n = w_n.lock();
            } else {
                if (conn_to.size() > 1)
                    throw std::runtime_error("ERROR");
                break;
            }
        }

        // need to reverse to follow the proper route
        std::reverse(segment.begin(), segment.end());
        result.emplace(pin->id, segment);
    }

    return result;
}

std::vector<uint32_t>
RoutedGraph::pin_order(const std::map<uint32_t, std::vector<std::shared_ptr<Node>>> &routes) const {
    std::unordered_set<uint32_t> finished;
    std::unordered_set<const Node *> visited;
    visited.emplace(internal_to_normal_.at(src_node_).get());
    std::vector<uint32_t> result;
    while (finished.size() != routes.size()) {
        for (auto const &[pin_id, segment]: routes) {
            if (finished.find(pin_id) != finished.end()) continue;
            if (visited.find(segment[0].get()) != visited.end()) {
                finished.emplace(pin_id);
                result.emplace_back(pin_id);
                for (auto const &n: segment) {
                    visited.emplace(n.get());
                }
            }
        }
    }

    return result;
}


std::set<const Pin *> RoutedGraph::insert_reg_output(std::shared_ptr<Node> src_node, bool reverse) {
    // we cannot insert pass a branch
    // mapped from normal to internal
    if (normal_to_internal_.find(src_node) != normal_to_internal_.end()) {
        src_node = normal_to_internal_.at(src_node);
    }
    while (true) {
        if (src_node->type == NodeType::SwitchBox) {
            auto sb = std::reinterpret_pointer_cast<SwitchBoxNode>(src_node);
            if (sb->io == SwitchBoxIO::SB_OUT) {
                // make sure we haven't pipelined this register
                auto next = sb->begin()->lock();
                if (next->type != NodeType::Register)
                    break;
            }
        }

        if (reverse) {
            if (src_node->get_conn_in().empty()) {
                throw std::runtime_error("Route completely full. Unable to insert pipeline registers");
            }
            src_node = src_node->get_conn_in().begin()->lock();
        } else {
            if (src_node->size() == 0) {
                throw std::runtime_error("Route completely full. Unable to insert pipeline registers");
            }
            src_node = src_node->begin()->lock();
        }

    }

    auto next = src_node->begin()->lock();
    std::shared_ptr<Node> reg;
    auto const &original_src_node = internal_to_normal_.at(src_node);
    for (auto const &n: *original_src_node) {
        auto node = n.lock();
        if (node->type == NodeType::Register) {
            reg = node;
            break;
        }
    }
    if (!reg) {
        throw std::runtime_error("Unable to find pipeline register");
    }

    src_node->remove_edge(next);
    auto reg_net = get_node(reg);
    src_node->add_edge(reg_net);
    reg_net->add_edge(next);

    // figure out the affected pins
    // assume no loop
    std::set<const Pin *> pins;
    std::queue<const Node *> nodes;
    nodes.emplace(next.get());
    std::unordered_set<const Node *> visited;
    while (!nodes.empty()) {
        auto const *n = nodes.front();
        nodes.pop();
        visited.emplace(n);
        if (n->type == NodeType::Port || n->type == NodeType::Register) {
            // need to figure out which pins gets affected
            for (auto const &[pin, pin_node]: pins_) {
                if (pin_node.get() == n) {
                    pins.emplace(pin);
                }
            }
        }
        for (auto const &nn: *n) {
            auto const &node_ptr = nn.lock();
            if (visited.find(node_ptr.get()) != visited.end()) {
                throw std::runtime_error("Loop detected. This is an error");
            }
            nodes.emplace(node_ptr.get());
        }
    }

    return pins;
}


std::set<const Pin *> RoutedGraph::insert_pipeline_reg(const Pin * pin) {
    if (pins_.find(pin) == pins_.end()) {
        throw std::runtime_error("Unable to find pin " + pin->name);
    }

    // itself must be affected
    std::set<const Pin *> pin_nodes = {pin};
    std::set<const Pin *> full_nodes;
    for (auto const &iter: pins_) full_nodes.emplace(iter.first);

    // figure out if we have any branch in the segments
    auto const &pin_node = pins_.at(pin);

    // need to see if we have a free RMUX node
    // couple sanity check
    if (pin_node->get_conn_in().size() != 1) {
        throw std::runtime_error("Unexpected pin connection");
    }

    // we insert it right after the source sink, if possible

    auto sb = pin_node->get_conn_in().front().lock();
    // if that switch box has two outputs already, we insert at the very beginning.
    if (sb->size() > 1) {
        auto pins = insert_reg_output(src_node_);
        if (pins.size() != full_nodes.size()) {
            throw std::runtime_error("Unable to insert registers to all pins from source");
        }
        return full_nodes;
    }
    // need to make sure the source is a rmux node
    std::shared_ptr<Node> rmux;
    if (sb->type == NodeType::Generic) {
        // this only happens when we are trying to insert pipeline registers before the IO ports
        rmux = sb;
    } else {
        // if it's not rmux, which is very likely the case
        rmux = sb->get_conn_in().front().lock();
    }

    if (!rmux || rmux->type != NodeType::Generic || internal_to_normal_.at(rmux)->get_conn_in().size() != 2) {
        throw std::runtime_error("Unable to find register mux");
    }

    auto pre_node = rmux->get_conn_in().front().lock();
    if (pre_node->type == NodeType::Register) {
        // we already register it. try one more step
        auto pins = insert_reg_output(pre_node, true);
        return pins;
    }

    auto pins = insert_reg_output(pre_node);
    if (pins.empty()) {
        throw std::runtime_error("Unable to insert a single register to the targeted pin");
    }

    return pin_nodes;
}


std::vector<std::shared_ptr<Node>> RoutedGraph::get_sink_to_src_route(const Pin *pin) const {
    std::vector<std::shared_ptr<Node>> result;
    auto node = pins_.at(pin);
    while (node) {
        result.emplace_back(internal_to_normal_.at(node));
        auto const &conn_in = node->get_conn_in();
        if (conn_in.empty()) {
            node = nullptr;
        } else {
            node = conn_in[0].lock();
        }
    }

    return result;
}

std::shared_ptr<Node> RoutedGraph::get_internal_node(const std::shared_ptr<Node> &normal) const {
    if (normal_to_internal_.find(normal) != normal_to_internal_.end()) {
        return normal_to_internal_.at(normal);
    } else {
        return nullptr;
    }
}

void RoutedGraph::connect(const std::shared_ptr<Node> &src, const std::shared_ptr<Node> &sink) {
    auto pre_node = get_node(src);
    auto current_node = get_node(sink);

    // add edge
    if (!pre_node->has_edge(current_node)) {
        pre_node->add_edge(current_node);
    }
}

void RoutedGraph::remove_connection(const std::shared_ptr<Node> &src, const std::shared_ptr<Node> &sink) {
    auto pre_node = get_node(src);
    auto current_node = get_node(sink);

    // add edge
    if (pre_node->has_edge(current_node)) {
        pre_node->remove_edge(current_node);
    }
}
