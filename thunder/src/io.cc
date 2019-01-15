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
        auto x = stou(tokens[1]);
        auto y = stou(tokens[2]);
        auto blk_id = tokens[3].substr(1, ::string::npos);

        placement.insert({blk_id, {x, y}});
        line_num++;
    }

    return placement;
}


Layout load_layout(const std::string &filename) {
    if (!::exists(filename))
        throw ::runtime_error(filename + " does not exist");
    ::ifstream in;
    in.open(filename);

    Layout layout;

    const ::string BEGIN = "BEGIN";
    const ::string END = "END";

    ::string line;
    // the first line has to be meta data line
    // we don't support comments yet
    while(std::getline(in, line)) {
        trim(line);
        auto tokens = get_tokens(line);
        if (tokens.size() != 4 || tokens[0] != "LAYOUT") {
            throw ::runtime_error("expect layer header. got " + line);
        }
        char blk_type = tokens[1][0];
        uint32_t major = stou(tokens[2]);
        uint32_t minor = stou(tokens[3]);

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
    return layout;
}

void dump_layout(const Layout &layout, const std::string &filename) {
    std::ofstream out;
    out.open(filename, std::ofstream::out);

    const ::string BEGIN = "BEGIN";
    const ::string END = "END";

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
}