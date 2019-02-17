#include "io.hh"
#include "layout.hh"
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


#define DELIMITER ": \t,()"


const ::string BEGIN = "BEGIN";
const ::string END = "END";

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

inline uint32_t stou(const std::string &str) {
    return static_cast<uint32_t>(std::stoi(str));
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


void parse_layout(::ifstream &in, Layout &layout,
                  std::vector<::string> &tokens) {
    ::string line;
    char blk_type;
    uint32_t major;
    uint32_t minor;
    if (tokens.size() == 3) {
        blk_type = ' ';
        major = stou(tokens[1]);
        minor = stou(tokens[2]);
    } else if (tokens.size() == 4) {
        if (tokens[1].size() != 1)
            throw ::runtime_error("expect single char. got " + tokens[1]);
        blk_type = tokens[1][0];

        major = stou(tokens[2]);
        minor = stou(tokens[3]);
    } else {
        throw ::runtime_error("expect layer header. got " + line);
    }

    ::vector<::vector<bool>> layer;
    // we expect BEGIN token
    std::getline(in, line);
    trim(line);
    if (line != BEGIN) {
        std::stringstream msg;
        msg << "expect " << BEGIN << " got " << line;
        throw ::runtime_error(msg.str());
    }
    while(std::getline(in, line)) {
        trim(line);
        if (line == END)
            break;
        ::vector<bool> row;
        for (const auto c : line) {
            if (c == '1')
                row.emplace_back(true);
            else if (c == '0')
                row.emplace_back(false);
            else
                throw ::runtime_error("expect either 1 or 0, got " +
                                      ::string(1, c));
        }
        if (!layer.empty()) {
            if (layer[0].size() != row.size()) {
                throw ::runtime_error("not a rectangular layout");
            }
        }
        layer.emplace_back(row);
    }
    auto height = static_cast<uint32_t>(layer.size());
    auto width = static_cast<uint32_t>(layer[0].size());
    auto l = Layer(blk_type, width, height);
    for (uint32_t y = 0; y < layer.size(); y++) {
        auto const &row = layer[y];
        for (uint32_t x = 0; x < row.size(); x++) {
            if (layer[y][x])
                l.mark_available(x, y);
        }
    }
    layout.add_layer(l, major, minor);
}

void parse_mask(::ifstream &in, Layout &layout,
                std::vector<::string> &tokens) {
    ::string line;
    // read the masks
    if (tokens.size() != 3) {
        throw std::runtime_error("expect format MASK %c %c.");
    }
    char blk_type = tokens[1][0];
    char mask_blk_type = tokens[2][0];

    std::getline(in, line);
    trim(line);
    if (line != BEGIN) {
        std::stringstream msg;
        msg << "expect " << BEGIN << " got " << line;
        throw ::runtime_error(msg.str());
    }
    LayerMask mask;
    mask.blk_type = blk_type;
    mask.mask_blk_type = mask_blk_type;

    while(std::getline(in, line)) {
        trim(line);
        if (line == END)
            break;
        tokens = get_tokens(line);
        if (tokens.size() % 2) {
            throw ::runtime_error("expect coordinates pair, got " + line);
        }
        uint32_t src_x = stou(tokens[0]);
        uint32_t src_y = stou(tokens[1]);

        std::pair<uint32_t, uint32_t> src_pos = {src_x, src_y};
        if (mask.mask_pos.find(src_pos) == mask.mask_pos.end())
            mask.mask_pos.insert({src_pos, {}});

        for (uint32_t i = 2; i < tokens.size(); i += 2) {
            uint32_t x = stou(tokens[i]);
            uint32_t y = stou(tokens[i + 1]);
            mask.mask_pos[src_pos].emplace_back(std::make_pair(x, y));
        }
    }

    layout.add_layer_mask(mask);
}

Layout load_layout(const std::string &filename) {
    if (!::exists(filename))
        throw ::runtime_error(filename + " does not exist");
    ::ifstream in;
    in.open(filename);

    Layout layout;


    ::string line;
    // the first line has to be meta data line
    // we don't support comments yet
    while(std::getline(in, line)) {
        trim(line);
        auto tokens = get_tokens(line);
        if (tokens[0] == "LAYOUT") {
            parse_layout(in, layout, tokens);
        } else if (tokens[0] == "MASK") {
            parse_mask(in, layout, tokens);
        } else {
            throw ::runtime_error("expect header. got " + line);
        }

    }
    return layout;
}

void dump_layout(const Layout &layout, const std::string &filename) {
    std::ofstream out;
    out.open(filename, std::ofstream::out);

    auto [width, height] = layout.get_size();

    auto blk_types = layout.get_layer_types();

    for (const auto &blk_type : blk_types) {
        const auto &layer = layout.get_layer(blk_type);
        auto major = layout.get_priority_major(blk_type);
        auto minor = layout.get_priority_minor(blk_type);
        out << "LAYOUT " << blk_type << " " << major << " " << minor << endl;
        out << BEGIN << endl;
        for (uint32_t y = 0; y < height; y++) {
            for (uint32_t x = 0; x < width; x++) {
                if (layer[{x, y}])
                    out << "1";
                else
                    out << "0";
            }
            out << endl;
        }
        out << END << endl;
    }

    // dump masks as well
    auto masks = layout.get_layer_masks();
    for (const auto &[blk_type, mask] : masks) {
        const auto mask_type = mask.mask_blk_type;
        out << "MASK " << blk_type << " " << mask_type << endl << BEGIN << endl;
        for (const auto &[blk_pos, positions] : mask.mask_pos) {
            auto [src_x, src_y] = blk_pos;
            out << "(" << src_x << ", " << src_y << ")";
            for (uint32_t i = 0; i < positions.size(); i++) {
                auto [x, y] = positions[i];
                out << " (" << x << ", " << y << ") ";
                if (i % 8 == 7 && i != positions.size() - 1) {
                    out << endl << "(" << src_x << ", " << src_y << ")";
                }
            }
        }
        out << endl << END << endl;
    }

    out.close();
}

void save_placement(const std::map<std::string, std::pair<int, int>> &placement,
                    const std::map<std::string, std::string> &id_to_name,
                    const std::string &filename) {
    std::ofstream out;
    out.open(filename, std::ofstream::out);

    // write the header
    std::string header = "Block Name\t\t\tX\tY\t\t#Block ID";
    out << header << endl;
    for (uint32_t i = 0; i < header.length(); i++) {
        out << "-";
    }
    out << endl;
    // sort the list by blk_id (int value)
    auto cmp = [&id_to_name](::string a, ::string b) -> bool {
        return id_to_name.at(a) < id_to_name.at(b);
    };
    std::set<::string, decltype(cmp)> blk_ids(cmp);
    for (auto const &iter: placement) {
        blk_ids.insert(iter.first);
    }

    // write the connect
    for (auto const &blk_id : blk_ids) {
        auto const [x, y] = placement.at(blk_id);
        out << id_to_name.at(blk_id) << "\t\t" << x << "\t"
            << y << "\t\t#" << blk_id << endl;
    }

    out.close();
}

std::map<std::string, std::string>
load_id_to_name(const std::string &filename) {
    if (!::exists(filename))
        throw ::runtime_error(filename + " does not exist");
    ::ifstream in;
    in.open(filename);

    ::string line;
    std::map<std::string, std::string> id_to_name;
    bool in_section = false;
    while(std::getline(in, line)) {
        trim(line);
        if (in_section) {
            if (line[0] == '#') {
                continue;
            } else if (line.empty()) {
                break;
            }
            auto tokens = get_tokens(line);
            if (tokens.size() != 2)
                throw ::runtime_error("expected line " + line);
            auto blk_id = tokens[0];
            auto name = tokens[1];
            id_to_name.insert({blk_id, name});
            continue;
        }
        in_section = line == "ID to Names:";
    }
    return id_to_name;
}
