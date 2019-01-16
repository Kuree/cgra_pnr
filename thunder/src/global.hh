#ifndef THUNDER_GLOBALPLACER_HH
#define THUNDER_GLOBALPLACER_HH

#include "include/spline.h"
#include "anneal.hh"
#include "layout.hh"
#include <unordered_set>


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
    int height = 0;
    bool fixed = false;
    std::set<int> nets = {};

    ClusterBox() = default;
    ClusterBox(const ClusterBox &box) { assign(box); }

    void assign(const ClusterBox &box);
};

struct ClusterMove {
    ClusterBox box1;
    ClusterBox box2;
};

class GlobalPlacer : public SimAnneal {
public:
    GlobalPlacer(std::map<std::string, std::set<std::string>> clusters,
                 std::map<std::string, std::vector<std::string>> netlists,
                 std::map<std::string, std::pair<int, int>> fixed_pos,
                 const Layout &board_layout);

    void solve();
    void anneal() override;
    std::map<std::string, std::map<char, std::set<std::pair<int, int>>>>
    realize();
    void set_seed(uint32_t seed);

    double anneal_param_factor = 1.0;
    char EMPTY_BLK = ' ';
    std::set<char> IO_BLK = {'i', 'I'};

protected:
    void move() override;
    void commit_changes() override;
    double energy() override;
    double init_energy() override;

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

    void get_clb_types_();

    // SA
    void bound_box(ClusterBox &box);

    char clb_type_;
    std::map<std::string, std::set<std::string>> clusters_;
    std::vector<std::vector<int>> netlists_;
    std::map<std::string, std::pair<int, int>> fixed_pos_;
    Layout board_layout_;
    std::vector<std::vector<char>> reduced_board_layout_;
    std::vector<ClusterBox> boxes_;
    std::vector<std::map<char, tk::spline>> legal_spline_;
    std::map<uint32_t, uint32_t> column_mapping_;
    std::map<std::string, std::map<char, int>> box_dsp_blocks_;
    std::map<std::string, uint32_t> intra_count_;
    randutils::random_generator<std::mt19937> global_rand_;
    std::unordered_set<char> clb_types_;

    // helper values
    uint32_t reduced_width_ = 0;
    uint32_t reduced_height_ = 0;
    double aspect_ratio_ = 0;
    std::map<char, std::set<double>> hidden_columns;
    std::vector<double> gaussian_table_;
    double gaussian_sigma_2_ = 1;
    void compute_gaussian_table();

    // CG parameters
    double hpwl_param_ = .05;
    double potential_param_ = 0.05;
    double legal_param_ = .05;
    double aspect_param_ = 1;

    // Anneal parameters
    double anneal_param_ = 1;
    ClusterMove current_move_ = {};
    ClusterMove backup_move = {};

    // TODO: add it abck to board info
    uint32_t clb_margin_ = 1;
};


#endif //THUNDER_GLOBALPLACER_HH
