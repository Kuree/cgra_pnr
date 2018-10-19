#include "util.hh"

using std::pair;

bool operator< (const Point &p1, const Point &p2) {
    return ::pair<int, int>({p1.x, p1.y}) < ::pair<int, int>({p2.x, p2.y});
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