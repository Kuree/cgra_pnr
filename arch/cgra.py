from __future__ import print_function
import os
import json
import networkx as nx
import sys
import arch


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


def place_special_blocks(board, blks, board_pos, netlists, place_on_board):
    # put IO in fixed blocks
    # TODO: fix 1bit IO
    io_count = 0
    mem_count = 0

    # find ports
    io_mapping = {}
    for net_id in netlists:
        for blk_id, port in netlists[net_id]:
            if blk_id[0] == "i":
                if port == "in":     # this is an output port
                    io_mapping[blk_id] = False
                elif port == "out":
                    io_mapping[blk_id] = True
                else:
                    raise Exception("Unknown port: " + port + " for IO: " +
                                    blk_id)

    input_io_locations = [(1, 2), (2, 1)]
    output_io_locations = [(18, 2), (2, 18)]

    for blk_id in blks:
        if blk_id[0] == "i":
            is_input = io_mapping[blk_id]
            if is_input:
                pos = input_io_locations.pop(0)
            else:
                pos = output_io_locations.pop(0)
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
            io_count += 1
        elif blk_id[0] == "m":
            # just evenly distributed
            x = 5 + (mem_count % 3) * 4
            y = 2 + (mem_count // 3) * 4
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
    return netlists, g, dont_care, id_to_name, raw_netlists


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

        def sort_value(key):
            raw_splits = key.split(".")
            if "in" in raw_splits:
                return 2
            elif "out" in raw_splits:
                return 0
            else:
                return 1
        # rearrange the net so that it's src -> sink
        net.sort(key=lambda p: sort_value(p))
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
            # TODO: stupid 1 bit IO thing need to take care of
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
                blk_type = "p"
                print("INFO: change", name, "to a PE tile")
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
    for conn in connections:
        edge_id = "e" + str(h_edge_count)
        h_edge_count += 1
        hyper_edge = []
        for idx, v in enumerate(conn):
            raw_names = v.split(".")
            blk_name = raw_names[0]
            port = ".".join(raw_names[1:])
            # FIXME
            if port == "ren" or port == "cg_en":
                continue
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
                id2 = name_to_id[name2]
                if name2 not in dont_care and id2[0] != "m":
                    # reg cannot be put into memory
                    dont_care[blk_name] = name2
                    print("Absorb", blk_name, "into", dont_care[blk_name])
                else:
                    raise Exception("Unknown state for blk " + blk_name)
        if len(hyper_edge) > 1:
            netlists[edge_id] = hyper_edge
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


def save_routing_result(routing_result, output_file):
    with open(output_file, "w+") as f:
        json.dump(routing_result, f)


def parse_routing_result(routing_file):
    with open(routing_file) as f:
        return json.load(f)


def compute_direction(src, dst):
    """ right -> 0 bottom -> 1 left -> 2 top -> 3 """
    assert (src != dst)
    x1, y1 = src
    x2, y2 = dst
    assert ((abs(x1 - x2) == 0 and abs(y1 - y2) == 1) or (abs(x1 - x2) == 1
                                                          and abs(y1 - y2)
                                                          == 0))

    if x1 == x2:
        if y2 > y1:
            return 1
        else:
            return 3
    if y1 == y2:
        if x2 > x1:
            return 0
        else:
            return 2
    raise Exception("direction error " + "{}->{}".format(src, dst))


def mem_tile_fix(board_meta, from_pos, to_pos):
    # this is just for the memory sides
    # will remove the logic once they change the memory tile to 1x1
    tile_mapping = board_meta[-1]
    side1 = compute_direction(from_pos, to_pos)
    side2 = compute_direction(to_pos, from_pos)
    # add an offset if it's the bottom of a memory tile

    if from_pos not in tile_mapping:
        # MEM tile?
        side1 += 4
        tile1 = tile_mapping[from_pos[0], from_pos[1] - 1]
    else:
        tile1 = tile_mapping[from_pos]
    if to_pos not in tile_mapping:
        side2 += 4
        tile2 = tile_mapping[to_pos[0], to_pos[1] - 1]
    else:
        tile2 = tile_mapping[to_pos]
    return side1, side2, tile1, tile2


def generate_bitstream(board_filename, netlist_filename, placement_filename,
                       routing_filename, output_filename):
    connections, instances = read_netlist_json(netlist_filename)
    dont_care, g, id_to_name, netlists = pack_netlists(connections, instances)
    board_meta = arch.parse_cgra(board_filename, True)["CGRA"]
    placement, _ = parse_placement(placement_filename)
    route_result = parse_routing_result(routing_filename)
    tile_mapping = board_meta[-1]

    output_string = ""

    # TODO: refactor this
    name_to_id = {}
    for blk_id in id_to_name:
        name_to_id[id_to_name[blk_id]] = blk_id

    # build PE tiles types
    pe_tiles = {}
    # keep track of whether it's 1-bit or 16-bit
    # really stupid design in my opinion
    pos_track_mode = {}
    type_str = "mpi"
    for name in instances:
        instance = instances[name]
        blk_id = name_to_id[name]
        if blk_id not in g.nodes():
            continue    # we have packed these instances
        blk_id = name_to_id[name]
        # it has to be a PE tile
        assert(blk_id[0] in type_str)
        pos = placement[blk_id]
        tile = tile_mapping[pos]

        # find out the PE type
        # TODO: Fix reg only PE tiles
        tile_sig = get_tile_signature(blk_id, connections,
                                      id_to_name, instance, name,
                                      name_to_id, placement, pos,
                                      pos_track_mode)
        if tile_sig is None:
            continue
        else:
            op, pins, print_order = tile_sig
            pe_tiles[blk_id] = (tile, op, pins, print_order)

    tab = "\t" * 6
    # generate tile mapping
    # sort them for pretty printing
    pe_keys = list(pe_tiles.keys())
    pe_keys.sort(key=lambda x: pe_tiles[x][-1])
    output_string += "# PLACEMENT\n"
    for blk_id in pe_keys:
        tile, op, pins, _ = pe_tiles[blk_id]
        if op == "mem":
            output_string += "T{}_{}_{}{}#{}\n".format(tile, op, pins,
                                                       tab,
                                                       id_to_name[blk_id])
        elif op == "nop":
            # reg tiles, no output
            continue
        else:
            output_string += "T{}_{}({}){}# {}\n".format(tile, op,
                                                         ",".join(pins),
                                                         tab,
                                                         id_to_name[blk_id])

    # one pass to convert from pos_track_mode -> net_track_mode
    net_track_mode = get_net_track_mode(netlists, placement, pos_track_mode)

    # write routing
    output_string += "\n#ROUTING\n"
    for net_id in route_result:
        track, path = route_result[net_id]
        output_string += "\n# net id: {}\n".format(net_id)
        netlist = netlists[net_id]
        pin_pos = {}
        for blk_id, port, in netlist:
            pos = placement[blk_id]
            pin_pos[pos] = (blk_id, port)
        # NOTE: in a netlist, a single src can drive multiple sinks
        # also because of the strict format that bsbuilder is assuming
        # input IO will not be outputted.
        track_mode = net_track_mode[net_id]
        assert(track_mode in [1, 16])
        track_str = "" if track_mode == 16 else "b"
        for i in range(len(path) - 1):
            # get operand
            current_pos = tuple(path[i])
            to_pos = tuple(path[i + 1])

            if current_pos in pin_pos:
                blk_id, port = pin_pos[current_pos]
                if blk_id[0] == "i":
                    # IO is a special case
                    # merely passing through
                    continue
                side1, _, tile1, _ = mem_tile_fix(board_meta,
                                                  current_pos,
                                                  to_pos)
                if "reg" in id_to_name[blk_id] and i != 0:
                    pre_pos = tuple(path[i - 1])
                    side2, _, _, _ = mem_tile_fix(board_meta, current_pos,
                                                  pre_pos)
                    output_string +=\
                        "T{1}_in_s{2}t{0}{4} -> T{1}_out_s{3}t{0}{4} (r)\n".format(track,
                                                                                   tile1,
                                                                                   side2,
                                                                                   side1,
                                                                                   track_str)
                    continue
                elif "out" in port:
                    # we have a PE output
                    output_string +=\
                        "T{1}_pe_out{3} -> T{1}_out_s{2}t{0}{3}\n".format(
                            track, tile1, side1, track_str)
                    continue    # we're done here
                elif "rdata" == port:
                    # memory out
                    output_string += \
                        "T{1}_mem_out{3} -> T{1}_out_s{2}t{0}{3}\n".format(
                            track, tile1, side1, track_str)
                else:
                    # it's a sink
                    assert(i != 0)
                    pre_pos = tuple(path[i - 1])
                    output_string = process_sink(board_meta, id_to_name, track,
                                                 pin_pos,
                                                 current_pos,
                                                 pre_pos, track_str,
                                                 output_string)
            else:
                # merely passing through
                output_string = connect_tiles(board_meta, i, path, track,
                                              track_str, track_str,
                                              output_string)

        # last position
        # still need to careful about the next tile though
        # as it could be an operand
        current_pos = tuple(path[-1])
        pre_pos = tuple(path[-2])
        assert(current_pos in pin_pos)
        output_string = process_sink(board_meta, id_to_name, track, pin_pos,
                                     current_pos, pre_pos, track_str,
                                     output_string)

    with open(output_filename, "w+") as f:
        f.write(output_string)


def get_net_track_mode(netlists, placement, pos_track_mode):
    net_track_mode = {}
    for net_id in netlists:
        for blk_id, _ in netlists[net_id]:
            pos = placement[blk_id]
            # if any pin in the net is a bit mode, everything in in bit mode
            if pos in pos_track_mode:
                if net_id not in net_track_mode:
                    net_track_mode[net_id] = pos_track_mode[pos]
                else:
                    if pos_track_mode[pos] == 1:
                        net_track_mode[net_id] = pos_track_mode[pos]
    return net_track_mode


def get_tile_signature(blk_id, connections, id_to_name, instance, name,
                       name_to_id, placement, pos, pos_track_mode):
    pe_type = instance["genref"]
    if pe_type == "coreir.reg":
        # reg tile, reg in and reg out
        op = "nop"
        pins = ("reg", "reg")
        print_order = 10
        pos_track_mode[pos] = 16
    elif pe_type == "cgralib.Mem":
        op = "mem"
        pins = int(instance["modargs"]["depth"][-1])
        print_order = 2
    elif pe_type == "cgralib.IO":
        return None    # don't care yet
    else:
        op = instance["genargs"]["op_kind"][-1]
        if op == "bit":
            # 1-bit line
            pos_track_mode[pos] = 1
            # and we have something called lut55 and lut88...
            lut_type = instance["modargs"]["lut_value"][-1][3:]
            if lut_type == "55":
                op = "lut55"
                print_order = 0
                pins = ["wire", "wire", "wire"]
                get_tile_pin_list(blk_id, connections, id_to_name, name,
                                  name_to_id,
                                  pins, placement, pos)
                pass
            elif lut_type == "88":
                op = "lut88"
                print_order = 0
                pins = ["wire", "wire", "wire"]
                get_tile_pin_list(blk_id, connections, id_to_name, name,
                                  name_to_id,
                                  pins, placement, pos)
            else:
                op = "lutFF"
                pins = ("const0", "const0", "const0")
                print_order = 3
        elif op == "alu" or op == "combined":
            pos_track_mode[pos] = 16
            if "alu_op_debug" in instance["modargs"]:
                op = instance["modargs"]["alu_op_debug"][-1]
            else:
                op = instance["modargs"]["alu_op"][-1]
            print_order = 0

            # TODO: fix this exhaustive search
            # find all placements to see what else got placed on the same
            # tile
            pins = ["wire", "wire"]
            get_tile_pin_list(blk_id, connections, id_to_name, name, name_to_id,
                              pins, placement, pos)

        else:
            raise Exception("Unknown PE op type " + op)
    return op, pins, print_order


def get_tile_pin_list(blk_id, connections, id_to_name, name, name_to_id, pins,
                      placement, pos):
    """update the pins you give"""
    pin_list = set()
    for b_id in placement:
        if placement[b_id] == pos and b_id != blk_id:
            pin_list.add(id_to_name[b_id])
    for pin in pin_list:
        # search for the entire connections to figure the pin
        # connection order
        for conn in connections:
            if pin in conn[0] and name in conn[1]:
                index = int(conn[1].split(".")[-1])
                pin_type = name_to_id[pin][0]
                if pin_type == "r":
                    pins[index] = "reg"
                elif pin_type == "c":
                    pins[index] = pin
                elif pin_type == "b":
                    # FIXME
                    pins[index] = "const0_0"
                else:
                    raise Exception("Unknown pin type " + pin)
                break
            elif pin in conn[1] and name in conn[0]:
                index = int(conn[0].split(".")[-1])
                pin_type = name_to_id[pin][0]
                if pin_type == "r":
                    pins[index] = "reg"
                elif pin_type == "c":
                    pins[index] = pin
                else:
                    raise Exception("Unknown pin type " + pin)
                break


def connect_tiles(board_meta, i, path, track, track_str1,
                  track_str2, output_string):
    current_pos = tuple(path[i])
    if i == 0:  # might be a reg
        next_pos = tuple(path[i + 1])
        _, side1, _, tile1 = mem_tile_fix(board_meta,
                                          next_pos,
                                          current_pos)
    else:
        pre_pos = tuple(path[i - 1])
        side1, _, tile1, _ = mem_tile_fix(board_meta,
                                          current_pos,
                                          pre_pos)
    to_pos = tuple(path[i + 1])
    side2, _, _, _ = mem_tile_fix(board_meta,
                                  current_pos,
                                  to_pos)
    output_string += \
        "T{1}_in_s{2}t{0}{4} -> T{1}_out_s{3}t{0}{5}\n".format(
            track, tile1, side1, side2, track_str1, track_str2)
    return output_string


def process_sink(board_meta, id_to_name, track, pin_pos, current_pos, pre_pos,
                 track_str, output_string):
    blk_id, port = pin_pos[current_pos]
    side1, _, tile1, _ = mem_tile_fix(board_meta,
                                      current_pos,
                                      pre_pos)

    # it has to be sink
    # TODO: change this to be architecture specific
    if "in" in port or "wdata":
        # figure out which operand to use
        if port == "data.in.0":
            operand = "op1"
            side = 2
        elif port == "data.in.1":
            operand = "op2"
            side = 1
        elif port == "in":
            # we have a IO, or a reg
            name = id_to_name[blk_id]
            if "reg" in name:
                # it's a reg
                track_str1 = track_str
                track_str2 = track_str + " (r)"
                # FIXME:
                # for now always put register on s1 or s0
                # once we have a packer, we need to change this
                side2 = 2 if side1 != 2 else 1
                output_string += \
                    "T{1}_in_s{2}t{0}{4} -> T{1}_out_s{3}t{0}{5}\n".format(
                        track, tile1, side1, side2, track_str1, track_str2)
                return output_string
            else:
                return output_string
        elif port == "bit.in.0":
            operand = "bit0"
            side = 2
        elif port == "bit.in.1":
            operand = "bit1"
            side = 1
        elif port == "wdata":
            operand = "mem_in"
            side = 2
        elif port == "ren":
            operand = "ren"
            side = 1
        elif port == "wen":
            operand = "wen"
            side = 2
        elif port == "cg_en":
            operand = "cg_en"
            side = 1
        else:
            raise Exception("Unknown port " + port)
        output_string += \
            "T{1}_in_s{2}t{0}{4} -> T{1}_{3}\n".format(track,
                                                       tile1,
                                                       side,
                                                       operand,
                                                       track_str)
    else:
        raise Exception("blk " + blk_id + " is not a sink")
    return output_string





