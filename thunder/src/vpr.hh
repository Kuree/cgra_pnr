#ifndef THUNDER_VPR_HH
#define THUNDER_VPR_HH
#include "detailed.hh"


class VPRPlacer : public DetailedPlacer {
public:
    VPRPlacer(std::map<std::string, std::pair<int, int>> init_placement,
              std::map<std::string, std::vector<std::string>> netlist,
              std::map<char,
                      std::vector<std::pair<int, int>>> available_pos,
              std::map<std::string, std::pair<int, int>> fixed_pos,
              char clb_type,
              bool fold_reg);

    void anneal() override;
};


#endif //THUNDER_VPR_HH
