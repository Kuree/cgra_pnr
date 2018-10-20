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
    std::vector<Instance> fixed_pos;
    std::set<DetailedMove> moves_;
    char clb_type;
    bool fold_reg_;
    std::map<Point, std::pair<int, int>> board_;

    randutils::random_generator<std::mt19937> detail_rand_;

    double init_energy() override;

    std::map<std::string, std::set<int>> reg_no_pos_;

    void init_place_regular(const std::vector<std::string> &cluster_blocks,
                            std::map<std::string, int> &blk_id_dict,
                            std::map<char, std::vector<std::pair<int, int>>> &available_pos);
    void init_place_reg(const std::vector<std::string> &cluster_blocks,
                        std::map<std::string, int> &blk_id_dict);
    // automatically set the fold reg
    // will speed up a lot if there is no registers
    void set_fold_reg(const std::vector<std::string> &cluster_blocks,
                      bool fold_reg);

    void compute_reg_no_pos(const std::vector<std::string> &cluster_blocks,
                            std::map<std::string, std::vector<std::string>> &nets,
                            std::map<std::string, int> &blk_id_dict);

    bool is_reg_net(const Instance &ins, const Point &next_pos);
};


#endif //THUNDER_DETAILED_HH
