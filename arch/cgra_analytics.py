from .graph import get_raw_connections
from .graph import build_raw_graph
from .cgra import load_packed_file, read_netlist_json
from .cgra import get_tile_op
import networkx as nx
import six


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


def deepcopy(obj_to_copy):
    if isinstance(obj_to_copy, dict):
        d = obj_to_copy.copy()  # shallow dict copy
        for k, v in six.iteritems(d):
            d[k] = deepcopy(v)
    elif isinstance(obj_to_copy, list):
        d = obj_to_copy[:]  # shallow list/tuple copy
        i = len(d)
        while i:
            i -= 1
            d[i] = deepcopy(d[i])
    elif isinstance(obj_to_copy, set):
        d = obj_to_copy.copy()
    else:
        # tuple is fine since we're not modifying tuples
        d = obj_to_copy
    return d


def find_all_timed_path(g, name_to_id, id_to_name, changed_pe):
    nodes = g.nodes()
    timed_elements = set()

    for node in nodes:
        if ("reg" in node or "mem" in node or "io" in node) and \
           ("lut" not in node and "cnst" not in node and
           name_to_id[node][0] != "b"):
            timed_elements.add(node)
    # in case of reg folding
    for node in changed_pe:
        timed_elements.add(id_to_name[node])

    def find_path(start_node):
        """recursive function to get all path starting from the start_node"""
        result = []
        nei = list(nx.neighbors(g, start_node))
        for n in nei:
            if n in timed_elements:
                result.append([start_node, n])
            else:
                r = find_path(n)
                for nn in r:
                    result.append([start_node] + nn)
        return result

    paths = []
    for node in timed_elements:
        path = find_path(node)
        for node_path in path:
            if len(node_path) > 1:
                paths.append(node_path)

    return paths


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


def calculate_delay(net_path, route_result, placement, netlists, id_to_name,
                    instances, changed_pe):
    # result entry setup
    result = {}
    for entry in TIMING_INFO:
        result[entry] = 0

    def find_net_entry(n, p, p_port):
        for blk_id, blk_port in n:
            blk_pos = placement[blk_id]
            if blk_pos == p and p_port == blk_port:
                return blk_id, p_port
        raise Exception("Unable to find " + str((p, p_port)))

    for i in range(len(net_path) - 1):
        src_id, net_id = net_path[i]
        dst_id, _ = net_path[i + 1]
        src_pos = placement[src_id]
        end_pos = placement[dst_id]

        path_result = {}
        link = {}

        def add_time(p_pos, conn_type, time):
            if p_pos not in path_result:
                path_result[p_pos] = {}
                for e in TIMING_INFO:
                    path_result[p_pos][e] = 0
            if len(conn_type) > 0:
                path_result[p_pos][conn_type] += time

        net = netlists[net_id][:]
        path = route_result[net_id][:]
        src_entry = path.pop(0)
        assert (src_entry[0] == "src")
        src_id, src_port = net.pop(0)
        if src_port == "reg":
            add_time(src_pos, "reg", TIMING_INFO["reg"])
        else:
            src_name = id_to_name[src_id]
            # FIXME
            if "mul" == src_name[:3]:
                op = "mul"
            else:
                op, _ = get_tile_op(instances[src_name], src_id, changed_pe,
                                    rename_op=False)
            if op is not None:
                add_time(src_pos, op, TIMING_INFO[op])
            else:
                add_time(src_pos, "", 0)
        pre_pos = src_pos
        # traverse through the net
        for path_entry in path:
            if path_entry[0] == "link":
                current_pos = path_entry[0][0]
                if current_pos in link:
                    pre_pos = current_pos
                    continue
                else:
                    add_time(current_pos, "sb", TIMING_INFO["sb"])
                    link[current_pos] = pre_pos
                    pre_pos = current_pos
            else:
                if path_entry[0] != "sink":
                    assert (path_entry[0] == "src")
                    pre_pos = src_pos
                    continue
                if len(path_entry) == 3:
                    _, _, (pos, port) = path_entry
                    dst_id, dst_port = find_net_entry(net, pos, port)
                    dst_pos = placement[dst_id]
                    assert (dst_port == port and dst_pos == pos)
                    net.remove((dst_id, dst_port))
                    if pos not in link:
                        link[pos] = pre_pos
                    pre_pos = pos
                    add_time(pos, "sb", TIMING_INFO["sb"])
                    if pos == end_pos:
                        add_time(pos, "cb", TIMING_INFO["cb"])
                        break
                else:
                    assert len(path_entry) == 4
                    pos, port = path_entry[-1]
                    dst_id, dst_port = find_net_entry(net, pos, port)
                    dst_pos = placement[dst_id]
                    assert (dst_pos == pos and dst_port == port)
                    net.remove((dst_id, dst_port))
                    if pos not in link:
                        link[pos] = pre_pos
                    pre_pos = pos
                    add_time(pos, "sb", TIMING_INFO["sb"])
                    if pos == end_pos:
                        break
        # reconstruct the path to compute the delay
        current_pos = end_pos
        while current_pos in link:
            for entry in path_result[current_pos]:
                result[entry] += path_result[current_pos][entry]
            current_pos = link[current_pos]
        assert current_pos == src_pos
        for entry in path_result[current_pos]:
            result[entry] += path_result[current_pos][entry]

    total_time = sum([result[x] for x in result])
    return total_time, result


