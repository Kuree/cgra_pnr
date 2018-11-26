#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <algorithm>
#include "../src/detailed.hh"
#include "../src/vpr.hh"
#include "../src/global.hh"
#include "../src/multi_place.hh"

namespace py = pybind11;
using std::move;
using std::vector;
using std::map;
using std::string;
using std::pair;
using std::set;


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
                    std::vector<std::vector<char>>,
                    char,
                    bool>())
            .def("solve", &GlobalPlacer::solve)
            .def("realize", &GlobalPlacer::realize)
            .def("anneal", &SimAnneal::anneal)
            .def_readwrite("anneal_param_factor",
                           &GlobalPlacer::anneal_param_factor)
            .def_readwrite("steps", &GlobalPlacer::steps);
}

void init_detailed_placement(py::module &m) {
    m.def("detailed_placement", &multi_place);
}

PYBIND11_MODULE(pythunder, m) {
    m.doc() = "pythunder";
    init_pythunder(m);
    init_detailed_placement(m);
}