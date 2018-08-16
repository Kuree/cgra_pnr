from .graph import get_raw_connections
from .graph import build_raw_graph
from .cgra import load_packed_file
import networkx as nx

# FIXME
# random numbers
# don't judge me... I have no idea what I'm doing
TIMING_INFO = {
    "sb": 10,
    "cb": 5,
    "alu": 100,
    "mem": 100,
    "reg": 20
}


def find_critical_path(netlist_json, packed_file):
    raw_connections = get_raw_connections(netlist_json)
    raw_graph = build_raw_graph(raw_connections)
    long_path = nx.dag_longest_path(raw_graph)
    netlists, folded_blocks, id_to_name, _ = load_packed_file(packed_file)

    name_to_id = {}
    for blk_id in id_to_name:
        name_to_id[id_to_name[blk_id]] = blk_id

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


def compute_critical_delay(net_path, route_result, placement):
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


