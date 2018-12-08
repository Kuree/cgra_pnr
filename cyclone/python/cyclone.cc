#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <sstream>
#include "../src/graph.hh"
#include "../src/route.hh"
#include "../src/global.hh"
#include "../src/util.hh"

namespace py = pybind11;
using std::to_string;

// just to be lazy with meta programming
template<class T, class D>
void init_node_class(py::class_<T, D> &class_) {
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
            std::ostringstream os; os << node; return os.str();
        })
        .def("__iter__", [](const T &node) {
            return py::make_iterator(node.begin(), node.end());
        }, py::keep_alive<0, 1>());
}

template<class T>
void init_router_class(py::class_<T> &class_) {
    class_
        .def("add_net", &T::add_net)
        .def("add_placement", &T::add_placement)
        .def("overflow", &T::overflow)
        .def("route", &T::route)
        .def("realize", &T::realize);
}

void init_graph(py::module &m) {
    py::enum_<NodeType>(m, "NodeType")
        .value("SwitchBox", NodeType::SwitchBox)
        .value("Port", NodeType::Port)
        .value("Register", NodeType::Register);

    py::enum_<SwitchBoxSide>(m, "SwitchBoxSide")
        .value("Left", SwitchBoxSide::Left)
        .value("Bottom", SwitchBoxSide::Bottom)
        .value("Right", SwitchBoxSide::Right)
        .value("Top", SwitchBoxSide::Top);

    // the generic node type
    py::class_<Node, std::shared_ptr<Node>> node(m, "Node");
    // init_node_class<Node>(node);
    node.def(py::init<>());

    py::class_<PortNode, std::shared_ptr<PortNode>> p_node(m, "PortNode", node);
    init_node_class<PortNode, std::shared_ptr<PortNode>>(p_node);
    p_node
        .def(py::init<const std::string &, uint32_t, uint32_t, uint32_t>())
        .def(py::init<const std::string &, uint32_t, uint32_t>());

    py::class_<RegisterNode, std::shared_ptr<RegisterNode>>
    r_node(m, "RegisterNode", node);
    init_node_class<RegisterNode, std::shared_ptr<RegisterNode>>(r_node);
    r_node
        .def(py::init<const std::string &, uint32_t, uint32_t, uint32_t,
                      uint32_t>());

    py::class_<SwitchBoxNode, std::shared_ptr<SwitchBoxNode>>
    sb_node(m, "SwitchBoxNode", node);
    init_node_class<SwitchBoxNode, std::shared_ptr<SwitchBoxNode>>(sb_node);
    sb_node
        .def(py::init<uint32_t, uint32_t, uint32_t, uint32_t>())
        .def("add_side_info", &SwitchBoxNode::add_side_info)
        .def("get_side", &SwitchBoxNode::get_side)
        .def("add_edge",
             py::overload_cast<const std::shared_ptr<Node> &,
                               SwitchBoxSide >(&SwitchBoxNode::add_edge));

    py::class_<Tile>(m, "Tile")
        .def(py::init<>())
        .def(py::init<uint32_t, uint32_t, uint32_t>())
        .def(py::init<uint32_t, uint32_t, uint32_t, uint32_t>())
        .def_readwrite("x", &Tile::x)
        .def_readwrite("y", &Tile::y)
        .def_readwrite("height", &Tile::height)
        .def("num_tracks", &Tile::num_tracks)
        .def_readwrite("sbs", &Tile::sbs)
        .def_readwrite("registers", &Tile::registers)
        .def_readwrite("ports", &Tile::ports);

    py::class_<RoutingGraph>(m, "RoutingGraph")
        .def(py::init<>())
        .def(py::init<uint32_t, uint32_t, uint32_t, const SwitchBoxNode &>())
        .def(py::init<uint32_t, uint32_t, uint32_t,
                      const std::vector<SwitchBoxNode> &>())
        .def("add_tile", &RoutingGraph::add_tile)
        .def("remove_tile", &RoutingGraph::remove_tile)
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &,
                               uint32_t>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &,
                               SwitchBoxSide>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &,
                               SwitchBoxSide,
                               uint32_t>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const SwitchBoxNode &,
                               const SwitchBoxNode &,
                               SwitchBoxSide,
                               SwitchBoxSide>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const SwitchBoxNode &,
                               const SwitchBoxNode &,
                               SwitchBoxSide,
                               SwitchBoxSide,
                               uint32_t>(&RoutingGraph::add_edge))
        .def("get_sb", &RoutingGraph::get_sb)
        .def("get_port", &RoutingGraph::get_port)
        .def("__getitem__", &RoutingGraph::operator[])
        .def("__iter__", [](RoutingGraph &r) {
            return py::make_key_iterator(r.begin(), r.end());
        }, py::keep_alive<0, 1>());
}

void init_router(py::module &m) {
    py::class_<Router> router(m, "Router");
    router.def(py::init<RoutingGraph>());
    init_router_class<Router>(router);

    py::class_<GlobalRouter> gr(m, "GlobalRouter", router);
    gr.def(py::init<uint32_t, RoutingGraph>())
      .def_readwrite("route_strategy_ratio",
                     &GlobalRouter::route_strategy_ratio);
    init_router_class<GlobalRouter>(gr);
}

void init_util(py::module &m) {
    auto util_m = m.def_submodule("util");
    util_m.def("get_side_value", &get_side_value)
          .def("gsv", &get_side_value)
          .def("get_side_int", &get_side_int)
          .def("gsi", &get_side_int)
          .def("get_opposite_side",
               py::overload_cast<SwitchBoxSide>(&get_opposite_side))
          .def("get_opposite_side",
               py::overload_cast<uint32_t>(&get_opposite_side));
}

PYBIND11_MODULE(pycyclone, m) {
    m.doc() = "pycyclone";
    init_graph(m);
    init_router(m);
    init_util(m);
}
