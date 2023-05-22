#include "../src/util.hh"
#include "../src/detailed.hh"
#include "../src/multi_place.hh"
#include <iostream>

#define SINGLE_THREAD 1

using namespace std;

int main() {

#if SINGLE_THREAD
    auto blks1 = vector<string>{"p1", "p2", "p3", "p4", "r1", "r2"};
    auto available_pos1 = map<char, vector<pair<int, int>>>();
    available_pos1['p'] = vector<pair<int, int>>{make_pair(1, 1),
                                                 make_pair(1, 2),
                                                 make_pair(1, 3),
                                                 make_pair(1, 4)};
    map<std::string, std::pair<int, int>> fixed_pos;
#else
    auto blks1 = set<string>{"p1", "p2", "p3", "p4", "r1", "r2"};
    auto available_pos1 = map<char, set<pair<int, int>>>();
    available_pos1['p'] = set<pair<int, int>>{make_pair(1, 1),
                                                make_pair(1, 2),
                                                make_pair(1, 3),
                                                make_pair(1, 4)};
    map<int, map<std::string, std::pair<int, int>>> fixed_pos =
        {{1, {}}, {2, {}}};
#endif

    auto blks2 = set<string>{"p5", "p6", "p7", "p8"};

    auto available_pos2 = map<char, set<pair<int, int>>>();
    available_pos2['p'] = set<pair<int, int>>{make_pair(2, 1),
                                                 make_pair(2, 2),
                                                 make_pair(2, 3),
                                                 make_pair(2, 4)};



    map<std::string, std::vector<std::string>> netlist1;
    netlist1["1"] = vector<string>{"p1", "r1"};
    netlist1["2"] = vector<string>{"p3", "p4"};
    netlist1["2"] = vector<string>{"r1", "p2"};

    std::map<std::string, std::vector<std::string>> netlist2;
    netlist2["1"] = vector<string>{"p5", "p6"};
    netlist2["2"] = vector<string>{"p7", "p8"};

#if !SINGLE_THREAD
    map<int, set<string>> blks = {{1, blks1},
                                  {2, blks2}};
    map<int, map<std::string, std::vector<std::string>>> netlists =
            {{1, netlist1}, {2, netlist2}};
    map<int, map<char, set<pair<int, int>>>> available_pos =
            {{1, available_pos1}, {2, available_pos2}};
#endif

#if SINGLE_THREAD
    auto dp = DetailedPlacer(blks1, netlist1, available_pos1, fixed_pos, 'p',
                             true);
    dp.anneal();
    auto result = dp.realize();
    dp = DetailedPlacer(result, netlist1, available_pos1, fixed_pos, 'p', true);
    dp.anneal();
    result = dp.realize();
#else
    auto result = multi_place(blks, available_pos, netlists, fixed_pos, 'p', true);
#endif

    for (const auto &iter : result) {
        cerr << iter.first << " " << Point(iter.second) << endl;
    }
}