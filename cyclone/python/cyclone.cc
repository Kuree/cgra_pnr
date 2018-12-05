#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "../src/graph.hh"
#include "../src/route.hh"
#include "../src/global.hh"

namespace py = pybind11;
using std::to_string;

// just to be lazy with meta programming
template<class T>
void init_node_class(py::class_<T> &class_) {
    class_
        .def_readwrite("type", &T::type)
        .def_readwrite("name", &T::name)
        .def_readwrite("x", &T::x)
        .def_readwrite("y", &T::y)
        .def_readwrite("width", &T::width)
        .def_readwrite("delay", &T::delay)
        .def_readwrite("track", &T::track)
        .def("add_edge",
           py::overload_cast<const std::shared_ptr<Node> &>(&Node::add_edge))
        .def("get_edge_cost", &T::get_edge_cost)
        .def("__repr__", [](const T &node) -> std::string {
          switch(node.type) {
              case NodeType::SwitchBox:
                  return "SB (" + ::to_string(node.x) + ", "
                         + ::to_string(node.y) + ")";
              case NodeType::Port:
              case NodeType::Register:
                  return node.name + " (" + ::to_string(node.x) + ", "
                         + ::to_string(node.y) + ")";
              default:
                  return "Node";
          }
        });
}

template<class T>
void init_router_class(py::class_<T> &class_) {
    class_
        .def("add_net", &Router::add_net)
        .def("add_edge", &Router::add_edge)
        .def("add_placement", &Router::add_placement)
        .def("overflow", &Router::overflow);
}


void init_graph(py::module &m) {
    py::enum_<NodeType>(m, "NodeType")
        .value("SwitchBox", NodeType::SwitchBox)
        .value("Port", NodeType::Port);

    py::class_<PortNode> p_node(m, "PortNode");
    init_node_class<PortNode>(p_node);
    p_node
        .def(py::init<const std::string &, uint32_t, uint32_t, uint32_t>())
        .def(py::init<const std::string &, uint32_t, uint32_t>());

    py::class_<RegisterNode> r_node(m, "RegisterNode");
    init_node_class<RegisterNode>(r_node);
    r_node
        .def(py::init<const std::string &, uint32_t, uint32_t, uint32_t,
                      uint32_t>());

    py::class_<SwitchBoxNode> sb_node(m, "SwitchBoxNode");
    init_node_class<SwitchBoxNode>(sb_node);
    sb_node
        .def(py::init<uint32_t, uint32_t, uint32_t, uint32_t>())
        .def("clear", &SwitchBoxNode::clear);

    py::class_<Tile>(m, "Tile")
        .def(py::init<uint32_t, uint32_t, uint32_t>())
        .def(py::init<uint32_t, uint32_t, uint32_t, uint32_t>())
        .def_readwrite("x", &Tile::x)
        .def_readwrite("y", &Tile::y)
        .def_readwrite("height", &Tile::height)
        .def("num_tracks", &Tile::num_tracks);

    py::class_<RoutingGraph>(m, "RoutingGraph")
        .def(py::init<>())
        .def(py::init<uint32_t, uint32_t, uint32_t, const SwitchBoxNode &>())
        .def("add_tile", &RoutingGraph::add_tile)
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &, uint32_t>(&RoutingGraph::add_edge))
        .def("get_sb", &RoutingGraph::get_sb)
        .def("get_port", &RoutingGraph::get_port);
}

void init_router(py::module &m) {
    py::class_<Router> router(m, "Router");
    router.def(py::init<>());
    init_router_class<Router>(router);

    py::class_<GlobalRouter> gr(m, "GlobalRouter");
    gr.def(py::init<uint32_t>());
    init_router_class<GlobalRouter>(gr);
}

PYBIND11_MODULE(pycyclone, m) {
    m.doc() = "pycyclone";
    init_graph(m);
    init_router(m);
}