#ifndef THUNDER_UTIL_HH
#define THUNDER_UTIL_HH
#include <string>
#include <vector>
#include <map>
#include <climits>
#include <iterator>
#include <set>

struct Net;

struct Point {
    int x = 0;
    int y = 0;

    Point() = default;
    Point(const int x, const int y) : x(x), y(y) {}
    Point(const Point &p) { x = p.x; y = p.y; }
    explicit Point(const std::pair<int, int> &p) { x = p.first; y = p.second; }
    explicit operator std::string() const { return "x: " + std::to_string(x) +
                                            " y: " + std::to_string(y); }
};

std::ostream& operator<<(std::ostream& os, const Point &p);
bool operator< (const Point &p1, const Point &p2);
bool operator== (const Point &p1, const Point &p2);

struct Instance {
    std::string name;
    struct Point pos;
    int id = -1;
    std::vector<int> nets;

    Instance() = default;
    Instance(const std::string &name, const struct Point &pos,
            const int id) :
            name(name), pos(pos), id(id) {}
    Instance(const std::string &name, const std::pair<int, int> &pos,
             const int id) :
            name(name), pos(pos), id(id) {}
    Instance(const char name, const struct Point &pos,
             const int id):
             name(std::string(1, name)), pos(pos), id(id) {}
    Instance(const char name, const std::pair<int, int> &pos,
             const int id):
            name(std::string(1, name)), pos(pos), id(id) {}

};

struct Net {
    std::string net_id;
    std::vector<int> instances;
};

double get_hpwl(const std::vector<Net> &netlist,
                const std::vector<Instance> &instances);

std::map<std::string, std::vector<std::string>> group_reg_nets(
        std::map<std::string, std::vector<std::string>> &netlist);

inline std::pair<int, int> compute_overlap(const Point &p1, const Point &p2,
                                           const Point &p3, const Point &p4) {
    int dx = std::min(p2.x, p4.x) - std::max(p1.x, p3.x);
    int dy = std::min(p2.y, p4.y) - std::max(p1.y, p3.y);
    return {dx, dy};
}

std::map<std::string, std::set<std::string>>
convert_clusters(const std::map<int, std::set<std::string>> &clusters,
                 const std::map<std::string, std::pair<int, int>> &fixed_pos);

std::map<int, std::set<std::string>>
filter_clusters(const std::map<int, std::set<std::string>> &clusters,
                const std::map<std::string, std::pair<int, int>> &fixed_pos);

std::map<std::string, std::pair<int, int>>
compute_centroids(const std::map<std::string,
                                 std::map<char,
                                          std::set<std::pair<int,
                                                             int>>>> &clusters,
                  char clb_type);

std::map<std::string, std::vector<std::string>>
reduce_cluster_graph(const std::map<std::string,
                                    std::vector<std::string>> &netlist,
                     const std::map<std::string,
                                    std::set<std::string>> &clusters,
                     const std::map<std::string,
                             std::pair<int, int>> &fixed_blocks,
                     const std::string &cluster_id);

std::map<std::string, std::pair<int, int>>
get_cluster_fixed_pos(const std::map<std::string,
                                     std::pair<int, int>> &fixed_blocks,
                      const std::map<std::string,
                                     std::pair<int, int>> &centroids);

#endif //THUNDER_UTIL_HH
