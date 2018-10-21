#include "util.hh"
#include <set>
#include <cassert>

using std::pair;
using std::map;
using std::vector;
using std::string;
using std::set;

bool operator< (const Point &p1, const Point &p2) {
    return ::pair<int, int>({p1.x, p1.y}) < ::pair<int, int>({p2.x, p2.y});
}

bool operator== (const Point &p1, const Point &p2) {
    return p1.x == p2.x && p1.y == p2.y;
}

std::ostream& operator<<(std::ostream& os, const Point &p) {
    os << "x: " << p.x << " y: " << p.y;
    return os;
}

double get_hpwl(const std::vector<Net> &netlist, const std::vector<Instance> &instances) {
    double hpwl = 0;
    for (auto const &net : netlist) {
        int xmin = INT_MAX;
        int xmax = INT_MIN;
        int ymin = INT_MAX;
        int ymax = INT_MIN;
        for (const int blk_id : net.instances) {
            const auto &pos = instances[blk_id].pos;
            if (pos.x < xmin)
                xmin = pos.x;
            if (pos.x > xmax)
                xmax = pos.x;
            if (pos.y < ymin)
                ymin = pos.y;
            if (pos.y > ymax)
                ymax = pos.y;
        }
        hpwl += (xmax - xmin) + (ymax - ymin);
    }
    return hpwl;
}

::vector<::string> squash_net(::map<::string, ::vector<::string>> &nets,
                     const ::string &src_id,
                     ::map<::string, ::string> reg_srcs) {
    ::vector<::string> result = {src_id};

    for (uint32_t i = 1; i < nets[src_id].size(); i++) {
        auto b_id = nets[src_id][i];
        if (b_id[0] == 'r') {
            // found the next reg
            auto next_id = reg_srcs[b_id];
            auto r = squash_net(nets, next_id, reg_srcs);
            result.insert(result.end(), r.begin(), r.end());
        }
    }
    return result;
};

std::map<::string, ::vector<::string>> group_reg_nets(
        ::map<::string, ::vector<::string>> &netlist) {
    // direct translation from Python implementation
    ::map<::string, ::vector<::string>> linked_nets;
    ::map<::string, ::string> reg_srcs;
    ::set<::string> reg_srcs_nets;
    uint32_t net_id_to_remove = 0;
    ::set<::string> resolved_net;

    for (auto const &net_iter : netlist) {
        auto net_id = net_iter.first;
        auto net = net_iter.second;
        if (net[0][0] == 'r') {
            auto reg_id = net[0];
            reg_srcs[reg_id] = net_id;
            reg_srcs_nets.insert(net_id);
            net_id_to_remove++;
        }
    }

    for (auto const &iter : reg_srcs) {
        auto reg_id = iter.first;
        auto r_net_id = iter.second;
        if (resolved_net.find(r_net_id) != resolved_net.end())
            continue;
        // search for the ultimate src
        auto reg = netlist[r_net_id][0];
        for (auto const &iter2 : netlist) {
            auto net_id = iter2.first;
            if (reg_srcs_nets.find(net_id) != reg_srcs_nets.end())
                continue;
            auto net = iter2.second;
            for (auto const &blk_id : net) {
                if (blk_id == reg) {
                    // found the ultimate src
                    // now do a squash to obtain the set of all nets
                    auto merged_nets = squash_net(netlist, r_net_id, reg_srcs);
                    for (auto const &m_id : merged_nets) {
                        resolved_net.insert(m_id);
                    }
                    if (linked_nets.find(net_id) != linked_nets.end()) {
                        linked_nets[net_id].insert(linked_nets[net_id].end(),
                                                   merged_nets.begin(),
                                                   merged_nets.end());
                    } else {
                        linked_nets[net_id] = merged_nets;
                    }

                }
            }
        }
    }

    // make sure we've merged every nets
    if (resolved_net.size() != net_id_to_remove) {
        throw std::runtime_error("unexpected resolve size: " +
                std::to_string(resolved_net.size()) + " "
                + std::to_string(net_id_to_remove));
    }

    return linked_nets;
}