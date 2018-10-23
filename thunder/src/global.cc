#include <string>
#include <cmath>
#include <limits>
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
                           hidden_columns() {
    // first compute the reduced board_layout
    setup_reduced_layout();
    create_fixed_boxes();
    // set up the boxes
    create_boxes();

    // setup reduced netlist
    auto [nets, intra_count] = this->collapse_netlist(::move(netlists));
    netlists_ = nets;

    /*
    for (auto const &iter : intra_count)
        printf("%s %d\n", iter.first.c_str(), iter.second);
    */

    // random setup
    global_rand_.seed(0);

    // init placement
    init_place();

    // set annealing parameters
    this->tmax = tmin * 2;
    this->steps = (int)(clusters_.size() * clusters_.size() * 100);
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
    /*
    for (auto const &y : reduced_board_layout_) {
        if (y.size() != reduced_board_layout_[margin].size())
            throw std::runtime_error("failed layout check at " +
                                     std::to_string(y.size()));
        else
            for (const auto &t : y)
                printf("%c", t);
        printf("\n");
    }
    */

    // set helper values
    reduced_height_ = (uint32_t)reduced_board_layout_.size();
    reduced_width_ = (uint32_t)reduced_board_layout_[0].size();
}

void GlobalPlacer::create_fixed_boxes() {
    for (const auto &iter : fixed_pos_) {
        ClusterBox box {
            (double)iter.second.first, // xmin
            (double)iter.second.first, // xmax
            (double)iter.second.second, // ymin
            (double)iter.second.second, // ymax
            (double)iter.second.first,  // cx
            (double)iter.second.second, // cy
            iter.first,                 // id
            0,                          // clb_size
            1,                          // width
            (int)boxes_.size(),      // index
            true                     //fixed
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
        ClusterBox box;
        box.id = cluster_id;
        box.index = box_index;
        box.clb_size = 0;
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
        // calculate the width
        box.width = (uint32_t)std::ceil(std::sqrt(box.clb_size));
        boxes_.emplace_back(box);

        // calculate the legal cost function
        ::map<char, tk::spline> splines;
        for (auto const &iter_dsp : dsp_blocks) {
            auto height = box.width;
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

void GlobalPlacer::solve() {
    uint32_t max_iter = 50;
    const double precision = 0.99;
    double obj_value = 0;
    double old_obj_value = 0;

    for (uint32_t iter = 0; iter < max_iter; iter++) {
        obj_value = eval_f();
        printf("HPWL: %f\n", obj_value);
        if (iter > 0 && obj_value >= precision * old_obj_value)
            break;
        uint32_t inner_iter = 0;
        ::vector<::pair<double, double>> last_grad_f;
        double best_hpwl = INT_MAX;
        while (true) {
            if (inner_iter == 0) {
                old_obj_value = std::numeric_limits<double>::max();
            }
            obj_value = eval_f();
            if (obj_value >= precision * old_obj_value) {
                break;
            }

            // compute the gradient
            ::vector<::pair<double, double>> grad_f;
            eval_grad_f(grad_f, iter);
            // adjust force
            adjust_force(grad_f);

            ::vector<::pair<double, double>> direction;
            direction.resize(grad_f.size());
            const ::pair<double, double> zero = {0, 0};
            std::fill(direction.begin(), direction.end(), zero);


            if (inner_iter == 0) {
                for(uint32_t i = 0; i < grad_f.size(); i++) {
                    direction[i].first = -grad_f[i].first;
                    direction[i].second = -grad_f[i].second;
                }
            } else {
                double beta = find_beta(grad_f, last_grad_f);
                for (uint32_t i = 0; i < grad_f.size(); i++) {
                    direction[i].first = - grad_f[i].first +
                                      beta * last_grad_f[i].first;
                    direction[i].second = - grad_f[i].second +
                                       beta * last_grad_f[i].second;
                }
            }

            // calculate a_k (step size)
            double step_size = line_search(grad_f);

            // compute move for every box
            for (uint32_t i = 0; i < boxes_.size(); i++) {
                auto &box = boxes_[i];
                if (box.fixed)
                    continue;
                box.cx += direction[i].first * step_size;
                box.cy += direction[i].second * step_size;

                // set bound
                // and a look-ahead legalization
                double xmin = box.cx - box.width / 2.0;
                double ymin = box.cy - box.width / 2.0;
                // bound them up
                xmin = std::max<double>(xmin, 0);
                xmin = std::min<double>(xmin, reduced_width_ - box.width);
                ymin = std::max<double>(ymin, 0);
                ymin = std::min<double>(ymin, reduced_height_ - box.width);
                box.cx = xmin + box.width / 2.0;
                box.cy = ymin + box.width / 2.0;
                box.xmin = xmin;
                box.ymin = ymin;
            }

            // compute the hpwl only once a while
            if (inner_iter % 4 == 0) {
                double hpwl = compute_hpwl();
                if (hpwl > best_hpwl)
                    break;
                best_hpwl = hpwl;
            }

            // copy over the grad_f
            last_grad_f.assign(grad_f.begin(), grad_f.end());
            old_obj_value = obj_value;
            inner_iter++;
        }
    }

    // legalize them into integers
    for (auto &box : boxes_) {
        if (box.fixed)
            continue;
        box.xmin = std::min<double>(std::round(box.xmin),
                                    reduced_width_ - box.width);
        box.xmin = std::max<double>(0, box.xmin);
        box.ymin = std::min<double>(std::round(box.ymin),
                                    reduced_height_ - box.width);
        box.ymin = std::max<double>(0, box.ymin);
        box.xmax = box.xmin + box.width;
        box.ymax = box.ymin + box.width;
        box.cx = box.xmin + box.width / 2.0;
        box.cy = box.ymax + box.width / 2.0;
    }

    this->curr_energy = eval_f(anneal_param_);
}

double GlobalPlacer::eval_f(double overlap_param) {
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
    for (const auto &box1 : boxes_) {
        if (box1.fixed)
            continue;
        double x1 = box1.cx;
        double y1 = box1.cy;

        for (const auto &box2 : boxes_) {
            if (box2.fixed || box1.index == box2.index)
                continue;
            // compute the distance
            double x2 = box2.cx;
            double y2 = box2.cy;
            double d_2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
            double width_2 = (box1.width + box2.width)
                             * (box1.width + box2.width);
            if (d_2 >= width_2) {
                continue;
            } else {
                overlap += (d_2 - width_2) * (d_2 - width_2);
            }
        }
    }

    // third part is the legalization
    double legal = 0;
    for (const auto &box : boxes_) {
        if (box.fixed)
            continue;
        // spline is calculated based on the xmin
        double x = box.xmin;
        for (const auto &iter : legal_spline_[box.index]) {
            // TODO: add different legal energy here
            legal += iter.second(x);
        }
    }

    return hpwl * hpwl_param_ + overlap * potential_param_ * overlap_param +
           legal * legal_param_;
}

void  GlobalPlacer::eval_grad_f(::vector<::pair<double, double>> &grad_f,
                                const uint32_t current_step) {
    // first part is HWPL
    ::vector<::pair<double, double>> hpwl;
    ::vector<::pair<double, double>> overlap;
    ::vector<::pair<double, double>> legal;

    grad_f.resize(boxes_.size());
    hpwl.resize(boxes_.size());
    overlap.resize(boxes_.size());
    legal.resize(boxes_.size());

    // set to zero
    const auto zero = std::make_pair(0, 0);
    std::fill(grad_f.begin(), grad_f.end(), zero);
    std::fill(hpwl.begin(), hpwl.end(), zero);
    std::fill(overlap.begin(), overlap.end(), zero);
    std::fill(legal.begin(), legal.end(), zero);

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
            hpwl[index].first -= 2.0 / (N * N) * ((N * N - 2 * N + 2) * x -
                                 2 * (N - 1) * (x_sum - x));
            hpwl[index].second -= 2.0 / (N * N) * ((N * N - 2 * N + 2) * y -
                                  2 * (N - 1) * (y_sum - y));
        }
    }
    // second part is the spreading potential
    for (const auto &box1 : boxes_) {
        if (box1.fixed)
            continue;
        double x1 = box1.cx;
        double y1 = box1.cy;

        for (const auto &box2 : boxes_) {
            if (box2.fixed || box1.index == box2.index)
                continue;
            // compute the distance
            double x2 = box2.cx;
            double y2 = box2.cy;
            double d_2 = (x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1);
            double width_2 = (box1.width + box2.width)
                             * (box1.width + box2.width);
            if (d_2 >= width_2) {
                continue;
            } else if (d_2 == 0) {
                throw std::runtime_error("not implemented");
            } else {
                // compute the gradient
                double value = std::abs(2 * (d_2 - width_2));
                double norm = std::sqrt(d_2);
                overlap[box1.index].first -= (x1 - x2) / norm * value;
                overlap[box1.index].second -= (y1 - y2) / norm * value;
            }
        }
    }

    // third part is the legalization
    for (const auto &box : boxes_) {
        if (box.fixed)
            continue;
        // spline is calculated based on the xmin
        double x = box.xmin;
        for (const auto &iter : legal_spline_[box.index]) {
            // TODO: add different legal energy here
            legal[box.index].first -= iter.second.deriv(1, x);
        }
    }

    for (const auto &box : boxes_) {
        auto index = box.index;
        grad_f[index].first = hpwl[index].first * hpwl_param_
                              + overlap[index].first * potential_param_
                                * (current_step)
                              + legal[index].first * legal_param_;
        grad_f[index].second = hpwl[index].second * hpwl_param_
                               + overlap[index].second * potential_param_
                                * (current_step)
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
                   (grad_f[i].first - last_grad_f[i].first);
        product += grad_f[i].second *
                   (grad_f[i].second - last_grad_f[i].second);
    }
    return product / l2norm;
}

double
GlobalPlacer::line_search(const ::vector<::pair<double, double>> &grad_f) {
    const double step = 1;
    // Keyi:
    // adapted from ntuplace
    uint64_t size = grad_f.size();
    double total_grad = 0;
    for (uint32_t i=0; i < size; i++) {
        total_grad += grad_f[i].first * grad_f[i].first;
        total_grad += grad_f[i].second * grad_f[i].second;
    }
    double avg_grad = std::sqrt(total_grad / size);
    return  1.0 / avg_grad * step;
}

void
GlobalPlacer::adjust_force(::vector<::pair<double, double>> &grad_f) {
    double norm_2 = 0;
    for (auto const &vec : grad_f) {
        norm_2 += vec.first * vec.first;
        norm_2 += vec.second * vec.second;
    }
    double average = norm_2 / grad_f.size();
    // truncate to the average
    for (auto &vec : grad_f) {
        double norm = vec.first * vec.first + vec.second * vec.second;
        if (norm > average) {
            vec.first = vec.first * average / norm;
            vec.second = vec.second * average / norm;
        }
    }
}

void GlobalPlacer::init_place() {
    double center_x = (reduced_width_ - 1) / 2.0;
    double center_y = (reduced_height_ - 1) / 2.0;
    for (auto &box : boxes_) {
        if (box.fixed)
            continue;
        box.cx = center_x + global_rand_.uniform<double>(-1, 1);
        box.cy = center_y + global_rand_.uniform<double>(-1, 1);
        box.xmin = box.cx - (box.width) / 2.0;
        box.xmax = box.cx + (box.width) / 2.0;
        box.ymin = box.cy - (box.width) / 2.0;
        box.ymax = box.cy + (box.width) / 2.0;
    }
}

double GlobalPlacer::compute_hpwl() const {
    double hpwl = 0;
    for (const auto &net : netlists_) {
        double xmin = INT_MAX;
        double xmax = 0;
        double ymin = INT_MAX;
        double ymax = 0;
        for (const auto &box_index : net) {
            auto const &box = boxes_[box_index];
            if (box.cx > xmax)
                xmax = box.cx;
            if (box.cx < xmin)
                xmin = box.cx;
            if (box.cy > ymax)
                ymax = box.cy;
            if (box.cy < ymin)
                ymin = box.cy;
        }
        hpwl += xmax - xmin + ymax - ymin;
    }
    return hpwl;
}

::map<int, ::map<char, ::vector<::pair<int, int>>>>
GlobalPlacer::realize() {
    // several problem to solve
    // 1. reverse the mapping
    // 2. assign cells

    ::map<int, ::map<char, ::vector<::pair<int, int>>>> result;

    return result;
}

void GlobalPlacer::move() {
    auto box_index = global_rand_.uniform<uint64_t>(fixed_pos_.size(),
                                                        boxes_.size() - 1);

    int dx = global_rand_.uniform<int>(-2, 2);
    int dy = global_rand_.uniform<int>(-2, 2);

    double xmin = boxes_[box_index].xmin + dx;
    double ymin = boxes_[box_index].ymin + dy;
    xmin = std::min<double>(xmin,
                            reduced_width_ - boxes_[box_index].width);
    xmin = std::max<double>(0, xmin);
    ymin = std::min<double>(ymin,
                            reduced_height_ - boxes_[box_index].width);
    ymin = std::max<double>(0, ymin);

    dx = (int)(xmin - boxes_[box_index].xmin);
    dy = (int)(ymin - boxes_[box_index].ymin);

    if (dx == 0 and dy == 0) {
        // assume we always have at least a fixed box
        current_move_.box_index = 0;
    } else {
        current_move_.box_index = box_index;
        current_move_.dx = dx;
        current_move_.dy = dy;
    }
}

double GlobalPlacer::energy() {
    if (current_move_.box_index == 0)
        return curr_energy;
    auto &box = boxes_[current_move_.box_index];
    int dx = current_move_.dx;
    int dy = current_move_.dy;

    // make the change
    box.xmin += dx;
    box.ymax += dx;
    box.cx += dx;
    box.ymin += dy;
    box.ymax += dy;
    box.cy += dy;

    double new_energy = eval_f(anneal_param_);

    // revert back
    box.xmin -= dx;
    box.ymax -= dx;
    box.cx -= dx;
    box.ymin -= dy;
    box.ymax -= dy;
    box.cy -= dy;


    return new_energy;
}

void GlobalPlacer::commit_changes() {
    if (current_move_.box_index == 0)
        return;

    auto &box = boxes_[current_move_.box_index];
    int dx = current_move_.dx;
    int dy = current_move_.dy;

    // make the change
    box.xmin += dx;
    box.ymax += dx;
    box.cx += dx;
    box.ymin += dy;
    box.ymax += dy;
    box.cy += dy;

    current_move_.box_index = 0;
}

void GlobalPlacer::anneal() {
    double old_energy = curr_energy;
    printf("Before annealing energy: %f\n", old_energy);
    SimAnneal::anneal();
    printf("After annealing energy: %f improvement: %f\n",
            curr_energy, (old_energy - curr_energy) / old_energy);
}