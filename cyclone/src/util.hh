#ifndef CYCLONE_UTIL_HH
#define CYCLONE_UTIL_HH

#include <functional>
#include "graph.hh"


std::function<double(const std::shared_ptr<Node> &)>
manhattan_distance(const std::shared_ptr<Node> &end);

std::function<double(const std::shared_ptr<Node> &)>
manhattan_distance(const std::pair<uint32_t, uint32_t> &end);

uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::shared_ptr<Node> &node2);

uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::pair<uint32_t, uint32_t> &pos);

uint32_t manhattan_distance(const std::pair<uint32_t, uint32_t> &pos1,
                            const std::pair<uint32_t, uint32_t> &pos2);

uint32_t zero_cost(const std::shared_ptr<Node> &,
                   const std::shared_ptr<Node> &);

uint32_t zero_estimate(const std::shared_ptr<Node> &,
                       const std::shared_ptr<Node> &);


std::function<bool(const std::shared_ptr<Node> &)>
same_loc(const std::pair<uint32_t, uint32_t> &p);

std::function<bool(const std::shared_ptr<Node> &)>
same_loc_reg(const std::pair<uint32_t, uint32_t> &p);

bool end_reg_f(const std::shared_ptr<Node> &node);

std::function<bool(const std::shared_ptr<Node> &)>
same_node(const std::shared_ptr<Node> &node1);

SwitchBoxSide get_opposite_side(SwitchBoxSide side);
inline SwitchBoxSide get_opposite_side(uint32_t side)
{ return get_opposite_side(static_cast<SwitchBoxSide>(side)); }

inline uint32_t get_side_value(SwitchBoxSide s)
{ return static_cast<uint32_t>(s); }

inline SwitchBoxSide get_side_int(uint32_t i)
{ return static_cast<SwitchBoxSide>(i); }

inline uint32_t get_io_value(SwitchBoxIO io)
{ return static_cast<uint32_t>(io); }

inline SwitchBoxIO get_io_int(uint32_t io)
{ return static_cast<SwitchBoxIO>(io); }

std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
get_disjoint_sb_wires(uint32_t num_tracks);

std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
get_wilton_sb_wires(uint32_t num_tracks);

std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
get_imran_sb_wires(uint32_t num_tracks);

#endif //CYCLONE_UTIL_HH