def find_critical_path_delay(netlist_json, packed_file, route_result,
                             placement):
    connections, instances = read_netlist_json(netlist_json)
    netlists, folded_blocks, id_to_name, changed_pe = \
        load_packed_file(packed_file)

    name_to_id = {}
    for blk_id in id_to_name:
        name_to_id[id_to_name[blk_id]] = blk_id

    timed_paths = \
        find_all_timed_path(build_raw_graph(get_raw_connections(netlist_json)),
                            name_to_id, id_to_name, changed_pe)
    delay_paths = convert_timed_path(timed_paths, netlists, folded_blocks,
                                     name_to_id)

    delays = [calculate_delay(net_path, route_result, placement, netlists,
                              id_to_name, instances, changed_pe)
              for net_path in delay_paths]

    delays.sort(key=lambda x: x[0], reverse=True)

    return delays[0]


def find_latency_path(netlist_json, packed_file):
    raw_connections = get_raw_connections(netlist_json)
    raw_graph = build_raw_graph(raw_connections)
    long_path = nx.dag_longest_path(raw_graph)
    netlists, folded_blocks, id_to_name, _ = load_packed_file(packed_file)

    name_to_id = {}
    for blk_id in id_to_name:
        name_to_id[id_to_name[blk_id].encode("ascii", "ignore")] = blk_id

    blk_ids = []
    for pin in long_path:
        blk_id = name_to_id[pin]
        if (blk_id, "out") in folded_blocks:
            blk_id = folded_blocks[(blk_id, "out")][0]
        blk_ids.append(blk_id)

    net_path = []
    for i in range(0, len(blk_ids) - 1):
        src_id = blk_ids[i]
        dst_id = blk_ids[i + 1]
        if src_id == dst_id:
            # folded case
            continue
        found_id = None
        for net_id in netlists:
            if found_id is not None:
                break
            net = netlists[net_id]
            if net[0][0] == src_id:
                for j in range(1, len(net)):
                    blk_id, _ = net[j]
                    if blk_id == dst_id:
                        found_id = net_id
                        break
        assert found_id is not None
        net_path.append((found_id, src_id, dst_id))

    return net_path


def compute_latency(net_path, route_result, placement):
    total_time = {"alu": 0, "sb": 0, "reg": 0, "mem": 0, "cb": 0}
    for net_id, src_id, dst_id in net_path:
        path = route_result[net_id]
        src_entry = path[0]
        stc_tag, (pos, src_port), _ = src_entry
        if src_port == "out" and src_id[0] != "i":
            total_time["alu"] += TIMING_INFO["alu"]
        elif src_port == "rdata":
            assert src_id[0] == "m"
            total_time["mem"] += TIMING_INFO["mem"]
        assert placement[src_id] == pos
        dst_pos = placement[dst_id]
        found_sink = False
        for i in range(1, len(path)):
            entry = path[i]
            if entry[0] == "link":
                total_time["sb"] += TIMING_INFO["sb"]
            else:
                assert entry[0] == "sink"
                if len(entry) == 4:
                    # one more sb sink (change direction)
                    pos, port = entry[-1]
                    if pos == dst_pos:
                        # we found the sink
                        found_sink = True
                        total_time["sb"] += TIMING_INFO["sb"]
                        total_time["cb"] += TIMING_INFO["cb"]
                        assert (port != "reg")
                        break
                elif len(entry) == 3:
                    # either reg or directly in sink
                    if entry[-1][-1] == "reg":
                        # we passed a switch box
                        total_time["sb"] += TIMING_INFO["sb"]
                        total_time["reg"] += TIMING_INFO["reg"]
                    else:
                        total_time["cb"] += TIMING_INFO["cb"]
                    found_sink = True
                    break
        assert found_sink

    return total_time


