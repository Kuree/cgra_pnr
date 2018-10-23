#include <string>
#include <cmath>
#include "global.hh"

using std::map;
using std::vector;
using std::string;
using std::move;
using std::pair;
using std::set;

GlobalPlacer::GlobalPlacer(::map<std::string, ::set<::string>> clusters,
                           ::map<::string, ::vector<::string>> netlists,
                           std::map<std::string, std::pair<int, int>> fixed_pos,
                           ::vector<::vector<char>> board_layout,
                           char clb_type,
                           bool reg_fold) :
                           clb_type_(clb_type),
                           reg_fold_(reg_fold),
                           clusters_(::move(clusters)),
                           netlists_(),
                           fixed_pos_(::move(fixed_pos)),
                           board_layout_(::move(board_layout)),
                           reduced_board_layout_(),
                           boxes_(),
                           legal_spline_(),
                           column_mapping_(),
                           hidden_columns(),
                           gaussian_gradient_(){
    // first compute the reduced board_layout
    setup_reduced_layout();
    create_fixed_boxes();
    // set up the boxes
    create_boxes();

    // setup reduced netlist
    auto [nets, intra_count] = this->collapse_netlist(::move(netlists));
    netlists_ = nets;

    for (auto const &iter : intra_count)
        printf("%s %d\n", iter.first.c_str(), iter.second);

}

void GlobalPlacer::setup_reduced_layout() {
    const int margin = 2;   // TODO: fix this
    std::vector<char> lane_types;
    for (auto &row : board_layout_) {
        const char blk_type = row[margin];
        lane_types.emplace_back(blk_type);
    }
    // create the new reduced_board and mapping between the new one and the old
    // one

    for (uint32_t y = 0; y < board_layout_.size(); y++) {
        reduced_board_layout_.emplace_back(::vector<char>());
        uint32_t new_x = 0;
        for (uint32_t x = 0; x < board_layout_[y].size(); x++) {
            const char blk_type = lane_types[x];
            if (blk_type != clb_type_ && blk_type != ' ') {
                // skip this one
                if (hidden_columns.find(blk_type) != hidden_columns.end()) {
                    hidden_columns[blk_type] = {};
                }
                hidden_columns[blk_type].emplace_back(new_x + 0.5);
            } else {
                assert (new_x == reduced_board_layout_[y].size());
                reduced_board_layout_[y].emplace_back(blk_type);
                if (column_mapping_.find(new_x) == column_mapping_.end()) {
                    column_mapping_[new_x] = x;
                } else {
                    if (x != column_mapping_[new_x])
                        throw std::runtime_error("error in processing board"
                                                 "layout");
                }
                new_x++;
            }
        }
    }
    // sanity check
    for (auto const &y : reduced_board_layout_) {
        if (y.size() != reduced_board_layout_[margin].size())
            throw std::runtime_error("failed layout check at " +
                                     std::to_string(y.size()));
        else
            for (const auto &t : y)
                printf("%c", t);
        printf("\n");
    }

    // set helper values
    reduced_height_ = (uint32_t)reduced_board_layout_.size();
    reduced_width_ = (uint32_t)reduced_board_layout_[0].size();

    // compute gradient
    compute_gaussian_grad();
}

void GlobalPlacer::create_fixed_boxes() {
    for (const auto &iter : fixed_pos_) {
        ClusterBox box {
            .xmin = iter.second.first,
            .xmax = iter.second.first,
            .ymin = iter.second.second,
            .ymax = iter.second.second,
            .cx = (double)iter.second.first,
            .cy = (double)iter.second.second,
            .id = iter.first,
            .index = (int)boxes_.size(),
            .fixed = true
        };
        boxes_.emplace_back(box);
    }
}

