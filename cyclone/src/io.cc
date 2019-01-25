#include "io.hh"
#include "util.hh"
#include <iostream>
#include <fstream>
#include <algorithm>
#include <functional>
#include <sstream>
#include <unordered_set>
#include <experimental/filesystem>

using std::ifstream;
using std::map;
using std::pair;
using std::string;
using std::vector;
using std::runtime_error;
using std::make_pair;
using std::endl;
using std::to_string;
using std::experimental::filesystem::exists;

//constexpr auto gsv = get_side_value;
constexpr auto gsi = get_side_int;
constexpr auto gsv = get_side_value;
constexpr auto gii = get_io_int;

constexpr char BEGIN[] = "BEGIN";
constexpr char END[] = "END";

#define DELIMITER ": \t,()"

// trim function copied from https://stackoverflow.com/a/217605
// trim from start (in place)
static inline void ltrim(std::string &s) {
    s.erase(s.begin(),
            std::find_if(s.begin(), s.end(),
                         std::not1(std::ptr_fun<int, int>(std::isspace))));
}

// trim from end (in place)
static inline void rtrim(std::string &s) {
    s.erase(std::find_if(s.rbegin(), s.rend(),
                         std::not1(std::ptr_fun<int,
                                                int>(std::isspace))).base(),
                                   s.end());
}

// trim from both ends (in place)
static inline void trim(std::string &s) {
    ltrim(s);
    rtrim(s);
}

::vector<::string> get_tokens(const ::string &line) {
    ::vector<::string> tokens;
    size_t prev = 0, pos = 0;
    ::string token;
    // copied from https://stackoverflow.com/a/7621814
    while ((pos = line.find_first_of(DELIMITER, prev))
           != ::string::npos) {
        if (pos > prev) {
            tokens.emplace_back(line.substr(prev, pos - prev));
        }
        prev = pos + 1;
    }
    if (prev < line.length())
        tokens.emplace_back(line.substr(prev, std::string::npos));
    return tokens;
}

::pair<::map<::string, ::vector<::pair<::string, ::string>>>,
       ::map<::string, uint32_t>>
load_netlist(const std::string &filename) {
    if (!::exists(filename))
        throw ::runtime_error(filename + " does not exist");
    ::ifstream in;
    in.open(filename);

    ::string line;
    bool in_netlist = false;
    bool in_bus = false;

    ::map<::string, ::vector<::pair<::string, ::string>>> netlist;
    ::map<::string, uint32_t> track_mode;

    while(std::getline(in, line)) {
        // we are only interested in the packed netlist section
        trim(line);
        if (line[0] == '#')
            continue;
        if (in_netlist) {
            if (line.empty()) {
                in_netlist = false;
                continue;
            }
            const ::vector<::string> tokens = get_tokens(line);

            if (tokens.size() % 2 != 1)
                throw ::runtime_error("unable to process line " + line);
            const ::string &net_id = tokens[0];
            ::vector<::pair<::string, ::string>> net;
            for (uint32_t i = 1; i < tokens.size(); i+= 2) {
                ::string const &blk_id = tokens[i];
                ::string const &port = tokens[i + 1];
                net.emplace_back(make_pair(blk_id, port));
            }
            netlist.insert({net_id, net});
            // skip the rest of logic
            continue;
        }

        if (in_bus) {
            if (line.empty()) {
                in_bus = false;
                continue;
            }
            const ::vector<::string> tokens = get_tokens(line);
            if (tokens.size() != 2)
                throw ::runtime_error("unable to process line " + line);
            const ::string net_id = tokens[0];
            const ::string track_str = tokens[1];

            auto width = static_cast<uint32_t>(std::stoi(track_str));
            track_mode.insert({net_id, width});

            // skip the rest of logic
            continue;
        }

        // state control
        if (line == "Netlists:") {
            in_netlist = true;
            continue;
        } else if (line == "Netlist Bus:") {
            in_bus = true;
        } else {
            in_netlist = false;
            in_bus = false;
        }
    }

    if (netlist.size() != track_mode.size()) {
        throw ::runtime_error("netlist size doesn't match with netlist bus");
    }
    return {netlist, track_mode};
}


