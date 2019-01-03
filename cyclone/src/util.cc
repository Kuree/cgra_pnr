#include <cstdlib>
#include "util.hh"

using std::shared_ptr;

std::function<double(const std::shared_ptr<Node> &)>
manhattan_distance(const std::shared_ptr<Node> &end) {
    return [&](const std::shared_ptr<Node> &node) {
        int dx = node->x - end->x;
        int dy = node->y - end->y;

        return static_cast<uint32_t>(abs(dx) + abs(dy));
    };
}

std::function<double(const std::shared_ptr<Node> &)>
manhattan_distance(const std::pair<uint32_t, uint32_t> &end) {
    return [&](const std::shared_ptr<Node> &node) {
        auto [x, y] = end;
        int dx = node->x - x;
        int dy = node->y - y;

        return static_cast<uint32_t>(abs(dx) + abs(dy));
    };
}

uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::shared_ptr<Node> &node2) {
    int dx = node1->x - node2->x;
    int dy = node1->y - node2->y;

    return static_cast<uint32_t>(abs(dx) + abs(dy));
}

uint32_t manhattan_distance(const std::shared_ptr<Node> &node1,
                            const std::pair<uint32_t, uint32_t> &pos) {
    auto [x, y] =pos;
    int dx = node1->x - x;
    int dy = node1->y - y;

    return static_cast<uint32_t>(abs(dx) + abs(dy));
}

uint32_t manhattan_distance(const std::pair<uint32_t, uint32_t> &pos1,
                            const std::pair<uint32_t, uint32_t> &pos2) {
    int dx = pos1.first - pos2.first;
    int dy = pos1.second - pos2.second;

    return static_cast<uint32_t>(abs(dx) + abs(dy));
}

uint32_t zero_cost(const ::shared_ptr<Node> &, const ::shared_ptr<Node> &)
{ return 0; }

uint32_t zero_estimate(const std::shared_ptr<Node> &,
                       const std::shared_ptr<Node> &) { return 0; }

std::function<bool(const std::shared_ptr<Node> &)>
same_loc(const std::pair<uint32_t, uint32_t> &p) {
    return [&](const std::shared_ptr<Node> &node) -> bool {
        if (node == nullptr)
            return false;
        else
            return node->x == p.first && node->y == p.second;
    };;
}

std::function<bool(const std::shared_ptr<Node> &)>
same_loc_reg(const std::pair<uint32_t, uint32_t> &p) {
    return [&](const std::shared_ptr<Node> &node) -> bool {
        if (node == nullptr || node->type != NodeType::Register)
            return false;
        else
            return node->x == p.first && node->y == p.second;
    };;
}

std::function<bool(const std::shared_ptr<Node> &)>
same_node(const std::shared_ptr<Node> &node1) {
    return [&](const ::shared_ptr<Node> &node2) -> bool {
        return node1 == node2;
    };;
}

bool end_reg_f(const std::shared_ptr<Node> &node) {
    if (node == nullptr)
        return false;
    else
        return node->type == NodeType::Register;
}

SwitchBoxSide get_opposite_side(SwitchBoxSide side) {
    auto side_i = static_cast<uint32_t>(side);
    uint32_t new_side = (side_i + 2) % 4;
    return static_cast<SwitchBoxSide>(new_side);
}

std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
get_disjoint_sb_wires(uint32_t num_tracks) {
    std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
    result;
    for (uint32_t track = 0; track < num_tracks; track++) {
        for (uint32_t from = 0; from < Switch::SIDES; from++) {
            for (uint32_t to = 0; to < Switch::SIDES; to++) {
                if (from == to)
                    continue;
                result.insert({track, get_side_int(from),
                               track, get_side_int(to)});
            }
        }
    }
    return result;
}

uint32_t mod(int a, int b) {
    while (a < 0)
        a += b;
    return static_cast<uint32_t>(a % b);
}

