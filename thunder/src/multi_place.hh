#ifndef THUNDER_MULTI_PLACE_HH
#define THUNDER_MULTI_PLACE_HH
#include <map>
#include <set>
#include <vector>

std::map<std::string, std::pair<int, int>>  multi_place(
        std::map<int, std::set<std::string>> clusters,
        std::map<int, std::map<char, std::set<std::pair<int, int>>>> cells,
        std::map<int, std::map<std::string, std::vector<std::string>>> netlists,
        std::map<int, std::map<std::string, std::pair<int, int>>> fixed_blocks,
        char clb_type, bool fold_reg);

#endif //THUNDER_MULTI_PLACE_HH
