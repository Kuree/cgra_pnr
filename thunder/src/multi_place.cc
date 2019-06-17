#include <cassert>
#include <thread>
#include <iostream>
#include "include/cxxpool.h"
#include "multi_place.hh"
#include "detailed.hh"

using std::move;
using std::vector;
using std::map;
using std::string;
using std::pair;
using std::set;


::map<std::string, std::pair<int, int>>  multi_place(
        const ::map<::string, ::set<::string>> &clusters,
        const ::map<::string, ::map<char, ::set<std::pair<int, int>>>> &cells,
        const ::map<::string, ::map<::string, ::vector<::string>>> &netlists,
        const ::map<::string, ::map<::string, ::pair<int, int>>> &fixed_blocks,
        char clb_type, bool fold_reg, uint32_t seed) {

    uint64_t num_clusters = clusters.size();
    // make sure that they have the same size
    assert (num_clusters == cells.size() && num_clusters == netlists.size()
            && num_clusters == fixed_blocks.size());
    uint32_t num_cpus = std::thread::hardware_concurrency();
    // 0 will be returned if it's not detected.
    num_cpus = std::max(1u, num_cpus);
    // use as much resource as possible
    num_cpus = std::min((uint32_t)num_clusters, num_cpus);

    cxxpool::thread_pool pool{num_cpus};

    ::vector<std::future<::map<::string, ::pair<int, int>>>> thread_tasks;

    ::vector<::vector<::string>> clusters_args;
    ::vector<::map<char, ::vector<::pair<int, int>>>> available_pos_args;
    ::vector<::map<std::string, std::vector<std::string>>> netlists_args;
    ::vector<::map<std::string, std::pair<int, int>>> fixed_pos_args;

    for (auto const &iter : clusters) {
        ::string cluster_id = iter.first;
        auto const &cluster_set = clusters.at(cluster_id);
        auto cluster = ::vector<::string>(cluster_set.begin(),
                                          cluster_set.end());

        // check to make sure that we have everything
        assert (cells.find(cluster_id) != cells.end());
        assert (netlists.find(cluster_id) != netlists.end());
        assert (fixed_blocks.find(cluster_id) != fixed_blocks.end());

        auto available_pos_set = cells.at(cluster_id);
        ::map<char, ::vector<::pair<int, int>>> available_pos;
        for (const auto &iter2 : available_pos_set) {
            auto pos = ::vector<::pair<int, int>>(iter2.second.begin(),
                                                  iter2.second.end());
            available_pos.insert({iter2.first, pos});
        }
        auto netlist = netlists.at(cluster_id);
        auto fixed_pos = fixed_blocks.at(cluster_id);

        // assign args
        clusters_args.emplace_back(cluster);
        netlists_args.emplace_back(netlist);
        available_pos_args.emplace_back(available_pos);
        fixed_pos_args.emplace_back(fixed_pos);
    }

    for (uint32_t i = 0; i < clusters_args.size(); i++) {
        auto cluster = clusters_args[i];
        auto netlist = netlists_args[i];
        auto available_pos = available_pos_args[i];
        auto fixed_pos = fixed_pos_args[i];

        auto task = pool.push([=](::vector<::string> blks,
                                 ::map<::string, ::vector<std::string>> n,
                ::map<char, ::vector<::pair<int, int>>> p,
                ::map<::string, ::pair<int, int>> f,
                char c,
                bool fold) {
            DetailedPlacer placer(blks, n, p, f, c, fold);
            placer.set_seed(seed);
            placer.anneal();
            // placer.refine(1000, 0.001, true);
            return placer.realize();
        }, cluster, netlist, available_pos, fixed_pos, clb_type, fold_reg);
        thread_tasks.emplace_back(std::move(task));
    }

    ::map<::string, ::pair<int, int>> result;
    for (auto &task : thread_tasks) {
        auto task_result = task.get();
        for (const auto &iter :task_result) {
            // remove fixed cluster center and dummy blocks
            if (iter.first[0] != 'x')
                result[iter.first] = iter.second;
        }
    }

    return result;
}

::map<std::string, std::pair<int, int>>  multi_place(
        const ::map<::string, ::set<::string>> &clusters,
        const ::map<::string, ::map<char, ::set<std::pair<int, int>>>> &cells,
        const ::map<::string, ::map<::string, ::vector<::string>>> &netlists,
        const ::map<::string, ::map<::string, ::pair<int, int>>> &fixed_blocks,
        char clb_type, bool fold_reg) {
    constexpr uint32_t seed = 0;
    return multi_place(clusters, cells, netlists, fixed_blocks, clb_type,
                       fold_reg, seed);
}

std::map<std::string, std::pair<int, int>>
detailed_placement(const std::map<std::string, std::set<std::string>> &clusters,
                   const std::map<std::string, std::vector<std::string>> &netlist,
                   const std::map<std::string, std::pair<int, int>> &fixed_pos,
                   const std::map<std::string,
                                  std::map<char,
                                  std::set<std::pair<int, int>>>> &gp_result,
                   const Layout &layout) {
    auto centroids = compute_centroids(gp_result);
    // substitutes the clusters
    auto cluster_fixed_pos = get_cluster_fixed_pos(fixed_pos,
                                                   centroids);
    map<string, map<string,
            vector<string>>> multi_netlists;
    // need to replicate the fix pos as well
    map<string, map<string,
            pair<int, int>>> multi_fixed_pos;
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
    return dp_result;
}