std::map<std::string, std::pair<uint32_t, uint32_t>>
load_placement(const std::string &filename) {
    if (!::exists(filename))
        throw ::runtime_error(filename + " does not exist");
    ::ifstream in;
    in.open(filename);

    ::string line;
    uint32_t line_num = 0;
    std::map<std::string, std::pair<uint32_t, uint32_t>> placement;

    while(std::getline(in, line)) {
        if (line_num < 2) {
            line_num++;
            continue;
        }
        trim(line);

        auto tokens = get_tokens(line);
        if (tokens.size() != 4)
            throw ::runtime_error("unable to process line " + line);
        auto x = static_cast<uint32_t>(std::stoi(tokens[1]));
        auto y = static_cast<uint32_t>(std::stoi(tokens[2]));
        auto blk_id = tokens[3].substr(1, ::string::npos);

        placement.insert({blk_id, {x, y}});
        line_num++;
    }

    return placement;
}

// used to print identifiers for edges
::string node_to_string(const ::string &pad,
                        const std::shared_ptr<Node> &node) {
    std::ostringstream oss;
    oss << pad << node->to_string();
    return oss.str();
}

void print_conn(std::ofstream &out, const std::string &pad,
                const std::shared_ptr<Node> &node) {
    // need to sort them to make the dump process deterministic
    ::vector<std::shared_ptr<Node>> nodes;
    for (const auto &n : *node)
        nodes.emplace_back(n);

    // ordering for sides and ios
    std::stable_sort(nodes.begin(), nodes.end(),
                     [](const std::shared_ptr<Node> &n1,
                        const std::shared_ptr<Node> &n2) {
                         if (n1->type == NodeType::SwitchBox &&
                             n2->type == NodeType::SwitchBox) {
                             auto sb1 =
                                     std::reinterpret_pointer_cast
                                             <SwitchBoxNode>(n1);
                             auto sb2 =
                                     std::reinterpret_pointer_cast
                                             <SwitchBoxNode>(n2);
                             return sb1->side > sb2->side;
                         } else {
                             return n1->name > n2->name;
                         }
                     });
    std::stable_sort(nodes.begin(), nodes.end(),
                     [](const std::shared_ptr<Node> &n1,
                        const std::shared_ptr<Node> &n2) {
                         if (n1->type == NodeType::SwitchBox &&
                             n2->type == NodeType::SwitchBox) {
                             auto sb1 =
                                     std::reinterpret_pointer_cast
                                             <SwitchBoxNode>(n1);
                             auto sb2 =
                                     std::reinterpret_pointer_cast
                                             <SwitchBoxNode>(n2);
                             return sb1->io > sb2->io;
                         } else {
                             return n1->name > n2->name;
                         }
                     });
    std::stable_sort(nodes.begin(), nodes.end(),
                     [](const std::shared_ptr<Node> &n1,
                        const std::shared_ptr<Node> &n2) {
                         return n1->track > n2->track;
                     });
    std::stable_sort(nodes.begin(), nodes.end(),
                     [](const std::shared_ptr<Node> &n1,
                        const std::shared_ptr<Node> &n2) {
                         return n1->x > n2->x;
                     });
    std::stable_sort(nodes.begin(), nodes.end(),
                     [](const std::shared_ptr<Node> &n1,
                        const std::shared_ptr<Node> &n2) {
                         return n1->y > n2->y;
                     });

    for (auto const &n : nodes) {
        out << pad << pad << node_to_string(pad, n) << endl;
    }
}

