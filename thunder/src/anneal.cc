#include <math.h>
#include <chrono>
#include "anneal.hh"
#include "include/tqdm.h"


SimAnneal::SimAnneal() {
    rand_.seed(0);
}

void SimAnneal::anneal() {
    float t_factor = -log(tmax / tmin);
    // random setup
    tqdm bar;
    for (current_step = 0; current_step < steps; current_step++) {
        bar.progress(current_step, steps);
        float t = tmax * exp(t_factor * current_step / steps);
        // make changes
        move();
        double new_energy = energy();
        double de = new_energy - this->curr_energy;
        if (de > 0.0 && exp(-de / t) < rand_.uniform<double>(0.0, 1.0)) {
            continue;
        } else {
            commit_changes();
            this->curr_energy = new_energy;
        }
    }
    bar.finish();
}

void SimAnneal::refine(int num_iter, double threshold) {
    tqdm bar;
    while (true) {
        double old_energy = this->curr_energy;
        for (int i = 0; i < num_iter; i++) {
            bar.progress(i, num_iter);
            move();
            double new_energy = energy();
            double de = new_energy - this->curr_energy;
            if (de < 0) {
                commit_changes();
                this->curr_energy = new_energy;
            }
        }
        if ((old_energy - this->curr_energy) / old_energy < threshold)
            break;
    }
    bar.finish();
}

double SimAnneal::estimate(const uint32_t steps) {
    auto start = std::chrono::system_clock::now();
    for (uint32_t i = 0; i < steps; i++) {
        move();
        energy();
    }

    auto end = std::chrono::system_clock::now();
    auto elapsed =
            std::chrono::duration_cast<std::chrono::milliseconds>(end - start);
    double time = elapsed.count();
    // this is in ms
    double total_time = time * this->steps / steps;

    return total_time;
}