#include <iostream>
#include <map>
#include "../src/io.hh"
#include "util.hh"
#include <unordered_map>
#include <unordered_set>

using Netlist = std::map<std::string,
        std::vector<std::pair<std::string, std::string>>>;
using Port = std::pair<std::string, std::string>;
using BusMode = std::map<std::string, uint32_t>;
using IOPortName = std::unordered_map<uint32_t, std::pair<std::string, std::string>>;

std::unordered_map<std::string, std::unordered_set<std::string>>
get_blk_to_sink_net(const Netlist &netlist) {
    std::unordered_map<std::string, std::unordered_set<std::string>> result;
    for (auto const &[net_id, net]: netlist) {
        auto blk_id = net[0].first;
        result[blk_id].emplace(net_id);
    }
    return result;
}

std::unordered_map<std::string, std::unordered_set<std::string>>
get_blk_to_src_net(const Netlist &netlist) {
    std::unordered_map<std::string, std::unordered_set<std::string>> result;
    for (auto const &[net_id, net]: netlist) {
        for (uint64_t i = 1; i < net.size(); i++) {
            auto const &blk_id = net[i].first;
            result[blk_id].emplace(net_id);
        }

    }
    return result;
}

std::pair<std::set<Port>, std::set<Port>>
compute_cut_edge(const std::set<std::string> &cluster, const Netlist &netlist) {
    std::set<Port> inputs, outputs;
    auto blk_to_sink_net = get_blk_to_sink_net(netlist);
    auto blk_to_src_net = get_blk_to_src_net(netlist);

    for (auto const &blk: cluster) {
        if (blk_to_sink_net.find(blk) != blk_to_sink_net.end()) {
            auto nets = blk_to_sink_net.at(blk);
            for (auto const &net_id: nets) {
                auto const &net = netlist.at(net_id);
                for (uint32_t i = 1; i < net.size(); i++) {
                    auto sink = net[i].first;
                    // check if it's in the cluster or not
                    if (cluster.find(sink) == cluster.end()) {
                        // we have an output edge
                        outputs.emplace(net[0]);
                    }
                }
            }
        }
        if (blk_to_src_net.find(blk) != blk_to_sink_net.end()) {
            auto nets = blk_to_src_net.at(blk);
            for (auto const &net_id: nets) {
                auto const &net = netlist.at(net_id);
                auto const &src = net[0];
                if (cluster.find(src.first) == cluster.end()) {
                    // we have an input edge
                    inputs.emplace(net[0]);
                }
            }
        }

    }

    return std::make_pair(inputs, outputs);
}

IOPortName get_io_port_name(const Netlist &netlist, const BusMode &bus) {
    static const std::string input_prefix = "io2f_";
    static const std::string output_prefix = "f2io_";
    IOPortName result;

    for (auto const &iter: bus) {
        auto width = iter.second;
        if (result.find(width) == result.end()) {
            // add default values in case we can't find it from the netlist
            result.emplace(width, std::make_pair(input_prefix + std::to_string(width),
                                                 output_prefix + std::to_string(width)));
        }
    }

    for (auto const &[net_id, net]: netlist) {
        auto width = bus.at(net_id);
        auto const &[src_name, src_port] = net[0];
        if (src_name[0] == 'I' || src_name[0] == 'i') {
            // this is input
            result[width].first = src_port;
        }
        for (uint32_t i = 1; i < net.size(); i++) {
            auto const &[dst_name, dst_port] = net[i];
            if (dst_name[0] == 'I' || dst_name[0] == 'i') {
                // this is output
                result[width].second = dst_port;
            }
        }
    }

    return result;
}

bool is_connected(const Port &src, const Port &sink, const Netlist &netlist) {
    for (auto const &iter: netlist) {
        auto const &net = iter.second;
        if (net[0] == src) {
            for (uint64_t i = 1; i < net.size(); i++) {
                if (net[i] == sink)
                    return true;
            }
        }
    }


    return false;
}

int main(int argc, char *argv[]) {
    if (argc != 3) {
        std::cerr << "Usage " << argv[0] << "raw_netlist.packed output_dir"
                  << std::endl;
        return EXIT_FAILURE;
    }
    std::string filename = argv[1];
    std::string dirname = argv[2];

    auto[netlist, bus_mode] = load_netlist(filename);
    auto id_to_name = load_id_to_name(filename);

    // remove unnecessary information
    auto simplified_netlist = convert_netlist(netlist);
    std::map<int, std::set<std::string>> raw_clusters;
    threshold_partition_netlist(simplified_netlist, raw_clusters);

    // get some meta info
    IOPortName io_names = get_io_port_name(netlist, bus_mode);

    // write out the netlist
    // given the partition result, we need to produce the new netlist
    std::map<uint32_t, std::pair<std::set<Port>, std::set<Port>>> extra_ports;
    for (auto const &[cluster_id, cluster]: raw_clusters) {
        auto ports = compute_cut_edge(cluster, netlist);
        extra_ports[cluster_id] = ports;
    }

    // compute the connectivity
    //

}