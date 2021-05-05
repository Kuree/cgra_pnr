#include <sstream>
#include "../src/io.hh"
#include "../src/graph.hh"
#include "../src/global.hh"
#include "../src/layout.hh"
#include "../src/util.hh"
#include "../src/multi_place.hh"
#include "../src/detailed.hh"

constexpr uint32_t dim_threshold = 6;

using std::string;
using std::map;
using std::vector;
using std::pair;
constexpr uint32_t seed = 0;
constexpr uint32_t partition_threshold = 10;
constexpr double partial_reconfigure_ratio = 0.5;

std::map<std::string, std::vector<std::string>>
convert_netlist(const std::map<::string,
        std::vector<std::pair<::string,
                ::string>>> &netlist) {
    std::map<std::string, std::vector<std::string>> result;
    for (auto &[net_id, net]: netlist) {
        std::vector<::string> blks(net.size());
        for (uint32_t i = 0; i < net.size(); i++) {
            blks[i] = net[i].first;
        }
        result.insert({net_id, blks});
    }
    return result;
}

std::map<std::string, std::pair<int, int>>
prefixed_placement(const std::map<std::string,
        std::vector<std::string>> &netlist,
                   const Layout &layout,
                   const std::pair<bool, ::string> &fix_loc) {
    auto const &[use_prefix, placement_filename] = fix_loc;
    std::map<std::string, std::pair<int, int>> result;
    if (use_prefix) {
        result = load_placement(placement_filename);
    }
    // place IO on CGRA
    // UPDATE: I'm not sure if CoreIR has fixed the bug where enable has high
    // priority over enable.
    auto cmp = [](const ::string &a, const ::string &b) -> bool {
        int value_a = std::stoi(a.substr(1));
        int value_b = std::stoi(b.substr(1));
        return value_a < value_b;
    };
    std::set<std::string, decltype(cmp)> working_set(cmp);
    for (const auto &iter: netlist) {
        for (auto const &blk : iter.second) {
            if ((blk[0] == 'i' || blk[0] == 'I')
                && result.find(blk) == result.end())
                working_set.insert(blk);
        }
    }

    // 1 bit first. there is another bug in the hardware that the reset signal
    // has to be placed first
    std::vector<std::string> blocks(working_set.begin(), working_set.end());
    // sort the blocks based on the tag
    std::partition(blocks.begin(), blocks.end(), [](const std::string &a) {
        return a[0] == 'i';
    });

    const auto &io_layout = layout.get_layer('I');
    const auto available_pos = io_layout.produce_available_pos();
    if (available_pos.size() < working_set.size())
        throw std::runtime_error("unable to assign all IO tiles");
    uint32_t pos_index = 0;
    for (auto const &blk_id : blocks) {
        auto const &pos = available_pos[pos_index++];
        result[blk_id] = pos;
    }
    return result;
}

void
threshold_partition_netlist(const std::map<std::string,
        std::vector<std::string>> &netlist,
                            std::map<int, std::set<std::string>> &raw_clusters) {

    // if we only have a few blks, don't bother doing a partition
    // get the clusters
    // count the number of blocks
    std::set<std::string> blks;
    for (auto const &iter : netlist) {
        for (auto const &blk : iter.second) {
            blks.insert(blk);
        }
    }
    if (blks.size() > partition_threshold) {
        raw_clusters = partition_netlist(netlist);
    } else {
        // just use the set
        raw_clusters.insert({0, blks});
    }
}

void
check_placement(const ::map<::string,
        ::vector<::pair<::string, ::string>>> &raw_netlist,
                const ::map<std::string, std::pair<int, int>> &placement,
                const Layout &layout) {
    // making sure the placement is correct
    // first making sure we have every block placed
    for (auto const &iter: raw_netlist) {
        for (auto const &blk_pair : iter.second) {
            if (placement.find(blk_pair.first) == placement.end())
                throw std::runtime_error("unable to find blk " +
                                         blk_pair.first);
        }
    }
    // making sure the positions are correct
    auto available_pos = layout.produce_available_pos();
    ::map<char, std::set<::pair<int, int>>> pos_set;
    for (auto const &[blk_type, pos_list] : available_pos) {
        pos_set[blk_type] = std::set<::pair<int, int>>(pos_list.begin(),
                                                       pos_list.end());
    }
    for (auto const &[blk_id, pos] : placement) {
        char blk_type = blk_id[0];
        // hack here
        // FIXME: NEED TO REMOVE THIS HACK, WHICH IS CAUSED BY A MANTLE BUG
        if (blk_type == 'i' || blk_type == 'I')
            continue;
        auto const[x, y] = pos;
        auto &blk_pos = pos_set.at(blk_type);
        if (blk_pos.find(pos) == blk_pos.end())
            throw std::runtime_error("over use position " + std::to_string(x)
                                     + " " + std::to_string(y));
        blk_pos.erase(pos);
    }
}

void print_help_message(char *argv[]) {
    std::cerr << "Usage: " << argv[0] << " [-h] [-f] <cgra.layout> "
              << "<netlist.packed> <result.place>" << std::endl;
}

