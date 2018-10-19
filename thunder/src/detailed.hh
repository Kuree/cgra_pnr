//
// Created by keyi on 10/17/18.
//

#ifndef THUNDER_DETAILED_HH
#define THUNDER_DETAILED_HH

#include "util.hh"
#include "anneal.hh"

struct DetailedMove {
    int blk_id;
    Point new_pos;
};
bool operator< (const DetailedMove &m1, const DetailedMove &m2);

class DetailedPlacer: public SimAnneal {
public:
    DetailedPlacer(std::vector<std::string> cluster_blocks,
                   std::map<std::string, std::vector<std::string>> netlist,
                   std::map<char, std::vector<std::pair<int, int>>> available_pos,
                   std::map<std::string, std::pair<int, int>> fixed_pos,
                   char clb_type,
                   bool fold_reg);
    void move() override;
    double energy() override;
    void commit_changes() override;
    std::map<std::string, std::pair<int, int>> realize();

private:
    std::vector<Instance> instances;
    std::vector<Net> netlist;
    std::map<char, std::vector<Point>> available_pos;
    std::vector<Instance> fixed_pos;
    std::map<Point, std::pair<int, int>> board;
    std::set<DetailedMove> moves;
    char clb_type;
    bool fold_reg;

    randutils::random_generator<std::mt19937> detail_rand_;

    double init_energy() override;
};


#endif //THUNDER_DETAILED_HH
