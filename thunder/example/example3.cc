#include "../src/global.hh"
#include "../src/detailed.hh"
#include "../src/layout.hh"
#include "../src/multi_place.hh"


using std::map;
using std::set;
using std::vector;
using std::string;
using std::pair;


int main() {
    auto layout = Layout();
    uint32_t size = 2;
    // 3x3 layout
    auto layer = Layer('p', size, size);
    for (uint32_t x = 0; x < size; x++)
        for (uint32_t y = 0; y < size; y++)
            layer.mark_available(x, y);
    layout.add_layer(layer);

    // two nets
    ::map<::string, ::vector<::string>> netlist = {{"e0", {"p0", "p1"}},
                                                   {"e1", {"p1", "p2", "p3"}}};
    // don't do clustering here
    ::map<::string, ::set<::string>> clusters = {{"x0", {"p0", "p1",
                                                         "p2", "p3"}}};
    // no fixed position
    ::map<::string, ::pair<int, int>> fixed_pos = {};

    // global placement
    auto gp = GlobalPlacer(clusters, netlist, fixed_pos, layout);
    // place in gp
    gp.solve();
    gp.anneal();
    auto gp_result = gp.realize();

    auto dp_result = detailed_placement(clusters, netlist, fixed_pos, gp_result,
                                        layout);
    // global refine
    auto refine_dp = DetailedPlacer(dp_result, netlist,
                                    layout.produce_available_pos(),
                                    fixed_pos, 'p', true);
    refine_dp.refine(1000, 0.001, true);
    auto result = refine_dp.realize();
    // print it out
    for (auto const &[blk_id, pos]: result)
        std::cout << blk_id << ": x " << pos.first << " y " << pos.second
                  << std::endl;

    return EXIT_SUCCESS;
}