#include <iostream>
#include <map>
#include "../src/io.hh"
#include "util.hh"
#include <unordered_map>
#include <unordered_set>

using NetID = std::string;
using BlockID = std::string;
using PortName = std::string;
using Port = std::pair<BlockID, PortName>;
using BusMode = std::map<NetID, uint32_t>;
using IOPortName = std::unordered_map<uint32_t, Port>;
using Netlist = std::map<NetID, std::vector<Port>>;


std::unordered_map<BlockID, std::unordered_set<NetID>>
get_blk_to_sink_net(const Netlist &netlist) {
    std::unordered_map<BlockID, std::unordered_set<NetID>> result;
    for (auto const &[net_id, net]: netlist) {
        auto blk_id = net[0].first;
        result[blk_id].emplace(net_id);
    }
    return result;
}

std::unordered_map<BlockID, std::unordered_set<NetID>>
get_blk_to_src_net(const Netlist &netlist) {
    std::unordered_map<BlockID, std::unordered_set<NetID>> result;
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
                    for (uint64_t i = 1; i < net.size(); i++) {
                        if (net[i].first == blk)
                            inputs.emplace(net[i]);
                    }
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

bool is_connected(const Port &a, const Port &b, const Netlist &netlist) {
    for (auto const &iter: netlist) {
        auto const &net = iter.second;
        auto has_a = false;
        auto has_b = false;
        for (auto const &blk: net) {
            if (blk == a) has_a = true;
            else if (blk == b) has_b = true;
        }
        if (has_a && has_b) return true;
    }
    return false;
}

bool is_driving(const BlockID &src, const BlockID &sink, const Netlist &netlist) {
    // doesn't seem to be efficient
    // in the future need to refactor it to a proper hypergraph data structure
    for (auto const &iter: netlist) {
        auto const &net = iter.second;
        if (net[0].first == src) {
            for (uint64_t i = 1; i < net.size(); i ++) {
                auto const &sink_ = net[i];
                if (sink_.first == sink) return true;
            }
        }
    }
    return false;
}

Netlist create_cluster_netlist(const Netlist &netlist,
                               const std::set<BlockID> &blks) {
    Netlist result;
    for (auto const &[net_id, net]: netlist) {
        for (auto const &port: net) {
            if (blks.find(port.first) != blks.end()) {
                result.emplace(net_id, net);
                break;
            }
        }
    }

    return result;
}

void fix_netlist(Netlist &netlist, const std::set<std::string> &blks,
                 const std::map<Port, std::string> &io_mapping,
                 const IOPortName &io_names,
                 const std::map<Port, uint32_t> &port_width) {
    for (auto &[net_id, net]: netlist) {
        auto const &src = net[0];
        if (blks.find(src.first) != blks.end()) {
            // the source is internal
            bool modified = false;
            for (uint32_t i = 1; i < net.size(); i++) {
                auto const &sink = net[i];
                if (blks.find(sink.first) == blks.end()) {
                    // this is an external sink
                    if (io_mapping.find(sink) == io_mapping.end())
                        throw std::runtime_error("invalid state checking io_mapping");
                    auto const &new_port = io_mapping.at(sink);
                    auto width = port_width.at(sink);
                    // this is a sink
                    auto port_name = io_names.at(width).second;
                    net[i] = std::make_pair(new_port, port_name);
                    modified = true;
                }
            }
            // notice that we may have repeated entries in the net
            if (modified) {
                std::set<Port> sinks;
                for (uint32_t i = 1; i < net.size(); i++) {
                    sinks.emplace(net[i]);
                }
                net.clear();
                net.reserve(1 + sinks.size());
                net.emplace_back(src);
                for (auto const &sink: sinks) net.emplace_back(sink);
            }
        } else {
            // the src is an external port
            // need to replace it with the external port
            if (io_mapping.find(src) == io_mapping.end())
                throw std::runtime_error("invalid state checking io_mapping");
            auto const &io_src = io_mapping.at(src);
            std::vector<Port> sinks;
            sinks.reserve(net.size() - 1);
            for (uint32_t i = 1; i < net.size(); i++) {
                auto const &sink = net[i];
                if (blks.find(sink.first) != blks.end()) {
                    sinks.emplace_back(sink);
                }
            }
            net.clear();
            net.reserve(sinks.size() + 1);
            // this is src
            auto width = port_width.at(src);
            auto port_name = io_names.at(width).first;
            net.emplace_back(std::make_pair(io_src, port_name));
            for (auto const &sink: sinks) {
                net.emplace_back(sink);
            }
        }
    }
}

std::pair<std::vector<std::string>,
        std::unordered_map<char, std::string>>
parse_argv(int argc, char *argv[]) {
    std::vector<std::string> args;
    std::unordered_map<char, std::string> flag_values;
    int idx = 1;
    std::string value;
    char flag = '\0';
    while (idx < argc) {
        value = argv[idx];
        if (value.length() == 2 && value[0] == '-') {
            flag = value[1];
        } else {
            if (flag != '\0') {
                flag_values.emplace(flag, value);
            } else {
                args.emplace_back(value);
            }
            flag = '\0';
        }
        idx++;
    }
    if (flag != '\0')
        throw std::runtime_error("Invalid flag " + std::string(flag, 1));

    return std::make_pair(args, flag_values);
}

std::map<Port, std::string>
get_io_mapping(const Netlist &netlist,
               std::map<BlockID, std::string> &id_to_name,
               const std::map<uint32_t, std::pair<std::set<Port>, std::set<Port>>> &extra_ports,
               const std::map<Port, uint32_t> &port_width) {
    std::map<Port, std::string> io_mapping;
    // function to add new IO ports
    auto add_io = [&id_to_name](const std::string &name, uint32_t width) {
        std::string prefix = width == 1 ? "1" : "I";
        auto id = id_to_name.size();
        std::string blk_id;
        do {
            blk_id = prefix + std::to_string(id);
            id++;
        } while (id_to_name.find(blk_id) != id_to_name.end());
        id_to_name.emplace(blk_id, name);
        return blk_id;
    };
    for (auto const &[cluster_id_0, ports_0]: extra_ports) {
        auto const &[inputs_0, outputs_0] = ports_0;
        for (auto const &[cluster_id_1, ports_1]: extra_ports) {
            if (cluster_id_0 == cluster_id_1) continue;
            auto const &[inputs_1, outputs_1] = ports_1;
            for (auto const &input: inputs_0) {
                for (auto const &output: outputs_1) {
                    if (is_connected(input, output, netlist)) {
                        auto width = port_width.at(input);
                        if (io_mapping.find(input) == io_mapping.end()) {
                            auto blk = add_io("virtualized_io_" + id_to_name.at(input.first) + "_" + input.second,
                                              width);
                            io_mapping.emplace(input, blk);
                        }
                        auto input_id = io_mapping.at(input);
                        io_mapping.emplace(output, input_id);
                    }
                }
            }
        }
    }
    return io_mapping;
}

std::unordered_map<uint32_t, std::map<BlockID, std::string>>
get_partition_id_to_names(const std::map<BlockID, std::string> &id_to_name,
                          const std::map<uint32_t, Netlist> &partition_result) {
    std::unordered_map<uint32_t, std::map<BlockID, std::string>> partition_id_to_names;
    for (auto const &[cluster_id, netlist]: partition_result) {
        std::map<std::string, std::string> names;
        for (auto const &iter: netlist) {
            auto const &net = iter.second;
            for (auto const &port: net) {
                if (names.find(port.first) == names.end()) {
                    names.emplace(port.first, id_to_name.at(port.first));
                }
            }
        }
        partition_id_to_names.emplace(cluster_id, names);
    }
    return partition_id_to_names;
}

std::map<Port, uint32_t>
index_port_width(const Netlist &netlist, const std::map<NetID, uint32_t> &bus_mode) {
    std::map<Port, uint32_t> port_width;
    for (auto const &[net_id, net]: netlist) {
        auto width = bus_mode.at(net_id);
        for (auto const &port: net)
            port_width.emplace(port, width);
    }
    return port_width;
}

std::string get_new_net_id(const std::map<NetID, uint32_t> &bus_mode) {
    uint64_t id = bus_mode.size();
    std::string net_id;
    do {
        net_id = std::string("e" + std::to_string(id));
        id++;
    } while (bus_mode.find(net_id) != bus_mode.end());
    return net_id;
}

std::pair<Port, std::set<Port>> extract_reset_ports(Netlist &netlist, std::map<BlockID, std::string> &id_to_names,
                                                    const std::map<Port, uint32_t> &port_width,
                                                    std::map<std::string, uint32_t> &bus_mode) {
    std::set<Port> result;
    // we assume there is only one reset net
    Port reset = {"", ""};
    for (auto const &[net_id, net]: netlist) {
        auto const &src = net[0];
        auto const &src_name = id_to_names.at(src.first);
        auto width = port_width.at(src);
        if (src_name.find("reset") != std::string::npos && width == 1) {
            // this is the reset net
            reset = src;
            for (uint64_t i = 1; i < net.size(); i++) {
                result.emplace(net[i]);
            }

            // remove the net
            netlist.erase(net_id);
            bus_mode.erase(net_id);
            break;
        }
    }

    return std::make_pair(reset, result);
}

void add_reset(Netlist &netlist, const Port &reset_port, std::set<BlockID> &cluster, const std::set<Port> &reset_blks,
               std::map<NetID, uint32_t> &bus_mode) {
    auto new_net_id = get_new_net_id(bus_mode);
    auto net = std::vector<Port>();
    net.emplace_back(reset_port);
    for (auto const &port: reset_blks) {
        if (cluster.find(port.first) != cluster.end()) {
            net.emplace_back(port);
        }
    }
    // add it to the netlist
    netlist.emplace(new_net_id, net);
    cluster.emplace(reset_port.first);
    bus_mode.emplace(new_net_id, 1);
}

void fix_clusters(const Netlist &netlist, std::map<int, std::set<BlockID>> &raw_clusters) {
    std::unordered_set<int> visited_cluster;
    uint64_t cluster_size = 0;
    while (cluster_size != raw_clusters.size()) {
        bool modified = false;
        for (auto &[cluster_id0, cluster0]: raw_clusters) {
            if (modified) break;
            for (auto const &[cluster_id1, cluster1]: raw_clusters) {
                if (cluster_id0 == cluster_id1) continue;
                // see if there is any di-directional connections
                bool from_0_to_1 = false;
                bool from_1_to_0 = false;
                // brute-force search clusters. this is O(NM)
                for (auto const &blk0: cluster0) {
                    for (auto const &blk1: cluster1) {
                        if (is_driving(blk0, blk1, netlist))
                            from_0_to_1 = true;
                        if (is_driving(blk1, blk0, netlist))
                            from_1_to_0 = true;
                    }
                    if (from_0_to_1 && from_1_to_0) break;
                }

                // to see if we need to merge
                if (from_0_to_1 && from_1_to_0) {
                    // merge these two
                    // delete 1 and merge into 0
                    for (auto const &blk: cluster1) {
                        cluster0.emplace(blk);
                    }
                    raw_clusters.erase(cluster_id1);
                    modified = true;
                    break;
                }
            }
        }

        cluster_size = raw_clusters.size();
    }
}

int main(int argc, char *argv[]) {
    auto[args, flag_values] = parse_argv(argc, argv);
    if (args.size() != 2) {
        std::cerr << "Usage " << argv[0] << "raw_netlist.packed output_dir"
                  << std::endl;
        return EXIT_FAILURE;
    }
    std::string filename = args[0];
    std::string dirname = args[1];

    auto[netlist, bus_mode] = load_netlist(filename);
    auto id_to_name = load_id_to_name(filename);

    // index port width
    auto port_width = index_port_width(netlist, bus_mode);

    // remove the reset
    auto[reset_port, connected_reset_port] = extract_reset_ports(netlist, id_to_name, port_width, bus_mode);
    bool has_reset = !reset_port.first.empty();

    std::map<int, std::set<BlockID>> raw_clusters;
    if (flag_values.find('c') == flag_values.end()) {
        // remove unnecessary information
        auto simplified_netlist = convert_netlist(netlist);
        threshold_partition_netlist(simplified_netlist, raw_clusters);
    } else {
        // manually read out the partition list
        raw_clusters = read_partition_result(flag_values.at('c'));
    }
    // make sure the clusters are legal
    fix_clusters(netlist, raw_clusters);

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
    auto io_mapping = get_io_mapping(netlist, id_to_name, extra_ports, port_width);

    // partition the netlist based on the clustering result, also fix the netlist
    // based on the clusters
    std::map<uint32_t, Netlist> partition_result;
    for (auto &[cluster_id, cluster]: raw_clusters) {
        auto cluster_netlist = create_cluster_netlist(netlist, cluster);
        fix_netlist(cluster_netlist, cluster, io_mapping, io_names, port_width);
        if (has_reset) {
            // need to reinsert the reset net
            add_reset(cluster_netlist, reset_port, cluster, connected_reset_port, bus_mode);
        }
        partition_result.emplace(cluster_id, cluster_netlist);
    }

    // need to create_id_to_name as well
    auto partition_id_to_names = get_partition_id_to_names(id_to_name, partition_result);

    // write out the final result
    if (!fs::dir_exists(dirname)) {
        fs::mkdir_(dirname);
    }

    // write out the new netlist
    for (auto const &[cluster_id, partition_netlist]: partition_result) {
        auto fn = fs::join(dirname, std::to_string(cluster_id) + ".packed");
        auto const &i2n = partition_id_to_names.at(cluster_id);
        save_netlist(partition_netlist, bus_mode, i2n, fn);
    }
}