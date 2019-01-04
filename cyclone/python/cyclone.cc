#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <sstream>
#include "../src/graph.hh"
#include "../src/route.hh"
#include "../src/global.hh"
#include "../src/util.hh"
#include "../src/io.hh"

namespace py = pybind11;
using std::to_string;
using std::vector;

const int Switch::SIDES;
const int Switch::IOS;

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
        .def("size", &T::size)
        .def("add_edge",
           py::overload_cast<const std::shared_ptr<Node> &>(&Node::add_edge))
        .def("get_edge_cost", &T::get_edge_cost)
        .def("remove_edge", &T::remove_edge)
        .def("get_conn_in", &T::get_conn_in, py::return_value_policy::reference)
        .def("__repr__", &T::to_string)
        .def("__iter__", [](const T &node) {
            return py::make_iterator(node.begin(), node.end());
        }, py::keep_alive<0, 1>(), py::return_value_policy::reference);
}

template<class T>
void init_router_class(py::class_<T> &class_) {
    class_
        .def("add_net", &T::add_net)
        .def("add_placement", &T::add_placement)
        .def("overflow", &T::overflow)
        .def("route", &T::route)
        .def("realize", &T::realize)
        // getter & setter
        .def("get_init_pn", &T::get_init_pn)
        .def("set_init_pn", &T::set_init_pn)
        .def("get_pn_factor", &T::get_pn_factor)
        .def("set_pn_factor", &T::set_pn_factor)
        .def("get_netlist", &T::get_netlist);
}

void init_netlist(py::module &m) {
    py::class_<Net>(m, "Net")
        .def(py::init<>())
        .def(py::init<const std::string &,
                      std::vector<std::pair<std::pair<uint32_t, uint32_t>,
                                                      std::pair<std::string,
                                            std::string>>>>())
        .def("", &Net::size)
        .def_readwrite("name", &Net::name)
        .def_readwrite("fixed", &Net::fixed)
        .def_readwrite("id", &Net::id)
        .def("add_pin", &Net::add_pin)
        .def("__iter__", [](Net &net) {
            return py::make_iterator(net.begin(), net.end());
        }, py::keep_alive<0, 1>());

    py::class_<Pin>(m, "Pin")
        .def_readwrite("name", &Pin::name)
        .def_readwrite("node", &Pin::node)
        .def_readwrite("port", &Pin::port)
        .def_readwrite("x", &Pin::x)
        .def_readwrite("y", &Pin::y);
}

