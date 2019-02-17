#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <algorithm>
#include "../src/detailed.hh"
#include "../src/vpr.hh"
#include "../src/global.hh"
#include "../src/multi_place.hh"
#include "../src/layout.hh"
#include "../src/io.hh"
#include "../src/graph.hh"
#include "../src/util.hh"

namespace py = pybind11;
using std::move;
using std::vector;
using std::map;
using std::string;
using std::pair;
using std::set;


void init_io(py::module &m) {
    auto io_m = m.def_submodule("io");

    io_m.def("load_layout", &load_layout)
        .def("dump_layout", &dump_layout);
}

void init_graph(py::module &m) {
    auto graph_m = m.def_submodule("graph");

    graph_m.def("partition_netlist", &partition_netlist);
}

void init_util(py::module &m) {
    auto util_m = m.def_submodule("util");
    util_m.def("convert_clusters", &convert_clusters);
    util_m.def("filter_clusters", &filter_clusters);
}


void init_layout(py::module &m) {
    py::class_<Layer>(m, "Layer")
            .def(py::init<char, uint32_t, uint32_t>())
            .def(py::init<const Layer &>())
            .def_readwrite("blk_type", &Layer::blk_type)
            .def("mark_available", &Layer::mark_available)
            .def("mark_unavailable", &Layer::mark_unavailable)
            .def("produce_available_pos", &Layer::produce_available_pos)
            .def_readwrite("blk_type", &Layer::blk_type)
            .def("__getitem__", [](const Layer &layer,
                                   const std::pair<uint32_t, uint32_t> &pos) {
                return layer[pos];
            });
    py::class_<Layout>(m, "Layout")
            .def(py::init<>())
            .def(py::init<const std::map<char,
                    std::vector<std::vector<bool>>> &>())
            .def(py::init<const std::vector<std::vector<char>> &>())
            .def("add_layer",
                 py::overload_cast<const Layer&>(&Layout::add_layer))
            .def("add_layer",
                 py::overload_cast<const Layer&,
                         uint32_t, uint32_t>(&Layout::add_layer))
            .def_readwrite_static("DEFAULT_PRIORITY", &Layout::DEFAULT_PRIORITY)
            .def("is_legal", &Layout::is_legal)
            .def("get_blk_type", &Layout::get_blk_type)
            .def("get_blk_types", &Layout::get_blk_types)
            .def("get_layer", &Layout::get_layer)
            .def("get_priority_major", &Layout::get_priority_major)
            .def("get_priority_minor", &Layout::get_priority_minor)
            .def("get_layer_types", &Layout::get_layer_types)
            .def("set_priority_major", &Layout::set_priority_major)
            .def("set_priority_minor", &Layout::set_priority_minor)
            .def("produce_available_pos", &Layout::produce_available_pos)
            .def("get_layer_masks", &Layout::get_layer_masks)
            .def("add_layer_mask", &Layout::add_layer_mask)
            .def("get_clb_type", &Layout::get_clb_type)
            .def("get_margin", &Layout::get_margin)
            .def("height", &Layout::height)
            .def("width", &Layout::width)
            .def("__repr__", &Layout::layout_repr);

    py::class_<LayerMask>(m, "LayerMask")
            .def(py::init<>())
            .def_readwrite("blk_type", &LayerMask::blk_type)
            .def_readwrite("mask_blk_type", &LayerMask::mask_blk_type)
            .def("add_mask_pos",
                    [](LayerMask &mask,
                       const std::pair<uint32_t, uint32_t> &blk_pos,
                       std::vector<std::pair<uint32_t, uint32_t>> &list) {
                if (mask.mask_pos.find(blk_pos) != mask.mask_pos.end())
                    throw std::runtime_error("pos already exists");
                mask.mask_pos[blk_pos] = list;
            })
            .def_readwrite("mask_pos", &LayerMask::mask_pos,
                           py::return_value_policy::reference);
}

void init_pythunder(py::module &m) {
    py::class_<DetailedMove>(m, "DetailedMove")
            .def(py::init<>());

    py::class_<DetailedPlacer>(m, "DetailedPlacer")
            .def(py::init<::vector<::string>,
                 ::map<::string, ::vector<std::string>>,
                 ::map<char, ::vector<::pair<int, int>>>,
                 ::map<::string, ::pair<int, int>>,
                 char,
                 bool>())
            .def(py::init<::map<::string, ::pair<int, int>>,
                    ::map<::string, ::vector<std::string>>,
                    ::map<char, ::vector<::pair<int, int>>>,
                    ::map<::string, ::pair<int, int>>,
                    char,
                    bool>())
            .def("anneal", &SimAnneal::anneal)
            .def("realize", &DetailedPlacer::realize)
            .def("refine", &SimAnneal::refine)
            .def("estimate", &DetailedPlacer::estimate)
            .def("set_seed", &DetailedPlacer::set_seed)
            .def_readwrite("steps", &DetailedPlacer::steps)
            .def_readwrite("tmax", &DetailedPlacer::tmax)
            .def_readwrite("tmin", &DetailedPlacer::tmin);

    py::class_<VPRPlacer>(m, "VPRPlacer")
            .def(py::init<std::map<std::string, std::pair<int, int>>,
                    std::map<std::string, std::vector<std::string>>,
                    std::map<char, std::vector<std::pair<int, int>>>,
                    std::map<std::string, std::pair<int, int>>,
                    char,
                    bool>())
            .def("anneal", &VPRPlacer::anneal)
            .def("realize", &VPRPlacer::realize);

    py::class_<GlobalPlacer>(m, "GlobalPlacer")
            .def(py::init<std::map<std::string, std::set<std::string>>,
                    std::map<std::string, std::vector<std::string>>,
                    std::map<std::string, std::pair<int, int>>,
                    const Layout&>())
            .def("solve", &GlobalPlacer::solve)
            .def("realize", &GlobalPlacer::realize)
            .def("anneal", &SimAnneal::anneal)
            .def("set_seed", &GlobalPlacer::set_seed)
            .def_readwrite("anneal_param_factor",
                           &GlobalPlacer::anneal_param_factor)
            .def_readwrite("steps", &GlobalPlacer::steps);
}

void init_detailed_placement(py::module &m) {
    m.def("detailed_placement",
            py::overload_cast<const ::map<::string, std::set<std::string>>&,
            const ::map<::string, ::map<char, std::set<std::pair<int, int>>>>&,
            const ::map<::string, ::map<std::string, std::vector<std::string>>>&,
            const ::map<::string, ::map<std::string, std::pair<int, int>>>&,
            char, bool>(&multi_place))
      .def("detailed_placement",
             py::overload_cast<const ::map<::string, std::set<std::string>>&,
             const ::map<::string, ::map<char, std::set<std::pair<int, int>>>>&,
             const ::map<::string, ::map<::string, std::vector<std::string>>>&,
             const ::map<::string, ::map<::string, std::pair<int, int>>>&,
             char, bool, uint32_t>(&multi_place));
}

PYBIND11_MODULE(pythunder, m) {
    m.doc() = "pythunder";
    init_pythunder(m);
    init_detailed_placement(m);
    init_layout(m);
    init_io(m);
    init_graph(m);
    init_util(m);
}
