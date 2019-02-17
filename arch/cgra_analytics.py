# FIXME
# random numbers
TIMING_INFO = {
    "sb": 50,
    "cb": 0,
    "alu": 200,
    "mul": 1000,
    "mem": 1000,
    "reg": 0
}


def convert_timed_path(timed_paths, netlists, folded_blocks, name_to_id):
    # building indexes
    blk_to_net = {}
    for net_id in netlists:
        blk_id, blk_port = netlists[net_id][0]
        if blk_port in ["out", "outb", "rdata", "reg"]:
            blk_to_net[blk_id] = net_id

    result = []
    for path in timed_paths:
        path_entry = []
        for index, entry_name in enumerate(path):
            blk_id = name_to_id[entry_name]
            if (blk_id, "out") in folded_blocks:
                blk_id = folded_blocks[(blk_id, "out")][0]
            if blk_id not in blk_to_net:
                assert (blk_id[0] == "i") and index == len(path) - 1
                path_entry.append((blk_id, None))
            else:
                net_id = blk_to_net[blk_id]
                # the last one is the end
                path_entry.append((blk_id, net_id))

        result.append(path_entry)

    return result


def compute_total_wire(routing_result):
    wire_length = {}
    for net_id in routing_result:
        path = routing_result[net_id]
        length = 0
        visited_sb = set()
        for segment in path:
            for i in range(len(segment) - 1):
                if tuple(segment[i]) in visited_sb:
                    continue
                if segment[i][0] == "SB" and segment[i + 1][0] == "SB":
                    # also make sure it's connecting to a different
                    # tile. also make sure it's not in visited_sb
                    if segment[i][1] != segment[i + 1][1] or \
                        segment[i][2] != segment[i + 1][2] or \
                            segment[i][3] != segment[i + 1][3]:
                        length += 1

                    visited_sb.add(tuple(segment[i]))

        wire_length[net_id] = max(length, 1)
    return wire_length


def compute_area_usage(placement, board_layout):
    result = {}
    height = board_layout.height()
    width = board_layout.width()
    for y in range(height):
        for x in range(width):
            blk_type = board_layout.get_blk_type(x, y)
            if blk_type is None:
                continue
            if blk_type not in result:
                result[blk_type] = [0, 0]
            result[blk_type][-1] += 1
    pos_set = set()
    for blk_id in placement:
        pos = placement[blk_id]
        if pos in pos_set:
            continue
        x, y = pos
        blk_type = board_layout.get_blk_type(x, y)
        result[blk_type][0] += 1
        pos_set.add(pos)
    # remove entries
    if " " in result:
        result.pop(" ")
    if "i" in result:
        result.pop("i")
    return result


def compute_routing_usage(routing_result, routing_resource):
    route_resource = {}
    for pos in routing_resource:
        route_resource[pos] = routing_resource[pos]["route_resource"]

    # construct all the available switch boxes, by bus, and then tracks
    total_resource = {}
    for tile in route_resource:
        resource = route_resource[tile]
        for conn1, conn2 in resource:
            conns = [conn1, conn2]
            for width, io, side, track in conns:
                if width not in total_resource:
                    total_resource[width] = {}
                if track not in total_resource[width]:
                    total_resource[width][track] = set()
                total_resource[width][track].add((tile, io, side))

    total_resource_count = {}
    for bus in total_resource:
        total_resource_count[bus] = {}
        for track in total_resource[bus]:
            total_resource_count[bus][track] = len(total_resource[bus][track])

    for net_id in routing_result:
        path = routing_result[net_id]
        for segments in path:
            for seg in segments:
                if seg[0] == "SB":
                    track, x, y, side, io, bus = seg[1:]
                    entry = ((x, y), io, side)
                    if entry in total_resource[bus][track]:
                        total_resource[bus][track].remove(entry)

    resource_usage = {}
    for bus in total_resource_count:
        resource_usage[bus] = {}
        for track in total_resource_count[bus]:
            resource_usage[bus][track] = (total_resource_count[bus][track],
                                          len(total_resource[bus][track]))

    return resource_usage