void init_graph(py::module &m) {
    py::enum_<NodeType>(m, "NodeType")
        .value("SwitchBox", NodeType::SwitchBox)
        .value("Port", NodeType::Port)
        .value("Register", NodeType::Register)
        .export_values();

    py::enum_<SwitchBoxSide>(m, "SwitchBoxSide")
        .value("Left", SwitchBoxSide::Left)
        .value("Bottom", SwitchBoxSide::Bottom)
        .value("Right", SwitchBoxSide::Right)
        .value("Top", SwitchBoxSide::Top)
        .export_values();

    py::enum_<SwitchBoxIO>(m, "SwitchBoxIO")
        .value("SB_IN", SwitchBoxIO::SB_IN)
        .value("SB_OUT", SwitchBoxIO::SB_OUT)
        .export_values();

    // the generic node type
    py::class_<Node, std::shared_ptr<Node>> node(m, "Node");
    // init_node_class<Node>(node);
    node.def(py::init<>());

    py::class_<PortNode, std::shared_ptr<PortNode>> p_node(m, "PortNode", node);
    init_node_class<PortNode, std::shared_ptr<PortNode>>(p_node);
    p_node
        .def(py::init<const std::string &, uint32_t, uint32_t, uint32_t>())
        .def(py::init<const std::string &, uint32_t, uint32_t>())
        .def("__eq__", [](const PortNode &n1, const PortNode &n2) {
            return n1.type == n2.type && n1.name == n2.name && n1.x == n2.y &&
                   n1.y == n2.y && n1.width == n2.width &&
                   n1.track == n2.track;
        });

    py::class_<RegisterNode, std::shared_ptr<RegisterNode>>
    r_node(m, "RegisterNode", node);
    init_node_class<RegisterNode, std::shared_ptr<RegisterNode>>(r_node);
    r_node
        .def(py::init<const std::string &, uint32_t, uint32_t, uint32_t,
                      uint32_t>())
        .def("__eq__", [](const RegisterNode &n1, const RegisterNode &n2) {
            return n1.type == n2.type && n1.name == n2.name && n1.x == n2.y &&
                       n1.y == n2.y && n1.width == n2.width &&
                       n1.track == n2.track;
        });

    py::class_<SwitchBoxNode, std::shared_ptr<SwitchBoxNode>>
    sb_node(m, "SwitchBoxNode", node);
    init_node_class<SwitchBoxNode, std::shared_ptr<SwitchBoxNode>>(sb_node);
    sb_node
        .def(py::init<uint32_t, uint32_t, uint32_t, uint32_t, SwitchBoxSide,
                      SwitchBoxIO>())
        .def_readwrite("side", &SwitchBoxNode::side)
        .def_readwrite("io", &SwitchBoxNode::io)
        .def("__eq__", [](const SwitchBoxNode &n1, const SwitchBoxNode &n2) {
            return n1.type == n2.type && n1.name == n2.name && n1.x == n2.y &&
                   n1.y == n2.y && n1.width == n2.width &&
                   n1.track == n2.track && n1.side == n2.side && n1.io == n2.io;
        });

    py::class_<Switch>(m, "Switch")
        .def(py::init<uint32_t, uint32_t, uint32_t, uint32_t, uint32_t,
                      const std::set<std::tuple<uint32_t, SwitchBoxSide,
                                                uint32_t, SwitchBoxSide>> &>())
        .def_readwrite("x", &Switch::x)
        .def_readwrite("y", &Switch::y)
        .def_readwrite("num_track", &Switch::num_track)
        .def_readwrite("id", &Switch::id)
        .def_readwrite("width", &Switch::width)
        .def("internal_wires", &Switch::internal_wires)
        .def("get_sbs_by_side", &Switch::get_sbs_by_side,
             py::return_value_policy::copy)
        .def_readonly_static("SIDES", &Switch::SIDES)
        .def("remove_sb_nodes", &Switch::remove_sb_nodes)
        .def_readonly_static("IOS", &Switch::IOS)
        .def("__getitem__", [](const Switch &s,
                               const std::tuple<SwitchBoxSide,
                                                uint32_t,
                                                SwitchBoxIO> &index) {
            return s[index];
        });

    py::class_<Tile>(m, "Tile")
        .def(py::init<uint32_t, uint32_t, const Switch &>())
        .def(py::init<uint32_t, uint32_t, uint32_t, const Switch &>())
        .def_readwrite("x", &Tile::x)
        .def_readwrite("y", &Tile::y)
        .def_readwrite("height", &Tile::height)
        .def("num_tracks", &Tile::num_tracks)
        .def_readwrite("switchbox", &Tile::switchbox)
        .def_readwrite("registers", &Tile::registers)
        .def_readwrite("ports", &Tile::ports)
        .def("to_string", &Tile::to_string)
        .def("input_ports", [](const Tile &tile) {
            std::set<std::string> result;
            for (auto const &iter : tile.ports) {
                if (!iter.second->get_conn_in().empty()) {
                    if (iter.second->size())
                        throw std::runtime_error(iter.first + " has both in "
                                                              "and out "
                                                              "connection");
                    result.insert(iter.first);
                }
            }
            return result;})
        .def("output_ports", [](const Tile &tile) {
            std::set<std::string> result;
            for (auto const &iter : tile.ports) {
                if (iter.second->size()) {
                    if (!iter.second->get_conn_in().empty())
                        throw std::runtime_error(iter.first + " has both in "
                                                              "and out "
                                                              "connection");
                    result.insert(iter.first);
                }
            }
            return result;})
        .def("__repr__", [](const Tile &t) { return t.to_string(); });

    py::class_<RoutingGraph>(m, "RoutingGraph")
        .def(py::init<>())
        .def(py::init<uint32_t, uint32_t, const Switch &>())
        .def("add_tile", &RoutingGraph::add_tile)
        .def("remove_tile", &RoutingGraph::remove_tile)
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &>(&RoutingGraph::add_edge))
        .def("add_edge",
             py::overload_cast<const Node &,
                               const Node &,
                               uint32_t>(&RoutingGraph::add_edge))

        .def("get_sb", &RoutingGraph::get_sb)
        .def("get_port", &RoutingGraph::get_port)
        .def("has_tile",
             py::overload_cast<const std::pair<uint32_t,
                                               uint32_t>&>
                                               (&RoutingGraph::has_tile))
        .def("has_tile",
             py::overload_cast<uint32_t,
                               uint32_t>(&RoutingGraph::has_tile))
        .def("__getitem__", &RoutingGraph::operator[])
        .def("__iter__", [](RoutingGraph &r) {
            return py::make_key_iterator(r.begin(), r.end());
        }, py::keep_alive<0, 1>())
        .def("get_all_sb", [](RoutingGraph &r) {
            ::vector<SwitchBoxNode*> result;
            for (const auto &iter : r) {
                auto const &switch_ = iter.second.switchbox;
                const auto &top = switch_.get_sbs_by_side(SwitchBoxSide::Top);
                const auto &right =
                        switch_.get_sbs_by_side(SwitchBoxSide::Right);
                auto const &bottom =
                        switch_.get_sbs_by_side(SwitchBoxSide::Bottom);
                auto const &left = switch_.get_sbs_by_side(SwitchBoxSide::Left);
                // merge them into the result
                ::vector<::vector<std::shared_ptr<SwitchBoxNode>>> lists =
                        {top, right, bottom, left};
                for (const auto &lst: lists) {
                    for (auto const &n : lst) {
                        result.emplace_back(n.get());
                    }
                }
            }
            return result;
        }, py::return_value_policy::reference);
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
               py::overload_cast<uint32_t>(&get_opposite_side))
          .def("get_disjoint_sb_wires", &get_disjoint_sb_wires)
          .def("get_wilton_sb_wires", &get_wilton_sb_wires)
          .def("get_imran_sb_wires", &get_imran_sb_wires)
          .def("get_io_value", &get_io_value)
          .def("giv", &get_io_value)
          .def("get_io_int", &get_io_int)
          .def("gii", &get_io_int)
          .def("convert_to_sb", [](const Node *node) -> const SwitchBoxNode* {
              if (node->type != NodeType::SwitchBox)
                  throw std::runtime_error("Node has to be a SwitchBoxNode");
              return dynamic_cast<const SwitchBoxNode*>(node);
          })
          .def("convert_to_port", [](const Node *node) -> const PortNode* {
              if (node->type != NodeType::Port)
                  throw std::runtime_error("Node has to be a SwitchBoxNode");
              return dynamic_cast<const PortNode*>(node);
          })
          .def("convert_to_reg", [](const Node *node) -> const RegisterNode* {
              if (node->type != NodeType::Register)
                  throw std::runtime_error("Node has to be a SwitchBoxNode");
              return dynamic_cast<const RegisterNode*>(node);
          });
}

void init_io(py::module &m) {
    auto io_m = m.def_submodule("io");
    io_m.def("dump_routing_graph", &dump_routing_graph)
        .def("load_routing_graph", &load_routing_graph)
        .def("load_placement", &load_placement)
        .def("load_netlist", &load_netlist)
        .def("dump_routing_result", &dump_routing_result)
        .def("setup_router_input", &setup_router_input);
}

PYBIND11_MODULE(pycyclone, m) {
    m.doc() = "pycyclone";
    init_graph(m);
    init_router(m);
    init_util(m);
    init_io(m);
    init_netlist(m);
}
