#include "../src/io.hh"
#include "../src/graph.hh"
#include "../src/global.hh"
#include "../src/layout.hh"
#include "../src/util.hh"
#include "../src/multi_place.hh"
#include "../src/detailed.hh"

using std::string;
constexpr uint32_t seed = 0;
constexpr uint32_t partition_threshold = 10;

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
                   const Layout &layout) {
    // place IO on CGRA
    // we are not doing masks now and current CGRA has some bug with
    // using two 1bit tiles. assigning all of them to the 16-bit for now
    std::set<std::string> working_set;
    for (const auto &iter: netlist) {
        for (auto const &blk : iter.second) {
            if (blk[0] == 'i' || blk[0] == 'I')
                working_set.insert(blk);
        }
    }

    const auto &io_layout = layout.get_layer('I');
    const auto available_pos = io_layout.produce_available_pos();
    if (available_pos.size() < working_set.size())
        throw std::runtime_error("unable to assign all IO tiles");
    uint32_t pos_index = 0;
    std::map<std::string, std::pair<int, int>> result;
    for (auto const &blk_id : working_set) {
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

int main(int argc, char *argv[]) {
    if (argc != 4) {
        std::cerr << "Usage: " << argv[0] << " <cgra.layout> "
                  << "<netlist.packed> <result.place>" << std::endl;
        return EXIT_FAILURE;
    }
    auto layout = load_layout(argv[1]);
    auto raw_netlist = load_netlist(argv[2]).first;
    auto id_to_name = load_id_to_name(argv[2]);
    std::string result_filename = argv[3];

    // all available pos
    auto available_pos = layout.produce_available_pos();

    // remove unnecessary information
    auto netlist = convert_netlist(raw_netlist);
    std::map<int, std::set<std::string>> raw_clusters;
    threshold_partition_netlist(netlist, raw_clusters);

    // get fixed pos
    const auto fixed_pos = prefixed_placement(netlist, layout);

    auto clusters = convert_clusters(raw_clusters, fixed_pos);
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
    double fill_ratio = fmax(0.99, num_blks /num_blks_layout);
    gp.anneal_param_factor = 1 / (1 - fill_ratio);
    std::cout << "Use anneal_param_factor " << gp.anneal_param_factor
              << std::endl;
    gp.solve();
    gp.anneal();

    auto gp_result = gp.realize();
    auto centroids = compute_centroids(gp_result, layout.get_clb_type());
    // substitutes the clusters
    auto cluster_fixed_pos = get_cluster_fixed_pos(fixed_pos,
                                                   centroids);
    std::map<std::string, std::map<std::string,
             std::vector<std::string>>> multi_netlists;
    // need to replicate the fix pos as well
    std::map<std::string, std::map<std::string,
             std::pair<int, int>>> multi_fixed_pos;
    for (const auto &iter : clusters) {
        auto cluster_netlist = reduce_cluster_graph(netlist,
                                                    clusters,
                                                    cluster_fixed_pos,
                                                    iter.first);
        multi_netlists[iter.first] = cluster_netlist;
        multi_fixed_pos[iter.first] = cluster_fixed_pos;
    }
    // multi-core placement
    auto dp_result = multi_place(clusters, gp_result, multi_netlists,
                                 multi_fixed_pos, layout.get_clb_type(), true);

    // global refinement
    auto global_refine = DetailedPlacer(dp_result,
                                        netlist,
                                        available_pos,
                                        fixed_pos,
                                        layout.get_clb_type(),
                                        true);
    // compute the refine parameters
    auto it = static_cast<uint32_t>(100 * pow(dp_result.size(), 1.33));
    global_refine.refine(it, 0.001, true);
    auto result = global_refine.realize();

    // save the result
    save_placement(result, id_to_name, result_filename);

    return EXIT_SUCCESS;
}