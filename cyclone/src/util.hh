#ifndef CYCLONE_UTIL_HH
#define CYCLONE_UTIL_HH

#include <functional>
#include "graph.hh"


uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::shared_ptr<Node> &node2);

uint32_t zero_cost(const std::shared_ptr<Node> &,
                   const std::shared_ptr<Node> &);

uint32_t zero_estimate(const std::shared_ptr<Node> &,
                       const std::shared_ptr<Node> &);


std::function<bool(const std::shared_ptr<Node> &)>
same_loc(const std::pair<uint32_t, uint32_t> &p);


bool end_reg_f(const std::shared_ptr<Node> &node);

std::function<bool(const std::shared_ptr<Node> &)>
same_node(const std::shared_ptr<Node> &node1);

SwitchBoxSide get_opposite_side(SwitchBoxSide side);

inline uint32_t get_side_value(SwitchBoxSide s)
{ return static_cast<uint32_t>(s); }

inline SwitchBoxSide get_side_int(uint32_t i)
{ return static_cast<SwitchBoxSide>(i); }

#endif //CYCLONE_UTIL_HH