def compute_total_wire(routing_result):
    wire_length = {}
    for net_id in routing_result:
        path = routing_result[net_id]
        length = 0
        for entry in path:
            if entry[0] == "link":
                length += 1
            elif entry[0] == "sink":
                if len(entry) == 4:
                    length += 1
        wire_length[net_id] = length
    return wire_length


def compute_area_usage(placement, board_layout):
    result = {}
    for y in range(len(board_layout)):
        for x in range(len(board_layout[0])):
            blk_type = board_layout[y][x]
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
        blk_type = board_layout[y][x]
        result[blk_type][0] += 1
        pos_set.add(pos)
    return result


def compute_routing_usage(routing_result, routing_resource, board_layout):
    route_resource = {}
    for pos in routing_resource:
        route_resource[pos] = routing_resource[pos]["route_resource"]
    unused_route_resource = deepcopy(route_resource)
    for net_id in routing_result:
        path = routing_result[net_id]
        track_in = None
        for path_entry in path:
            if path_entry[0] == "src":
                (pos, _), (track_out, track_in) = path_entry[1:]
                # update left resource
                chans = route_resource[pos]
                conn_to_remove = set()
                for conn_in, conn_out in chans:
                    if conn_out == track_out:
                        conn_to_remove.add((conn_in, conn_out))
                for entry in conn_to_remove:
                    chans.remove(entry)
            elif path_entry[0] == "link":
                assert (track_in is not None)
                p1, p2 = path_entry[1]
                conn_out, conn_in = path_entry[2]
                chans = route_resource[p1]
                conn_to_remove = set()
                for c_in, c_out in chans:
                    if track_in == c_in:
                        conn_to_remove.add((c_in, c_out))
                for entry in conn_to_remove:
                    chans.remove(entry)
                chans = route_resource[p2]
                conn_to_remove = set()
                for c_in, c_out in chans:
                    if conn_out == c_out:
                        conn_to_remove.add((c_in, c_out))
                for entry in conn_to_remove:
                    chans.remove(entry)
                track_in = conn_in
            elif path_entry[0] == "sink":
                if len(path_entry) == 3:
                    _, conn_in, (pos, _) = path_entry
                    chans = route_resource[pos]
                    conn_to_remove = set()
                    for c_in, c_out in chans:
                        if conn_in == c_in:
                            conn_to_remove.add((c_in, c_out))
                    for entry in conn_to_remove:
                        chans.remove(entry)
                    track_in = conn_in
                else:
                    link_entry = path_entry[1]
                    (pos, _), (conn_in, conn_out) = link_entry
                    chans = route_resource[pos]
                    conn_to_remove = set()
                    for c_in, c_out in chans:
                        if conn_in == c_in:
                            conn_to_remove.add((c_in, c_out))
                        if conn_out == c_out:
                            conn_to_remove.add((c_in, c_out))
                    for entry in conn_to_remove:
                        chans.remove(entry)

                    track_in = conn_in

    # this is indexed by bus, then track
    resource_usage = {}
    total_bus = set()
    total_chan = set()
    for pos in route_resource:
        x, y = pos
        if board_layout[y][x] == "p" or board_layout[y][x] == "m":
            resource_left = route_resource[(x, y)]
            total_resource = unused_route_resource[(x, y)]
            if len(total_bus) == 0:
                for entry in total_resource:
                    total_bus.add(entry[0][0])
                    total_chan.add(entry[0][-1])
            for bus in total_bus:
                for chan in total_chan:
                    left = 0
                    total = 0
                    for entry in resource_left:
                        if entry[0][0] == bus and entry[0][-1] == chan:
                            left += 1
                    for entry in total_resource:
                        if entry[0][0] == bus and entry[0][-1] == chan:
                            total += 1

                    if bus not in resource_usage:
                        resource_usage[bus] = {}
                    if chan not in resource_usage[bus]:
                        resource_usage[bus][chan] = set()
                    resource_usage[bus][chan].add((pos, left, total))
    return resource_usage