void GlobalPlacer::create_boxes() {
    // allocate more because we have some fixed boxes
    legal_spline_.resize(boxes_.size() + clusters_.size());
    for (const auto &iter : clusters_) {
        auto const &cluster_id = iter.first;
        int box_index = (int)boxes_.size();
        ::map<char, int> dsp_blocks;
        ClusterBox box {
            .id = cluster_id,
            .index = box_index,
            .clb_size = 0};
        for (auto const &blk_name : iter.second) {
            char blk_type = blk_name[0];
            if (blk_type == clb_type_) {
                box.clb_size++;
            } else {
                if (reg_fold_ && blk_type == 'r')
                    continue;
                if (dsp_blocks.find(blk_type) == dsp_blocks.end())
                    dsp_blocks[blk_type] = 0;
                dsp_blocks[blk_type]++;
            }
        }
        boxes_.emplace_back(box);

        // calculate the legal cost function
        ::map<char, tk::spline> splines;
        for (auto const &iter_dsp : dsp_blocks) {
            auto height = (uint32_t)std::ceil(std::sqrt(box.clb_size));
            const char blk_type = iter_dsp.first;

            ::vector<double> cost;
            ::vector<double> x_data;
            auto dsp_columns = hidden_columns[blk_type];
            for (uint32_t x = 0; x < reduced_width_ - height; x++) {
                // try to place it on every x and then see how many blocks left
                // TODO: fix DSP block height
                int blk_need = iter_dsp.second;
                for (uint32_t xx = x; xx < x + height; xx++) {
                    for (const auto &xxx : dsp_columns) {
                        if (xxx - 1 < xx && xxx + 1 > xx) {
                            // found some
                            blk_need -= height;
                        }
                    }
                }
                if (blk_need <= 0)
                    cost.emplace_back(0);
                else
                    cost.emplace_back(blk_need);
                x_data.emplace_back(x);
            }
            // compute the spline for this cost function
            tk::spline spline;
            spline.set_points(x_data, cost);
            splines[blk_type] = spline;
        }
        legal_spline_[box.index] = splines;
    }
}

::pair<::vector<::vector<int>>, ::map<::string, uint32_t>>
GlobalPlacer::collapse_netlist(::map<::string,
                                     ::vector<::string>> raw_netlists) {
    ::vector<::vector<::string>> netlist;
    ::map<::string, uint32_t> intra_cluster_count;
    ::map<::string, ::string> blk_index;

    // create id->index for boxes
    ::map<::string, int> id_to_index;
    for (auto const &box : boxes_)
        id_to_index[box.id] = box.index;

    // reserve space
    netlist.reserve(raw_netlists.size());

    for (auto const &iter : clusters_) {
        intra_cluster_count[iter.first] = 0;
        for (auto const &blk : iter.second)
            blk_index[blk] = iter.first;
    }

    // fixed position is its own stuff
    for (auto const &iter : fixed_pos_)
        blk_index[iter.first] = iter.first;

    // change it to the new netlist
    for (const auto &net_iter : raw_netlists) {
        ::vector<::string> new_net;
        new_net.reserve(net_iter.second.size());
        for (const auto &blk : net_iter.second) {
            if (blk_index.find(blk) == blk_index.end())
                throw std::runtime_error(blk + " not found in blk_index");
            new_net.emplace_back(blk_index[blk]);
        }
        netlist.emplace_back(new_net);
    }

    // second pass to find out any intra connection
    ::set<uint32_t> remove_index;
    for (uint32_t i = 0; i < netlist.size(); i++) {
        bool self_connect = true;
        auto const &net = netlist[i];
        for (auto const &blk : net) {
            if (blk != net[0]) {
                self_connect = false;
                break;
            }
        }
        if (self_connect)
            remove_index.insert(i);
    }

    // actual result
    ::vector<::vector<int>> result;
    result.reserve(raw_netlists.size() - remove_index.size());
    for (uint32_t i = 0; i < netlist.size(); i++) {
        if (remove_index.find(i) != remove_index.end()) {
            ::string const &cluster_id = netlist[i][0];
            if (intra_cluster_count.find(cluster_id) ==
                intra_cluster_count.end()) {
                intra_cluster_count[cluster_id] = 0;
            }
            intra_cluster_count[cluster_id]++;
        } else {
            ::set<int> net;
            for (auto const &id : netlist[i]) {
                if (id_to_index.find(id) == id_to_index.end())
                    throw std::runtime_error("unable to find id " + id);
                net.insert(id_to_index[id]);
            }
            ::vector<int> new_net;
            new_net.assign(net.begin(), net.end());
            // add the net to box net as well;
            for (const auto &box_index : new_net) {
                boxes_[box_index].nets.insert((int)result.size());
            }
            if (new_net.size() == 1) {
                throw std::runtime_error("error in processing netlist");
            }
            result.emplace_back(new_net);
        }
    }
    // sanity check
    if (result.size() != (raw_netlists.size() - remove_index.size()))
        throw std::runtime_error("error in condensing netlist");

    return {result, intra_cluster_count};
}