void print_sb(std::ofstream &out, const std::string &pad, const Switch &sb) {
    out << Switch::TOKEN << " " << sb.width << " " << sb.id << " "
        << sb.num_track << endl;
    out << BEGIN << endl;
    const auto wires = sb.internal_wires();
    for (auto const iter : wires) {
        auto [track_from, side_from, track_to, side_to] = iter;
        out << pad << track_from << " " << gsv(side_from) << " "
            << track_to << " " << gsv(side_to) << endl;
    }
    out << END << endl;
}

void dump_routing_graph(RoutingGraph &graph,
                        const std::string &filename) {
    // TODO:
    // add delay info into the graph
    std::ofstream out;
    out.open(filename);
    static const ::string PAD = "  ";
    // first, prints out the switch box
    ::map<uint32_t, Switch> switch_boxes;
    for (const auto &iter : graph) {
        auto const &switch_box = iter.second.switchbox;
        if (switch_boxes.find(switch_box.id) == switch_boxes.end())
            switch_boxes.insert({switch_box.id, switch_box});
    }

    for (const auto &iter : switch_boxes) {
        print_sb(out, PAD, iter.second);
    }

    for (const auto &iter : graph) {
        auto tile = iter.second;
        out << tile.to_string() << endl;
        for (uint32_t side = 0; side < Switch::SIDES; side++) {
            for (auto const &sb : tile.switchbox.get_sbs_by_side(gsi(side))) {
                // skip in since it's connected internationally
                if (sb->io != SwitchBoxIO::SB_OUT || sb->size() == 0)
                    continue;
                out << PAD << sb->to_string() << endl;
                out << PAD << BEGIN << endl;
                print_conn(out, PAD, sb);
                out << PAD << END << endl;
            }
        }
        for (auto const &port_iter : tile.ports) {
            // Note
            // This is to compress the output graph since it will be referenced
            // by other tile that's connected to
            if (port_iter.second->size() == 0)
                continue;
            out << PAD << port_iter.second->to_string() << endl;
            out << PAD << BEGIN << endl;
            print_conn(out, PAD, port_iter.second);
            out << PAD << END << endl;
        }

        for (auto const &reg_tier : tile.registers) {
            out << PAD << reg_tier.second->to_string() << endl;
            out << PAD << BEGIN << endl;
            print_conn(out, PAD, reg_tier.second);
            out << PAD << END << endl;
        }

        for (auto const &generic_tier : tile.rmux_nodes) {
            out << PAD << generic_tier.second->to_string() << endl;
            out << PAD << BEGIN << endl;
            print_conn(out, PAD, generic_tier.second);
            out << PAD << END << endl;
        }
    }
}

inline uint32_t stou(const std::string &str) {
    return static_cast<uint32_t>(std::stoi(str));
}

PortNode create_port_from_tokens(const ::vector<::string> &tokens) {
    if (tokens[0] != PortNode::TOKEN)
        throw ::runtime_error("expect PORT, got " + tokens[0]);
    if (tokens.size() < 4)
        throw ::runtime_error("expect at least 6 entries for port");
    ::vector<uint32_t> values(3);
    // x, y, width
    for (uint32_t i = 0; i < 3; i++)
        values[i] = stou(tokens[i + 2]);
    return PortNode(tokens[1], values[0], values[1], values[2]);
}

RegisterNode create_reg_from_tokens(const ::vector<::string> &tokens) {
    if (tokens[0] != RegisterNode::TOKEN)
        throw ::runtime_error("expect REG, got " + tokens[0]);
    if (tokens.size() < 6)
        throw ::runtime_error("expect at least 6 entries for reg");
    ::vector<uint32_t> values(4);
    // track, x, y, width
    for (uint32_t i = 0; i < 4; i++)
        values[i] = stou(tokens[i + 2]);
    return RegisterNode(tokens[1], values[1], values[2], values[3], values[0]);
}

