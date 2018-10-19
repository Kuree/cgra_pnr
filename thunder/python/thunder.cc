#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include "../src/detailed.hh"

namespace py = pybind11;

void init_pythunder(py::module &m) {
    py::class_<DetailedMove>(m, "DetailedMove")
            .def(py::init<>());

    py::class_<DetailedPlacer>(m, "DetailedPlacer").def(py::init<std::vector<std::string>,
            std::map<std::string, std::vector<std::string>>,
            std::map<char, std::vector<std::pair<int, int>>>,
            std::map<std::string, std::pair<int, int>>,
            char,
            bool>())
            .def("anneal", &SimAnneal::anneal)
            .def("realize", &DetailedPlacer::realize)
            .def("refine", &SimAnneal::refine);
}

PYBIND11_MODULE(pythunder, m) {
    m.doc() = "pythunder";
    init_pythunder(m);
}