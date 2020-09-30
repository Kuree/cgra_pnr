#ifndef THUNDER_EXAMPLE_UTIL_HH
#define THUNDER_EXAMPLE_UTIL_HH

#include <map>
#include <vector>
#include "../src/graph.hh"

constexpr uint32_t partition_threshold = 10;

inline std::map<std::string, std::vector<std::string>>
convert_netlist(const std::map<std::string, std::vector<std::pair<std::string, std::string>>> &netlist) {
    std::map<std::string, std::vector<std::string>> result;
    for (auto &[net_id, net]: netlist) {
        std::vector<std::string> blks(net.size());
        for (uint32_t i = 0; i < net.size(); i++) {
            blks[i] = net[i].first;
        }
        result.insert({net_id, blks});
    }
    return result;
}

inline void
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

#endif //THUNDER_EXAMPLE_UTIL_HH