void GlobalPlacer::compute_gaussian_grad() {
    ::vector<double> grad_x;
    ::vector<double> grad_y;

    const auto x_mid = (reduced_width_ - 1) / 2.0;
    const auto y_mid = (reduced_height_ - 1) / 2.0;

    const auto x_spread = 1. / (sigma_x * sigma_x * 2);
    const auto y_spread = 1. / (sigma_y * sigma_y * 2);

    grad_x.resize(reduced_width_);
    for (uint32_t i = 0;  i < reduced_width_;  i++) {
        auto const x = i - x_mid;
        grad_x[i] = std::exp(-x * x * x_spread);
    }

    grad_y.resize(reduced_height_);
    for (uint32_t i = 0;  i < reduced_height_;  i++) {
        auto y = i - y_mid;
        grad_y[i] = std::exp(-y * y * y_spread);
    }

    double denominator = 0;
    gaussian_gradient_.resize(reduced_height_);
    for (uint32_t y = 0; y < reduced_height_; y++) {
        gaussian_gradient_[y].resize(reduced_width_);
        for (uint32_t x = 0; x < reduced_width_; x++) {
            double value = grad_x[x] * grad_y[y];
            denominator += value;
            gaussian_gradient_[y][x] = value;
        }
    }

    for (uint32_t y = 0; y < reduced_height_; y++) {
        for (uint32_t x = 0; x < reduced_width_; x++) {
            gaussian_gradient_[y][x] /= denominator;
        }
    }
}

void GlobalPlacer::solve() {

}

double GlobalPlacer::eval_f() {
    // first part is HPWL.
    double hpwl = 0;
    for (const auto & net : netlists_) {
        int N = (int)net.size();
        // star model
        double x_sum = 0;
        double y_sum = 0;

        for (const auto &index : net) {
            x_sum += boxes_[index].cx;
            y_sum += boxes_[index].cy;
        }

        for (const auto &index : net) {
            auto x = boxes_[index].cx;
            auto y = boxes_[index].cy;
            hpwl += (x - x_sum / N) * (x - x_sum / N);
            hpwl += (y - y_sum / N) * (y - y_sum / N);
        }
    }

    // second part is the spreading potential
    double overlap = 0;
    for (const auto &box : boxes_) {
        if (box.fixed)
            continue;
        int x = (int)box.cx;
        int y = (int)box.cy;

        overlap += gaussian_gradient_[y][x];
    }

    // third part is the legalization
    double legal = 0;
    for (const auto &box : boxes_) {
        if (box.fixed)
            continue;
        // spline is calculated based on the xmin
        int x = box.xmin;
        for (const auto &iter : legal_spline_[box.index]) {
            // TODO: add different legal energy here
            legal += iter.second(x);
        }
    }

    return hpwl * hpwl_param_ + overlap * potential_param_ +
           legal * legal_param_;
}

