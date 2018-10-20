#ifndef THUNDER_UTIL_HH
#define THUNDER_UTIL_HH
#include <string>
#include <vector>
#include <map>
#include <climits>
#include <iterator>

struct Net;

struct Point {
    int x = 0;
    int y = 0;

    Point() = default;
    Point(const int x, const int y) : x(x), y(y) {}
    Point(const Point &p) { x = p.x; y = p.y; }
    Point(const std::pair<int, int> &p) { x = p.first; y = p.second; }
};

std::ostream& operator<<(std::ostream& os, const Point &p);
bool operator< (const Point &p1, const Point &p2);

struct Instance {
    std::string name;
    struct Point pos;
    int id = -1;
    std::vector<int> nets;

    Instance() = default;
    Instance(const std::string &name, const struct Point &pos,
            const int id) :
            name(name), pos(pos), id(id) {}
    Instance(const char name, const struct Point &pos,
             const int id):
             name(std::string(1, name)), pos(pos), id(id) {}

};

struct Net {
    std::string net_id;
    std::vector<int> instances;
};

double get_hpwl(const std::vector<Net> &netlist, const std::vector<Instance> &instances);

std::map<std::string, std::vector<std::string>> group_reg_nets(
        std::map<std::string, std::vector<std::string>> &netlist);

#endif //THUNDER_UTIL_HH
