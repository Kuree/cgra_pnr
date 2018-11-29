#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "../src/graph.hh"

namespace py = pybind11;
using std::to_string;


void init_graph(py::module &m) {
    py::enum_<NodeType>(m, "NodeType")
        .value("SwitchBox", NodeType::SwitchBox)
        .value("ConnectionBox", NodeType::ConnectionBox)
        .value("Port", NodeType::Port);
    py::class_<Node>(m, "Node")
        .def(py::init<NodeType, uint32_t, uint32_t>())
        .def(py::init<NodeType, uint32_t, uint32_t, uint32_t>())
        .def(py::init<const std::string &, uint32_t, uint32_t>())
        .def_readwrite("type", &Node::type)
        .def_readwrite("name", &Node::name)
        .def_readwrite("track", &Node::track)
        .def_readwrite("x", &Node::x)
        .def_readwrite("y", &Node::y)
        .def_readonly("neighbors", &Node::neighbors)
        .def("__repr__", [](const Node &node) -> std::string {
            switch(node.type) {
                case NodeType::SwitchBox:
                    return "SB (" + ::to_string(node.x) + ", "
                            + ::to_string(node.y) + ")";
                case NodeType::ConnectionBox:
                    return "CB (" + ::to_string(node.x) + ", "
                           + ::to_string(node.y) + ")";
                case NodeType::Port:
                    return node.name + " (" + ::to_string(node.x) + ", "
                           + ::to_string(node.y) + ")";
                default:
                    return "Node";
            }
        });
    py::class_<RoutingGraph>(m, "RoutingGraph")
        .def(py::init<>())
        .def("add_edge", &RoutingGraph::add_edge)
        .def("get_nodes", &RoutingGraph::get_nodes);
}


PYBIND11_MODULE(pycyclone, m) {
    m.doc() = "pycyclone";
    init_graph(m);
}