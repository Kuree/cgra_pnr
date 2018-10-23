#ifndef THUNDER_GLOBALPLACER_HH
#define THUNDER_GLOBALPLACER_HH

#include "include/spline.h"
#include "anneal.hh"


struct ClusterBox {
    int xmin = 0;
    int xmax = 0;
    int ymin = 0;
    int ymax = 0;
    double cx = 0;
    double cy = 0;

    std::string id;
    int index = 0;
    int clb_size = 0;
    bool fixed = false;
    std::set<int> nets = {};
};

class GlobalPlacer : SimAnneal {
public:
    GlobalPlacer(std::map<std::string, std::set<std::string>> clusters,
                 std::map<std::string, std::vector<std::string>> netlists,
                 std::map<std::string, std::pair<int, int>> fixed_pos,
                 std::vector<std::vector<char>> board_layout,
                 char clb_type,
                 bool reg_fold);

    void solve();
    void anneal();
    std::map<int, std::map<std::string, std::pair<int, int>>> realize();
private:

    double line_search(const std::vector<std::pair<double, double>> &grad_f,
                       const uint32_t &current_step);
    double eval_f();
    void eval_grad_f(std::vector<std::pair<double, double>> &);
    double find_beta(const std::vector<std::pair<double, double>> &grad_f,
                     const std::vector<std::pair<double, double>> &last_grad_f);
    void init_place();

    void setup_reduced_layout();
    void create_fixed_boxes();
    void create_boxes();
    void compute_gaussian_grad();

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

    // helper values
    uint32_t reduced_width_ = 0;
    uint32_t reduced_height_ = 0;
    std::map<char, std::vector<double>> hidden_columns;

    // gradient
    double sigma_x = 5;
    double sigma_y = 5;
    std::vector<std::vector<double>> gaussian_gradient_;

    // CG parameters
    double hpwl_param_ = 100;
    double potential_param_ = 30;
    double legal_param_ = 20;
};


#endif //THUNDER_GLOBALPLACER_HH