RegisterMuxNode create_generic_from_tokens(const ::vector<::string> &tokens) {
    if (tokens[0] != RegisterMuxNode::TOKEN)
        throw ::runtime_error("export GENERIC, got " + tokens[0]);
    if (tokens.size() < 6)
        throw ::runtime_error("expect at least 6 entries for reg");
    ::vector<uint32_t> values(4);
    // track, x, y, width
    for (uint32_t i = 0; i < 4; i++)
        values[i] = stou(tokens[i + 2]);
    return RegisterMuxNode(tokens[1], values[1], values[2], values[3], values[0]);
}

SwitchBoxNode create_sb_from_tokens(const ::vector<::string> &tokens) {
    if (tokens[0] != SwitchBoxNode::TOKEN)
        throw ::runtime_error("expect SB, got " + tokens[0]);
    if (tokens.size() < 6)
        throw ::runtime_error("expect at least 6 entries for sb");
    ::vector<uint32_t> values(6);
    // track, x, y, side, io, width
    for (uint32_t i = 0; i < 6; i++)
        values[i] = stou(tokens[i + 1]);
    return SwitchBoxNode(values[1], values[2], values[5], values[0],
                         gsi(values[3]), gii(values[4]));
}

void get_line_tokens(vector<string> &line_tokens, ifstream &in, string &line) {
    while (getline(in, line)) {
        trim(line);
        if (!line.empty() && line[0] != '#')
            break;
    }
    line_tokens = get_tokens(line);
}

void connect_nodes(Node &from, std::ifstream &in, RoutingGraph &g) {
    // the next line has to be SB
    ::vector<::string> line_tokens;
    ::string line;
    get_line_tokens(line_tokens, in, line);
    if (line_tokens.empty() || line_tokens[0] != BEGIN)
        throw ::runtime_error("expect " + ::string(BEGIN) +  ", got " + line);
    while (std::getline(in, line)) {
        trim(line);
        line_tokens = get_tokens(line);
        if (line_tokens[0] == END)
            break;
        if (line_tokens[0] == SwitchBoxNode::TOKEN) {
            auto sb = create_sb_from_tokens(line_tokens);
            g.add_edge(from, sb);
        } else if (line_tokens[0] == RegisterNode::TOKEN) {
            auto reg = create_reg_from_tokens(line_tokens);
            g.add_edge(from, reg);
        } else if (line_tokens[0] == PortNode::TOKEN) {
            auto port = create_port_from_tokens(line_tokens);
            g.add_edge(from, port);
        } else if (line_tokens[0] == RegisterMuxNode::TOKEN) {
            auto node = create_generic_from_tokens(line_tokens);
            g.add_edge(from, node);
        } else {
            throw ::runtime_error("unknown node type " + line_tokens[0]);
        }
    }
}

