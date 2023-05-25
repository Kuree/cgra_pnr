#ifndef THUNDER_MULTI_PLACE_HH
#define THUNDER_MULTI_PLACE_HH
#include <map>
#include <set>
#include <vector>
#include "layout.hh"


std::map<std::string, std::pair<int, int>>  multi_place(
        const std::map<std::string, std::set<std::string>> &clusters,
        const std::map<std::string, std::map<char,
                                    std::vector<std::pair<int, int>>>> &cells,
        const std::map<std::string, std::map<std::string,
                                    std::vector<std::string>>> &netlists,
        const std::map<std::string, std::map<std::string,
                                    std::pair<int, int>>> &fixed_blocks,
        char clb_type, bool fold_reg, uint32_t seed);

std::map<std::string, std::pair<int, int>>  multi_place(
        const std::map<std::string, std::set<std::string>> &clusters,
        const std::map<std::string, std::map<char,
                std::vector<std::pair<int, int>>>> &cells,
        const std::map<std::string, std::map<std::string,
                std::vector<std::string>>> &netlists,
        const std::map<std::string, std::map<std::string,
                std::pair<int, int>>> &fixed_blocks,
        char clb_type, bool fold_reg);

std::map<std::string, std::pair<int, int>>
detailed_placement(const std::map<std::string, std::set<std::string>> &clusters,
                   const std::map<std::string, std::vector<std::string>> &netlist,
                   const std::map<std::string, std::pair<int, int>> &fixed_pos,
                   const std::map<std::string,
                         std::map<char,
                                  std::vector<std::pair<int, int>>>> &gp_result,
                   const Layout &layout);

#endif //THUNDER_MULTI_PLACE_HH
