#include "../src/io.hh"
#include "../src/graph.hh"
#include "../src/global.hh"
#include "../src/layout.hh"
#include "../src/util.hh"

using std::string;
constexpr uint32_t seed = 0;

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

int main(int argc, char *argv[]) {
    if (argc != 3) {
        std::cerr << "Usage: " << argv[0] << " <cgra.layout> "
                  << "<netlist.packed" << std::endl;
        return EXIT_FAILURE;
    }
    auto layout = load_layout(argv[1]);
    auto raw_netlist = load_netlist(argv[2]).first;

    // remove unnecessary information
    auto netlist = convert_netlist(raw_netlist);

    // get the clusters
    const auto raw_clusters = partition_netlist(netlist);
    // get fixed pos
    const auto fixed_pos = prefixed_placement(netlist, layout);

    auto clusters = convert_clusters(raw_clusters, fixed_pos);
    // global placement
    auto gp = GlobalPlacer(clusters, netlist, fixed_pos, layout);
    gp.set_seed(seed);
    gp.anneal_param_factor = clusters.size();
    gp.solve();
    gp.anneal();

    auto gp_result = gp.realize();
    auto centroids = compute_centroids(gp_result, layout.get_clb_type());
    // substitutes the clusters

    (void)centroids;
    return EXIT_SUCCESS;
}