void  GlobalPlacer::eval_grad_f(::vector<::pair<double, double>> &grad_f) {
    // first part is HWPL
    ::vector<::pair<double, double>> hpwl;
    ::vector<::pair<double, double>> overlap;
    ::vector<::pair<double, double>> legal;

    // resize
    grad_f.resize(boxes_.size());
    hpwl.resize(boxes_.size());
    overlap.resize(boxes_.size());
    legal.resize(boxes_.size());

    // set to zero
    const auto zero = std::make_pair(0, 0);
    std::fill(grad_f.begin(), grad_f.end(), zero);
    std::fill(hpwl.begin(), hpwl.end(), zero);
    std::fill(overlap.begin(), hpwl.end(), zero);
    std::fill(legal.begin(), hpwl.end(), zero);

    for (const auto & net : netlists_) {
        int N = (int)net.size();
        // star model
        double x_sum = 0;
        double y_sum = 0;

        for (const auto &index : net) {
            x_sum += boxes_[index].cx;
            y_sum += boxes_[index].cy;
        }

        for (const auto &index : net) {
            auto x = boxes_[index].cx;
            auto y = boxes_[index].cy;
            hpwl[index].first += 2.0 / (N * N) * ((N * N - 2 * N + 2) * x -
                                 2 * (N - 1) * (x_sum - x));
            hpwl[index].second += 2.0 / (N * N) * ((N * N - 2 * N + 2) * y -
                                  2 * (N - 1) * (y_sum - y));
        }
    }
    // second part is the spreading potential

    const auto x_spread_2 = 1. / (sigma_x * sigma_x);
    const auto y_spread_2 = 1. / (sigma_y * sigma_y);
    for (const auto &box : boxes_) {
        if (box.fixed)
            continue;
        int x = (int)box.cx;
        int y = (int)box.cy;

        overlap[box.index].first += gaussian_gradient_[y][x] *
                                    (-x / x_spread_2);
        overlap[box.index].second += gaussian_gradient_[y][x] *
                                     (-y / y_spread_2);
    }

    // third part is the legalization
    for (const auto &box : boxes_) {
        if (box.fixed)
            continue;
        // spline is calculated based on the xmin
        int x = box.xmin;
        for (const auto &iter : legal_spline_[box.index]) {
            // TODO: add different legal energy here
            legal[box.index].first += iter.second.deriv(x, 1);
        }
    }

    for (const auto &box : boxes_) {
        auto index = box.index;
        grad_f[index].first = hpwl[index].first * hpwl_param_
                              + overlap[index].first * potential_param_
                              + legal[index].first * legal_param_;
        grad_f[index].second = hpwl[index].second * hpwl_param_
                               + overlap[index].second * potential_param_
                               + legal[index].second * legal_param_;
    }
}

double
GlobalPlacer::find_beta(const ::vector<::pair<double, double>> &grad_f,
                        const ::vector<::pair<double, double>> &last_grad_f) {
    // Polak-Ribiere formula from APlace journal paper
    // NOTE:
    //   g_{k-1} = -last_grad_f
    //   g_k     = grad_f
    // Keyi: adapted from NTU place
    double l2norm = 0;
    for (auto &i : last_grad_f) {
        l2norm += i.first * i.first;
        l2norm += i.second * i.second;
    }
    double product = 0;
    for (uint32_t i = 0; i < grad_f.size(); i++ ) {
        // g_k^T ( g_k - g_{k-1}
        product += grad_f[i].first *
                   (grad_f[i].first + last_grad_f[i].first);
        product += grad_f[i].second *
                   (grad_f[i].second + last_grad_f[i].second);
    }
    return product / l2norm;
}

double
GlobalPlacer::line_search(const ::vector<::pair<double, double>> &grad_f,
                          const uint32_t &current_step) {
    // Keyi:
    // adapted from ntuplace
    uint64_t size = grad_f.size();
    double total_grad = 0;
    for (uint32_t i=0; i < size; i++) {
        total_grad += grad_f[i].first * grad_f[i].first;
        total_grad += grad_f[i].second * grad_f[i].second;
    }
    double avg_grad = std::sqrt(total_grad / size);
    return  1.0 / avg_grad * current_step;
}