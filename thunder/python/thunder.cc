#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <vector>
#include <algorithm>
#include "../src/detailed.hh"
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

    py::class_<DetailedPlacer>(m, "DetailedPlacer").def(py::init<::vector<::string>,
            ::map<::string, ::vector<std::string>>,
            ::map<char, ::vector<::pair<int, int>>>,
            ::map<::string, ::pair<int, int>>,
            char,
            bool>())
            .def("anneal", &SimAnneal::anneal)
            .def("realize", &DetailedPlacer::realize)
            .def("refine", &SimAnneal::refine)
            .def_readwrite("steps", &DetailedPlacer::steps);
}

void init_detailed_placement(py::module &m) {
    m.def("detailed_placement", &multi_place);
}

PYBIND11_MODULE(pythunder, m) {
    m.doc() = "pythunder";
    init_pythunder(m);
    init_detailed_placement(m);
}