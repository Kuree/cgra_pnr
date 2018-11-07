#ifndef THUNDER_ANNEAL_HH
#define THUNDER_ANNEAL_HH

#include <set>
#include <map>
#include "include/randutils.hpp"
#include "util.hh"


class SimAnneal {
public:
    SimAnneal();

    virtual double init_energy() { return 0; }
    virtual double energy() { return 0; }
    virtual void anneal();
    void refine(int num_iter, double threshold);
    double estimate(uint32_t steps=10000);

    // attributes
    // default values
    int steps = 50000;
    float tmax = 25000;
    float tmin = 3;

protected:
    virtual void move() {}
    virtual void commit_changes() {}
    double curr_energy = 0;
    int current_step = 0;
private:
    randutils::random_generator<std::mt19937> rand_;
};


#endif //THUNDER_ANNEAL_HH
