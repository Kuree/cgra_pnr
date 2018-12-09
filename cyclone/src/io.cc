#include "io.hh"
#include "util.hh"
#include <iostream>
#include <fstream>
#include <algorithm>
#include <functional>
#include <sstream>

using std::ifstream;
using std::map;
using std::pair;
using std::string;
using std::vector;
using std::runtime_error;
using std::make_pair;
using std::endl;

constexpr auto gsv = get_side_value;
constexpr auto gsi = get_side_int;

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
    oss << pad << node->to_string() << " " << node->width;
    return oss.str();
}

void print_conn(std::ofstream &out, const std::string &pad,
                const std::shared_ptr<Node> &node) {
    for (auto const &n : *node) {
        out << pad << pad << node_to_string(pad, n) << endl;
    }
}

void dump_routing_graph(RoutingGraph &graph,
                        const std::string &filename) {
    std::ofstream out;
    out.open(filename);
    static const ::string PAD = "  ";
    for (const auto &iter : graph) {
        auto tile = iter.second;
        out << "TILE (" << tile.x << ", " << tile.y << ", "
            << tile.height << ", " << tile.num_tracks() << ")" << endl;
        for (uint32_t i = 0; i < tile.sbs.size(); i++) {
            auto const sb = tile.sbs[i];
            out << PAD << "SB " << i << " " << sb->width << endl;
            out << PAD << "SB BEGIN" << endl;
            auto const &sides = sb->get_sides_info();
            for (const auto &iter_side : sides) {
                if (sb->find(iter_side.first) != sb->end()) {
                    // Note
                    // We can further reduce the graph size by only listing
                    // edges out, since the in-coming edges will be constructed
                    // when another switch box connected to it.
                    out << PAD << node_to_string(PAD, iter_side.first) << " "
                        << gsv(iter_side.second) << endl;
                }
            }
            out << PAD << "SB END" << endl;
        }
        for (auto const &port_iter : tile.ports) {
            // Note
            // This is to compress the output graph since it will be referenced
            // by other tile that's connected to
            if (port_iter.second->size() == 0)
                continue;
            out << PAD << port_iter.second->to_string() << endl;
            out << PAD << "CONN BEGIN" << endl;
            print_conn(out, PAD, port_iter.second);
            out << PAD << "CONN END" << endl;
        }

        for (auto const &reg_tier : tile.registers) {
            out << PAD << reg_tier.second->to_string() << endl;
            out << PAD << "CONN BEGIN" << endl;
            print_conn(out, PAD, reg_tier.second);
            out << PAD << "CONN END" << endl;
        }
    }
}

inline uint32_t stou(const std::string &str) {
    return static_cast<uint32_t>(std::stoi(str));
}

::pair<Node, uint32_t>
create_node_from_tokens_sb(const ::vector<::string> &tokens) {
    if (tokens.size() < 6)
        throw ::runtime_error("expect at least 6 entries");
    const auto &type_token = tokens[0];
    if (type_token == "SB") {
        ::vector<uint32_t> values(5);
        for (uint32_t i = 0; i < 5; i++)
            values[i] = stou(tokens[i + 1]);
        // track, x, y, width, side
        SwitchBoxNode node(values[1], values[2], values[3], values[0]);
        uint32_t side = values[4];
        return {node, side};
    } else if (type_token == "PORT") {
        if (tokens.size() < 7)
            throw ::runtime_error("expect at least 7 entries for port");
        ::vector<uint32_t> values(5);
        for (uint32_t i = 0; i < 5; i++)
            values[i] = stou(tokens[i + 2]);
        PortNode node(tokens[1], values[1], values[2], values[3]);
        uint32_t side = values[4];
        return {node, side};
    } else if (type_token == "REG") {
        if (tokens.size() < 7)
            throw ::runtime_error("expect at least 7 entries for port");
        ::vector<uint32_t> values(5);
        for (uint32_t i = 0; i < 5; i++)
            values[i] = stou(tokens[i + 2]);
        RegisterNode node(tokens[1], values[1], values[2], values[3],
                          values[0]);
        uint32_t side = values[4];
        return {node, side};
    } else {
        throw ::runtime_error("unknown type " + type_token);
    }
}

RoutingGraph load_routing_graph(const std::string &filename) {
    std::ifstream in;
    in.open(filename);

    RoutingGraph g;
    ::string line;
    // reading per tile
    while(std::getline(in, line)) {
        trim(line);
        if (line.empty())
            continue;
        auto line_tokens = get_tokens(line);
        if (line_tokens[0] == "TILE") {
            if (line_tokens.size() != 5)
                throw ::runtime_error("unable to process line " + line);
            uint32_t x = stou(line_tokens[1]);
            uint32_t y = stou(line_tokens[2]);
            uint32_t height = stou(line_tokens[3]);
            uint32_t num_track = stou(line_tokens[4]);
            Tile tile(x, y, height, num_track);
            g.add_tile(tile);
        }
    }
    // we have to create all tiles first
    // so we rewind and start to process the graph nodes
    in.seekg(0);
    while(std::getline(in, line)) {
        trim(line);
        if (line.empty())
            continue;
        auto line_tokens = get_tokens(line);
        if (line_tokens[0] == "TILE") {
            if (line_tokens.size() != 5)
                throw ::runtime_error("unable to process line " + line);
            uint32_t x = stou(line_tokens[1]);
            uint32_t y = stou(line_tokens[2]);

            // parse SBs
            while(std::getline(in, line)) {
                trim(line);
                line_tokens = get_tokens(line);
                if (line_tokens[0] != "SB") {
                    throw ::runtime_error("expect token SB, got " + line);
                }
                uint32_t track = stou(line_tokens[1]);
                uint32_t width = stou(line_tokens[2]);
                SwitchBoxNode sb(x, y, width, track);
                // the next line has to be SB
                std::getline(in, line);
                trim(line);
                line_tokens = get_tokens(line);
                if (line_tokens[0] != "SB" && line_tokens[1] != "BEGIN")
                    throw ::runtime_error("expect SB BEGIN, got " + line);
                while(std::getline(in, line)) {
                    trim(line);
                    line_tokens = get_tokens(line);
                    if (line_tokens[0] == "SB" && line_tokens[1] == "END")
                        break;
                    auto [node, side] = create_node_from_tokens_sb(line_tokens);
                    g.add_edge(sb, node, gsi(side));
                }
            }
        }
    }
    return g;
}