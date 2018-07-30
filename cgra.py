from __future__ import print_function
import os
import json
import networkx as nx
import sys


def save_placement(board_pos, id_to_name, dont_care, place_file):
    blk_keys = list(board_pos.keys())
    blk_keys.sort(key=lambda b: int(b[1:]))
    with open(place_file, "w+") as f:
        header = "{0}\t\t\t{1}\t{2}\t\t#{3}\n".format("Block Name",
                                                      "X",
                                                      "Y",
                                                      "Block ID")
        f.write(header)
        f.write("-" * len(header) + "\n")
        name_to_id = {}
        for blk_id in blk_keys:
            x, y = board_pos[blk_id]
            f.write("{0}\t\t{1}\t{2}\t\t#{3}\n".format(id_to_name[blk_id],
                                                          x,
                                                          y,
                                                          blk_id))
        # reverse the index
        for blk_id in id_to_name:
            name_to_id[id_to_name[blk_id]] = blk_id

        # write out absorbed components
        for blk_name in dont_care:
            connected_name = dont_care[blk_name]
            assert(connected_name is not None)
            connected_id = name_to_id[connected_name]
            x, y = board_pos[connected_id]
            blk_id = name_to_id[blk_name]
            f.write("{0}\t\t{1}\t{2}\t\t#{3}\n".format(blk_name,
                                                       x,
                                                       y,
                                                       blk_id))


def parse_placement(placement_file):
    with open(placement_file) as f:
        lines = f.readlines()
    lines = lines[2:]
    placement = {}
    id_to_name = {}
    for line in lines:
        raw_line = line.split()
        assert(len(raw_line) == 4)
        blk_name = raw_line[0]
        x = int(raw_line[1])
        y = int(raw_line[2])
        blk_id = raw_line[-1][1:]
        placement[blk_id] = (x, y)
        id_to_name[blk_id] = blk_name
    return placement, id_to_name