RoutingGraph load_routing_graph(const std::string &filename) {
    if (!::exists(filename))
        throw ::runtime_error(filename + " does not exist");

    std::ifstream in;
    in.open(filename);

    RoutingGraph g;
    ::string line;
    ::map<int, Switch> switch_map;

    // reading per tile
    while(std::getline(in, line)) {
        trim(line);
        if (line.empty())
            continue;
        auto line_tokens = get_tokens(line);
        if (line_tokens[0] == Switch::TOKEN) {
            // create a switch based on its index
            if (line_tokens.size() != 4)
                throw ::runtime_error("unable to process line " + line);
            uint32_t width = stou(line_tokens[1]);
            uint32_t id = stou(line_tokens[2]);
            uint32_t num_track = stou(line_tokens[3]);
            // loop through the lines until we hit end
            // this will be the internal wiring
            std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t,
                                SwitchBoxSide>> wires;
            std::getline(in, line);
            trim(line);
            if (line != BEGIN)
                throw ::runtime_error("unable to process line " + line);
            while (std::getline(in, line)) {
                trim(line);
                if (line == END)
                    break;
                line_tokens = get_tokens(line);
                if (line_tokens.size() != 4)
                    throw ::runtime_error("unable to process line" + line);
                uint32_t track_from = stou(line_tokens[0]);
                SwitchBoxSide side_from = gsi(stou(line_tokens[1]));
                uint32_t track_to = stou(line_tokens[2]);
                SwitchBoxSide side_to = gsi(stou(line_tokens[3]));
                wires.insert({track_from, side_from, track_to, side_to});
            }
            Switch switchbox(0, 0, num_track, width, id, wires);
            switch_map.insert({id, switchbox});
        }
        else if (line_tokens[0] == Tile::TOKEN) {
            if (line_tokens.size() != 5)
                throw ::runtime_error("unable to process line " + line);
            uint32_t x = stou(line_tokens[1]);
            uint32_t y = stou(line_tokens[2]);
            uint32_t height = stou(line_tokens[3]);
            uint32_t switch_id = stou(line_tokens[4]);

            auto switchbox = switch_map.at(switch_id);
            Tile tile(x, y, height, switchbox);
            g.add_tile(tile);
        }
    }
    // we have to create all tiles first
    // so we rewind and start to process the graph nodes
    in.clear();
    in.seekg(0, std::ios::beg);
    while(std::getline(in, line)) {
        trim(line);
        if (line.empty() || line[0] == '#')
            continue;

        auto line_tokens = get_tokens(line);
        if (line_tokens[0] == SwitchBoxNode::TOKEN) {
            auto sb = create_sb_from_tokens(line_tokens);
            connect_nodes(sb, in, g);
        } else if (line_tokens[0] == PortNode::TOKEN) {
            auto port = create_port_from_tokens(line_tokens);
            connect_nodes(port, in, g);
        } else if (line_tokens[0] == RegisterNode::TOKEN) {
            auto reg = create_reg_from_tokens(line_tokens);
            connect_nodes(reg, in, g);
        } else if (line_tokens[0] == RegisterMuxNode::TOKEN) {
            auto generic = create_generic_from_tokens(line_tokens);
            connect_nodes(generic, in, g);
        }
    }
    in.close();
    return g;
}

void dump_routing_result(const Router &r, const std::string &filename) {
    std::ofstream out;
    out.open(filename, std::ofstream::out | std::ofstream::app);

    auto routes = r.realize();
    const auto &netlist = r.get_netlist();
    for (const auto &net : netlist) {
        const auto &net_id = net.name;
        auto const segments = routes.at(net.name);
        out << "Net ID: " << net_id << " Segment Size: "
            << segments.size() << endl;
        std::unordered_set<std::shared_ptr<Node>> visited;
        auto const &src = net[0].node;
        bool has_src = false;
        for (uint32_t seg_index = 0; seg_index < segments.size(); seg_index++) {
            auto const segment = segments[seg_index];
            out << "Segment: " << seg_index << " Size: " << segment.size()
                << endl;
            for (uint32_t node_index = 0; node_index < segment.size();
                 node_index++) {
                auto const &node = segment[node_index];
                if (node_index == 0 && node == src) {
                    has_src = true;
                }
                // just output plain sequence
                out << node->to_string() << endl;
            }
        }
        if (!has_src) {
            // it has to be the src
            throw ::runtime_error("unexpected state: src has to be"
                                  "the beginning of the net "
                                  "segments");
        }
        out << endl;
    }

    out.close();
}

void setup_router_input(Router &r, const std::string &packed_filename,
                        const std::string &placement_filename,
                        uint32_t width) {
    auto [netlist, track_mode] = load_netlist(packed_filename);
    printf("netlist: %ld\n", netlist.size());
    auto placement = load_placement(placement_filename);
    for (auto const &it : placement) {
        auto [x, y] = it.second;
        r.add_placement(x, y, it.first);
    }

    for (const auto &iter: netlist) {
        // Note
        // we only route 1bit at this time
        if (track_mode.at(iter.first) == width)
            r.add_net(iter.first, iter.second);
    }
}
