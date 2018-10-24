#ifndef THUNDER_GLOBALPLACER_HH
#define THUNDER_GLOBALPLACER_HH

#include "include/spline.h"
#include "anneal.hh"


struct ClusterBox {
    double xmin = 0;
    double xmax = 0;
    double ymin = 0;
    double ymax = 0;
    double cx = 0;
    double cy = 0;

    std::string id;
    int index = 0;
    int clb_size = 0;
    int width = 0;
    bool fixed = false;
    std::set<int> nets = {};
};

struct ClusterMove {
    uint64_t box_index = 0;
    int dx;
    int dy;
};

class GlobalPlacer : public SimAnneal {
public:
    GlobalPlacer(std::map<std::string, std::set<std::string>> clusters,
                 std::map<std::string, std::vector<std::string>> netlists,
                 std::map<std::string, std::pair<int, int>> fixed_pos,
                 std::vector<std::vector<char>> board_layout,
                 char clb_type,
                 bool reg_fold);

    void solve();
    void anneal() override;
    std::map<std::string, std::map<char, std::set<std::pair<int, int>>>>
    realize();

protected:
    void move() override;
    void commit_changes() override;
    double energy() override;

private:

    double line_search(const std::vector<std::pair<double, double>> &grad_f);
    double eval_f(double overlap_param=1) const;
    void eval_grad_f(std::vector<std::pair<double, double>> &, const uint32_t);
    double find_beta(const std::vector<std::pair<double, double>> &grad_f,
                     const std::vector<std::pair<double, double>> &last_grad_f);
    void adjust_force(std::vector<std::pair<double, double>> &grad_f);
    void init_place();
    void legalize_box();

    void setup_reduced_layout();
    void create_fixed_boxes();
    void create_boxes();
    double compute_hpwl() const;
    void
    find_exterior_set(const std::vector<std::vector<bool>> &bboard,
                      const std::set<std::pair<int, int>> &assigned,
                      std::vector<std::pair<int, int>> &empty_cells,
                      const int &max_dist) const;

    std::pair<std::vector<std::vector<int>>, std::map<std::string, uint32_t>>
    collapse_netlist(std::map<std::string, std::vector<std::string>>);

    char clb_type_;
    bool reg_fold_;
    std::map<std::string, std::set<std::string>> clusters_;
    std::vector<std::vector<int>> netlists_;
    std::map<std::string, std::pair<int, int>> fixed_pos_;
    std::vector<std::vector<char>> board_layout_;
    std::vector<std::vector<char>> reduced_board_layout_;
    std::vector<ClusterBox> boxes_;
    std::vector<std::map<char, tk::spline>> legal_spline_;
    std::map<uint32_t, uint32_t> column_mapping_;
    randutils::random_generator<std::mt19937> global_rand_;

    // helper values
    uint32_t reduced_width_ = 0;
    uint32_t reduced_height_ = 0;
    std::map<char, std::vector<double>> hidden_columns;

    // CG parameters
    double hpwl_param_ = .05;
    double potential_param_ = 0.1;
    double legal_param_ = .05;

    // Anneal parameters
    double anneal_param_ = 10;
    ClusterMove current_move_ = {};

    // TODO: add it abck to board info
    uint32_t clb_margin_ = 1;
};


#endif //THUNDER_GLOBALPLACER_HH