def place_special_blocks(board, blks, board_pos, place_on_board):
    # place io in the middle of each sides
    io_count = 0
    mem_count = 0
    io_start = len(board[0]) // 2 - 1
    for blk_id in blks:
        if blk_id[0] == "i":
            if io_count % 4 == 0:
                if io_count % 8 == 0:
                    x = io_start - io_count // 8
                else:
                    x = io_start + io_count // 8 + 1
                y = 0
            elif io_count % 4 == 1:
                tap = io_count - 1
                if tap % 8 == 0:
                    x = io_start - tap // 8
                else:
                    x = io_start + tap // 8 + 1
                y = len(board) - 1
            elif io_count % 4 == 2:
                tap = io_count - 2
                if tap % 8 == 0:
                    y = io_start - tap // 8
                else:
                    y = io_start + tap // 8 + 1
                x = 0
            else:
                tap = io_count - 3
                if tap % 8 == 0:
                    y = io_start - tap // 8
                else:
                    y = io_start + tap // 8 + 1
                x = len(board[0]) - 1
            pos = (x, y)
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
            io_count += 1
        elif blk_id[0] == "m":
            # just evenly distributed
            x = 5 + (mem_count % 4) * 4
            y = 4 + (mem_count // 4) * 4
            pos = (x, y)
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
            mem_count += 1
        else:
            raise Exception("Unknown block type", blk_id)

def parse_connection(netlist_filename):
    # just parse the connection without verifying
    connections, instances = read_netlist_json(netlist_filename)
    _, g, id_to_name, netlists = pack_netlists(connections,
                                               instances)
    return g, id_to_name, netlists


def parse_netlist(netlist_filename):
    """parse the netlist. also perform simple "packing" while reading out
       connections.
    """
    connections, instances = read_netlist_json(netlist_filename)
    dont_care, g, id_to_name, raw_netlists = pack_netlists(connections,
                                                           instances)
    netlists = {}
    for net_id in raw_netlists:
        hyper_edge = raw_netlists[net_id]
        netlists[net_id] = [e[0] for e in hyper_edge]
    return netlists, g, dont_care, id_to_name


def convert2netlist(connections):
    netlists = []
    skip_index = set()
    for i in range(len(connections)):
        if i in skip_index:
            continue
        conn = connections[i]
        assert(len(conn) == 2)
        # brute force search
        net = [conn[0], conn[1]]
        for j in range(len(connections)):
            if i == j:
                continue
            conn0 = connections[j][0]
            conn1 = connections[j][1]

            if conn0 in net and conn1 not in net:
                net.append(conn1)
                skip_index.add(j)
            if conn1 in net and conn0 not in net:
                skip_index.add(j)
                net.append(conn0)
        netlists.append(net)
    print("INFO: before conversion connections", len(connections),
          "after conversion netlists:", len(netlists))
    return netlists


def pack_netlists(connections, instances):
    name_to_id = {}
    id_count = 0
    # don't care list
    dont_care = {}
    # things we actually care in creating connection graph
    care_set = set()
    care_types = "pim"
    for name in instances:
        attrs = instances[name]
        if "genref" not in attrs:
            assert ("modref" in attrs)
            assert (attrs["modref"] == u"corebit.const")
            dont_care[name] = None
            blk_type = "b"
        else:
            instance_type = attrs["genref"]
            if instance_type == "cgralib.PE":
                blk_type = "p"
            elif instance_type == "cgralib.IO":
                blk_type = "i"
            elif instance_type == "cgralib.Mem":
                blk_type = "m"
            elif instance_type == "coreir.const":
                dont_care[name] = None
                blk_type = "c"
            elif instance_type == "coreir.reg":
                dont_care[name] = None
                blk_type = "r"
            else:
                raise Exception("Unknown instance type", instance_type)
        blk_id = blk_type + str(id_count)
        id_count += 1
        name_to_id[name] = blk_id
        if blk_type in care_types:
            care_set.add(name)
    # read the connections and pack them
    g = nx.Graph()
    netlists = {}
    # hyper edge count
    h_edge_count = 0
    need_to_absorb = set()
    for conn in connections:
        edge_id = "e" + str(h_edge_count)
        h_edge_count += 1
        hyper_edge = []
        for idx, v in enumerate(conn):
            raw_names = v.split(".")
            blk_name = raw_names[0]
            port = ".".join(raw_names[1:])
            if blk_name not in name_to_id:
                raise Exception("cannot find", blk_name, "in instances")
            if blk_name in care_set:
                blk_id = name_to_id[blk_name]
                g.add_edge(edge_id, blk_id)
                hyper_edge.append((blk_id, port))
            elif blk_name in dont_care and dont_care[blk_name] is None:
                # absorb consts and registers
                if idx != 0:
                    v2 = conn[idx - 1]
                elif idx != len(conn) - 1:
                    v2 = conn[idx + 1]
                else:
                    raise Exception("conn only has", conn)
                name2 = v2.split(".")[0]
                if name2 not in dont_care:
                    dont_care[blk_name] = name2
                    print("Absorb", blk_name, "into", dont_care[blk_name])
                    #blk_id = name_to_id[name2]
                    #hyper_edge.append((blk_id, port))
                else:
                    need_to_absorb.add((blk_name, port))
        if len(hyper_edge) > 1:
            netlists[edge_id] = hyper_edge
    # try to absorb again
    for blk_name, port in need_to_absorb:
        if blk_name not in dont_care:
            raise Exception("Failed to absorb " + blk_name)
        print("Absorb", blk_name, "into", dont_care[blk_name])
    # remove the ones that doesn't have connections
    remove_set = set()
    for blk_name in dont_care:
        if dont_care[blk_name] is None:
            print("WARNING: Failed to absorb", blk_name,
                  "\n         Caused by:",
                  "No connection", file=sys.stderr)
            remove_set.add(blk_name)
    for blk_name in remove_set:
        dont_care.pop(blk_name, None)
    for edge in g.edges():
        g[edge[0]][edge[1]]['weight'] = 1
    g = g.to_undirected()
    # reverse it since we need the actual name for placement
    id_to_name = {}
    for b_id in name_to_id:
        id_to_name[name_to_id[b_id]] = b_id

    print("INFO: before packing netlists:", len(connections),
          "after packing netlists:", len(netlists))
    return dont_care, g, id_to_name, netlists


def read_netlist_json(netlist_filename):
    assert (os.path.isfile(netlist_filename))
    with open(netlist_filename) as f:
        raw_data = json.load(f)
    namespace = raw_data["namespaces"]
    design = namespace["global"]["modules"]["DesignTop"]
    instances = design["instances"]
    connections = design["connections"]
    # the standard json input is not a netlist
    connections = convert2netlist(connections)
    return connections, instances
