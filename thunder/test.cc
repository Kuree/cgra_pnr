#include "src/detailed.hh"
#include <iostream>
using namespace std;

int main() {
    auto blks = vector<string>{"p1", "p2", "p3", "p4"};
    auto available_pos = map<char, vector<pair<int, int>>>();
    available_pos['p'] = vector<pair<int, int>>{make_pair(1, 1),
                                                make_pair(1, 2),
                                                make_pair(1, 3),
                                                make_pair(1, 4)};
    std::map<std::string, std::pair<int, int>> fixed_pos;

    std::map<std::string, std::vector<std::string>> netlist;
    netlist["1"] = vector<string>{"p1", "p2"};
    netlist["2"] = vector<string>{"p3", "p4"};

    DetailedPlacer placer(blks, netlist, available_pos, fixed_pos, 'p', false);

    placer.anneal();
    auto result = placer.realize();
    for (const auto &ins : result)
        cerr << ins.first << " " << ins.second << endl;
}