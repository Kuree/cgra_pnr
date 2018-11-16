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
                   std::map<char,
                            std::vector<std::pair<int, int>>> available_pos,
                   std::map<std::string, std::pair<int, int>> fixed_pos,
                   char clb_type,
                   bool fold_reg,
                   double step_ratio = 30);
    DetailedPlacer(std::map<std::string, std::pair<int, int>> init_placement,
                   std::map<std::string, std::vector<std::string>> netlist,
                   std::map<char,
                            std::vector<std::pair<int, int>>> available_pos,
                   std::map<std::string, std::pair<int, int>> fixed_pos,
                   char clb_type,
                   bool fold_reg,
                   double step_ratio = 1);
    double energy() override;
    std::map<std::string, std::pair<int, int>> realize();

protected:
    void move() override;
    void commit_changes() override;

    std::vector<Instance> instances_;
    std::vector<Net> netlist_;
    std::vector<int> instance_ids_;
    std::set<DetailedMove> moves_;
    std::map<char, std::pair<uint64_t, uint64_t>> instance_type_index_;
    char clb_type_;
    bool fold_reg_;

    randutils::random_generator<std::mt19937> detail_rand_;

    double init_energy() override;
    bool is_reg_net(const Instance &ins, const Point &next_pos);

    std::map<int, std::set<int>> reg_no_pos_;

private:
    void init_place_regular(const std::vector<std::string> &cluster_blocks,
                            std::map<std::string, int> &blk_id_dict,
                            std::map<char,
                                     std::vector<std::pair<int, int>>>
                                     &available_pos);
    void init_place_reg(const std::vector<std::string> &cluster_blocks,
                        std::map<std::string, int> &blk_id_dict);
    // automatically set the fold reg
    // will speed up a lot if there is no registers
    void set_fold_reg(const std::vector<std::string> &cluster_blocks,
                      bool fold_reg);

    void compute_reg_no_pos(const std::vector<std::string> &cluster_blocks,
                            std::map<std::string,
                                     std::vector<std::string>> &nets,
                            std::map<std::string, int> &blk_id_dict);

    void legalize_reg();

    void process_netlist(const std::map<std::string,
                                        std::vector<std::string>> &netlist,
                         std::map<std::string, int> &blk_id_dict);

    void create_fixed_pos(const std::map<std::string,
                                         std::pair<int, int>> &fixed_pos,
                          std::map<std::string, int> &blk_id_dict);

    void compute_blk_pos(const std::vector<std::string> &cluster_blocks,
                         std::map<char,
                                  std::vector<std::pair<int,
                                                        int>>> &available_pos,
                         std::map<char, std::vector<std::string>> &blk_counts,
                         std::map<char, int64_t> &empty_spaces) const;

    void copy_init_placement(
            std::map<std::string, std::pair<int, int>> &init_placement,
            std::map<char, std::vector<std::pair<int, int>>> &available_pos,
            const std::vector<std::string> &cluster_blocks,
            std::map<std::string, int> &blk_id_dict);
};


#endif //THUNDER_DETAILED_HH