std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
get_wilton_sb_wires(uint32_t num_tracks) {
    std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
    result;
    // based on Steven Wilton's PhD thesis
    // http://www.eecg.toronto.edu/~jayar/pubs/theses/Wilton/StevenWilton.pdf
    // page 119, equation 6.1
    auto const W = num_tracks;
    // we define the t_i as
    //    3
    //    _
    // 2 | | 0
    //   |_|
    //    1
    for (uint32_t track = 0; track < num_tracks; track++) {
        // t_0, t_2
        result.insert({track, SwitchBoxSide::Left,
                       track, SwitchBoxSide::Right});
        result.insert({track, SwitchBoxSide::Right,
                       track, SwitchBoxSide::Left});
        // t_1, t_3
        result.insert({track, SwitchBoxSide::Bottom,
                       track, SwitchBoxSide::Top});
        result.insert({track, SwitchBoxSide::Top,
                       track, SwitchBoxSide::Bottom});
        // t_0, t_1
        result.insert({track, SwitchBoxSide::Left,
                       mod(W - track, W), SwitchBoxSide::Bottom});
        result.insert({mod(W - track, W), SwitchBoxSide::Bottom,
                       track, SwitchBoxSide::Left});
        // t_1, t_2
        result.insert({track, SwitchBoxSide::Bottom,
                       mod(track + 1, W), SwitchBoxSide::Right});
        result.insert({mod(track + 1, W), SwitchBoxSide::Right,
                       track, SwitchBoxSide::Bottom});
        // t_2, t_3
        result.insert({track, SwitchBoxSide::Right,
                       mod(2 * W - 2 - track, W), SwitchBoxSide::Top});
        result.insert({mod(2 * W - 2 - track, W), SwitchBoxSide::Top,
                       track, SwitchBoxSide::Right});
        // t3, t_0
        result.insert({track, SwitchBoxSide::Top,
                       mod(track + 1, W), SwitchBoxSide::Left});
        result.insert({mod(track + 1, W), SwitchBoxSide::Left,
                       track, SwitchBoxSide::Top});
    }
    return result;
}

std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
get_imran_sb_wires(uint32_t num_tracks) {
    std::set<std::tuple<uint32_t, SwitchBoxSide, uint32_t, SwitchBoxSide>>
    result;
    // Design of Interconnection Networks for Programmable Logic
    // page 152 Table 7.1
    // we have 6 different functions
    // notice that the table only prescribes half of the connections. we will
    // double the connection by reverse the ordering
    auto const W = num_tracks;
    for (uint32_t track = 0; track < num_tracks; track++) {
        // f_e1
        result.insert({track, SwitchBoxSide::Left,
                       mod(W - track, W), SwitchBoxSide ::Top});
        result.insert({mod(W - track, W), SwitchBoxSide ::Top,
                       track, SwitchBoxSide::Left});
        // f_e2
        result.insert({track, SwitchBoxSide::Top,
                       mod(track + 1, W), SwitchBoxSide::Right});
        result.insert({mod(track + 1, W), SwitchBoxSide::Right,
                       track, SwitchBoxSide::Top});
        // f_e3
        result.insert({track, SwitchBoxSide::Bottom,
                       mod(W -track - 2, W), SwitchBoxSide::Right});
        result.insert({mod(W -track - 2, W), SwitchBoxSide::Right,
                       track, SwitchBoxSide::Bottom});
        // f_e4
        result.insert({track, SwitchBoxSide::Left,
                       mod(track - 1, W), SwitchBoxSide::Bottom});
        result.insert({mod(track - 1, W), SwitchBoxSide::Bottom,
                       track, SwitchBoxSide::Left});
        // f_e5
        result.insert({track, SwitchBoxSide::Left,
                       track, SwitchBoxSide::Right});
        result.insert({track, SwitchBoxSide::Right,
                       track, SwitchBoxSide::Left});
        // f_e6
        result.insert({track, SwitchBoxSide::Bottom,
                       track, SwitchBoxSide::Top});
        result.insert({track, SwitchBoxSide::Top,
                       track, SwitchBoxSide::Bottom});
    }
    return result;
}