// parse the command line options
std::tuple<::string, ::string, ::string, bool>
parse_cli_args(int argc, char *argv[]) {
    bool use_prefix = false;
    std::vector<::string> args;
    for (int i = 1; i < argc; i++) {
        if (::string(argv[i]).empty())
            continue;
        if (argv[i][0] != '-') {
            args.emplace_back(argv[i]);
        } else if (argv[i][1] == 'h') {
            return std::make_tuple("", "", "", false);
        } else if (argv[i][1] == 'f') {
            use_prefix = true;
        }
    }
    if (args.size() != 3)
        return std::make_tuple("", "", "", false);
    else
        return std::make_tuple(args[0], args[1], args[2], use_prefix);
}

bool early_termination(const std::map<::string, std::pair<int, int>> &prefix,
                       const std::map<int, std::set<::string>> &raw_c) {
    uint32_t count = 0;
    uint32_t prefix_size = 0;
    for (const auto &iter: raw_c) {
        count += iter.second.size();

        // compute the actual prefix size
        for (const auto &it_: prefix) {
            if (iter.second.find(it_.first) != iter.second.end())
                prefix_size++;
        }
    }
    return count <= prefix_size;
}

uint32_t blk_count(const std::map<int, std::set<std::string>> &clusters) {
    std::unordered_set<::string> blks;
    for (auto const &it: clusters) {
        for (auto const &blk : it.second)
            blks.emplace(blk);
    }
    return blks.size();
}

bool disable_global_placement() {
    return (std::getenv("DISABLE_GP") != nullptr) || (std::getenv("SKIP_GP") != nullptr);  // NOLINT
}

int main(int argc, char *argv[]) {
    auto const[layout_file, netlist_file, result_filename, use_prefix] =
    parse_cli_args(argc, argv);
    if (layout_file.empty() || netlist_file.empty()
        || result_filename.empty()) {
        print_help_message(argv);
        return EXIT_FAILURE;
    }
    auto layout = load_layout(layout_file);
    auto raw_netlist = load_netlist(netlist_file).first;
    auto id_to_name = load_id_to_name(netlist_file);

    // remove unnecessary information
    auto netlist = convert_netlist(raw_netlist);
    std::map<int, std::set<std::string>> raw_clusters;
    threshold_partition_netlist(netlist, raw_clusters);

    // get fixed pos
    const auto fixed_pos = prefixed_placement(netlist,
                                              layout, {use_prefix,
                                                       result_filename});
    const double total_blk_count = blk_count(raw_clusters);
    const double fixed_ratio = fixed_pos.size() / total_blk_count;

    // decide if we ned to terminate early
    // in most case it's an error
    if (early_termination(fixed_pos, raw_clusters)) {
        std::cerr << "Nothing to be done" << std::endl;
        return EXIT_SUCCESS;
    }

    auto clusters = convert_clusters(raw_clusters, fixed_pos);
    // notice that if there is only one cluster and the board is very small
    // we just do it flat
    ::map<::string, ::map<char, std::set<::pair<int, int>>>> gp_result;
    const auto &size = layout.get_size();
    if ((clusters.size() == 1)
        || (size.first <= dim_threshold && size.second <= dim_threshold)
        || (fixed_ratio >= partial_reconfigure_ratio) || disable_global_placement()) {
        // merge into one-single cluster, if more than one
        std::map<std::string, std::set<std::string>> new_cluster;
        for (auto const &it: clusters) {
            new_cluster["x0"].insert(it.second.begin(), it.second.end());
        }
        auto const &pos_collections = layout.produce_available_pos();
        gp_result["x0"] = {};
        for (auto const &[blk_type, pos]: pos_collections) {
            gp_result["x0"][blk_type] =
                    std::set<::pair<int, int>>(pos.begin(), pos.end());
        }
        clusters = new_cluster;

    } else {
        // global placement
        auto gp = GlobalPlacer(clusters, netlist, fixed_pos, layout);
        gp.set_seed(seed);
        // compute the anneal param based on some heuristics
        uint64_t num_blks_layout = layout.get_layer(layout.get_clb_type()).
                produce_available_pos().size();
        double num_blks = 0;
        const char clb_type = layout.get_clb_type();
        for (auto const &iter: clusters) {
            for (const auto &blk: iter.second) {
                if (blk[0] == clb_type)
                    num_blks += 1;
            }
        }
        double fill_ratio = fmax(0.99, num_blks / num_blks_layout);
        double base_factor = 1;
        if (fill_ratio > 0.8)
            base_factor = 1.2;
        gp.anneal_param_factor = base_factor / (1 - fill_ratio);
        std::cout << "Use anneal_param_factor " << gp.anneal_param_factor
                  << std::endl;
        gp.solve();
        gp.anneal();

        gp_result = gp.realize();
    }

    map<string, pair<int, int>> dp_result = detailed_placement(clusters,
                                                               netlist,
                                                               fixed_pos,
                                                               gp_result,
                                                               layout);

    // global refinement
    auto global_refine = DetailedPlacer(dp_result,
                                        netlist,
                                        layout.produce_available_pos(),
                                        fixed_pos,
                                        layout.get_clb_type(),
                                        true);
    // compute the refine parameters
    auto it = static_cast<uint32_t>(100 * pow(dp_result.size(), 1.33));
    global_refine.refine(it, 0.001, true);
    auto result = global_refine.realize();

    // check the placement
    check_placement(raw_netlist, result, layout);

    // save the result
    save_placement(result, id_to_name, result_filename);

    return EXIT_SUCCESS;
}
