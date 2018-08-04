from __future__ import print_function
import json
import arch
from cgra_packer import read_netlist_json, load_packed_file
import networkx as nx
import random
from copy import copy
import pickle


def save_placement(board_pos, id_to_name, folded_blocks, place_file):
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

        for blk_id, port in folded_blocks:
            new_block = folded_blocks[(blk_id, port)][0]
            x, y = board_pos[new_block]
            f.write("{0}\t\t{1}\t{2}\t\t#{3}\n".format(id_to_name[blk_id],
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

    random.seed(0)
    blks = list(blks)
    random.shuffle(blks)

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


def save_routing_result(route_result, route_ports, output_file):
    result = {"route": route_result, "ports": route_ports}
    with open(output_file, "w+") as f:
        pickle.dump(result, f)


def parse_routing_result(routing_file):
    with open(routing_file) as f:
        data = pickle.load(f)
    return data["route"], data["ports"]


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


def generate_bitstream(board_filename, packed_filename, placement_filename,
                       routing_filename, output_filename):
    netlists, folded_blocks, id_to_name, = load_packed_file(packed_filename)
    g = build_graph(netlists)
    board_meta = arch.parse_cgra(board_filename, True)["CGRA"]
    placement, _ = parse_placement(placement_filename)
    route_result, route_ports = parse_routing_result(routing_filename)
    tile_mapping = board_meta[-1]
    # FIXME
    netlist_filename = packed_filename.replace(".packed", ".json")
    connections, instances = read_netlist_json(netlist_filename)

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
    type_str = "mpir"
    for name in instances:
        instance = instances[name]
        blk_id = name_to_id[name]
        if blk_id in folded_blocks:
            continue
        blk_id = name_to_id[name]
        # it might be absorbed already
        if blk_id not in g.nodes():
            continue
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
            raise Exception("TODO")
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
        if len(path) == 0:
            continue
        output_string += "\n# net id: {}\n".format(net_id)
        netlist = netlists[net_id]
        if len(netlist) == 1:
            continue
        for p in netlist:
            output_string += "# {}: {}::{}\n".format(p[0], id_to_name[p[0]],
                                                     p[1])
        route_port = copy(route_ports[net_id])
        # notice that it may overlap
        port_positions = set()
        for (p, _, _) in route_port:
            port_positions.add(p)

        # NOTE: in a netlist, a single src can drive multiple sinks
        # also because of the strict format that bsbuilder is assuming
        # input IO will not be outputted.
        track_mode = net_track_mode[net_id]
        assert(track_mode in [1, 16])
        track_str = "" if track_mode == 16 else "b"
        for i in range(len(path) - 1):
            # get operand
            current_pos = path[i]
            to_pos = path[i + 1]

            if current_pos in port_positions:
                pp, blk_id, port = route_port[0]
                assert(pp == current_pos)
                if blk_id[0] == "i":
                    # IO is a special case
                    # merely passing through
                    route_port.pop(0)
                    continue
                if current_pos == to_pos:
                    # self-connection
                    pre_path_pos = path[i - 1]
                    if pre_path_pos == current_pos:
                        pre_path_pos = path[ i - 2]
                    output_string =\
                        bitstream_handle_self_loop(board_meta, route_port,
                                                   pre_path_pos,
                                                   track, track_str,
                                                   output_string)
                    route_port.pop(0)
                    continue
                side1, _, tile1, _ = mem_tile_fix(board_meta,
                                                  current_pos,
                                                  to_pos)
                if "out" == port:
                    assert(i == 0)
                    # we have a PE output
                    output_string +=\
                        "T{1}_pe_out{3} -> T{1}_out_s{2}t{0}{3}\n".format(
                            track, tile1, side1, track_str)
                    route_port.pop(0)
                    # we're done here
                elif "mem_out" == port:
                    # memory out
                    output_string += \
                        "T{1}_mem_out{3} -> T{1}_out_s{2}t{0}{3}\n".format(
                            track, tile1, side1, track_str)
                    route_port.pop(0)
                else:
                    # it's a sink
                    if i == 0 and "reg" in port:
                        output_string = connect_tiles(board_meta, i, path,
                                                      track,
                                                      track_str, track_str,
                                                      output_string)
                        route_port.pop(0)
                        continue
                    else:
                        assert (i != 0)
                        pre_pos = path[i - 1]

                        # FIXME
                        if pre_pos == current_pos:
                            pre_pos = path[i - 2]

                        output_string = process_sink(board_meta, track,
                                                     route_port,
                                                     current_pos,
                                                     pre_pos, track_str,
                                                     output_string)
                        route_port.pop(0)
            else:
                # merely passing through
                output_string = connect_tiles(board_meta, i, path, track,
                                              track_str, track_str,
                                              output_string)

        # last position
        # still need to careful about the next tile though
        # as it could be an operand
        # be aware of the self-connection!
        if len(path) > 1 and len(route_port) == 1 and path[-1] != path[-2]:
            current_pos = path[-1]
            pre_pos = path[-2]
            assert(current_pos in port_positions)
            output_string = process_sink(board_meta, track, route_port,
                                         current_pos, pre_pos, track_str,
                                         output_string)
        else:
            # handle self_loop
            pre_path_pos = path[-3]
            output_string = bitstream_handle_self_loop(board_meta,
                                                       route_port,
                                                       pre_path_pos,
                                                       track,
                                                       track_str,
                                                       output_string)

    with open(output_filename, "w+") as f:
        f.write(output_string)


def bitstream_handle_self_loop(board_meta,
                               route_port,
                               pre_pos,
                               track,
                               track_str,
                               output_string):
    tile_mapping = board_meta[-1]
    pos, blk_id, port = route_port[0]
    tile = tile_mapping[pos]
    fixed_direction = get_pin_fixed_direction(blk_id, port)
    pre_direction = compute_direction(pos, pre_pos)
    # compute the previous wire coming in (not counting the pin direction fix)

    if "reg" in port:
        track_str2 = track_str + " (r)"
    else:
        track_str2 = track_str
    if pre_direction == fixed_direction:
        output_string += \
            "T{1}_in_s{2}t{0}{4} -> T{1}_{3}{5}\n".format(track,
                                                          tile,
                                                          fixed_direction,
                                                          port,
                                                          track_str,
                                                          track_str2)
    else:
        output_string += \
            "T{1}_in_s{2}t{0}{4} -> T{1}_out_s{3}t{0}{5}\n".format(
                track,
                tile,
                pre_direction,
                fixed_direction,
                track_str,
                track_str2)
        output_string += \
            "T{1}_out_s{2}t{0}{4} -> T{1}_{3}{5}\n".format(track,
                                                       tile,
                                                        fixed_direction,
                                                       port,
                                                       track_str,
                                                       track_str2)
    return output_string


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
        op = "add"
        pins = ("reg", "const0_0")
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


def get_opposite_direction(direction):
    if direction == 0:
        return 2
    elif direction == 1:
        return 3
    elif direction == 2:
        return 0
    elif direction == 3:
        return 0
    else:
        raise Exception("Unknown direction " + str(direction))


def determine_pin_direction(net, placement):
    pin_directions = {}
    allowed_initial_ports = {"data0", "data1", "reg1", "reg2"}
    for index, (blk_id, port) in enumerate(net):
        if index == 0 and port not in allowed_initial_ports:
            # it's a a source
            continue
        pos = placement[blk_id]
        # reg is always put on data0 (op1)
        fixed_direction = get_pin_fixed_direction(blk_id, port)
        if fixed_direction > 0:
            pin_directions[(pos, port)] = fixed_direction


    return pin_directions


def connect_tiles(board_meta, i, path, track, track_str1,
                  track_str2, output_string):
    current_pos = path[i]
    if i == 0:  # might be a reg
        next_pos = path[i + 1]
        _, side1, _, tile1 = mem_tile_fix(board_meta,
                                          next_pos,
                                          current_pos)
    else:
        pre_pos = path[i - 1]
        side1, _, tile1, _ = mem_tile_fix(board_meta,
                                          current_pos,
                                          pre_pos)
    to_pos = path[i + 1]
    side2, _, _, _ = mem_tile_fix(board_meta,
                                  current_pos,
                                  to_pos)
    output_string += \
        "T{1}_in_s{2}t{0}{4} -> T{1}_out_s{3}t{0}{5}\n".format(
            track, tile1, side1, side2, track_str1, track_str2)
    return output_string


def get_pin_fixed_direction(blk_id, port):
    if ("data0" in port) or ("reg0" in port) or (port == "mem_in") or \
            (port == "wen") or (port == "bit0"):
        # this is an operand 0
        # it has to come from the left side
        return 2
    elif "data1" in port or ("reg1" in port) or (port == "bit1"):
        # this is an operand 1
        # it has to come from the bottom side
        return 1
    elif blk_id[0] == "i":
        # IO sink. should be handled already by routing resource
        return -1
    elif blk_id[0] == "r":
        assert port == "reg"
        # in unfolded scheme, reg is always put on the data0/op1
        # use id as a way to reduce routing load
        #num_id = int(blk_id[1:])
        #if num_id % 2 == 0:
        #    return 1
        #else:
        #    return 2
        return 2
    else:
        raise Exception(port)


def process_sink(board_meta, track, route_port, current_pos, pre_pos,
                 track_str, output_string):
    _, blk_id, port = route_port[0]
    _, direction, _, tile = mem_tile_fix(board_meta,
                                         pre_pos,
                                         current_pos)

    # it has to be sink
    # TODO: change this to be architecture specific
    if blk_id[0] == "i":
        # because IO only allows certain flow. we need to be extra careful
        if current_pos == (18, 2):
            if direction != 2:
                path = ((2, 16), (2, 17))
                #output_string = connect_tiles(board_meta, 1, path, track, "",
                #                              "", output_string)
                pass
            # don't care?
        else:
            raise Exception("Not implemented")

        return output_string
    if "reg" in port:
        # it's a reg
        track_str1 = track_str
        track_str2 = track_str + " (r)"
        # maybe a PE tile?
        if port == "reg":
            port = "data0"
        else:
            reg_op = int(port[-1])
            if reg_op == 0:
                port = "data0"
            else:
                port = "data1"
    else:
        track_str1, track_str2 = track_str, track_str

    # compute the fixed positions
    fixed_direction = get_pin_fixed_direction(blk_id, port)

    if fixed_direction == direction:
        # we're good

        output_string += \
            "T{1}_in_s{2}t{0}{4} -> T{1}_{3}{5}\n".format(
                track, tile, direction, port, track_str1, track_str2)
        return output_string
    else:
        # lots of tweaks
        # this has to be consistent with the router behavior

        output_string += \
            "T{1}_in_s{2}t{0}{4} -> T{1}_out_s{3}t{0}{5}\n".format(
                track, tile, direction, fixed_direction, track_str, track_str)
        output_string += \
            "T{1}_out_s{2}t{0}{4} -> T{1}_{3}{5}\n".format(track,
                                                       tile,
                                                       fixed_direction,
                                                       port,
                                                       track_str1,
                                                       track_str2)
        return output_string


def build_graph(netlists):
    g = nx.Graph()
    for net_id in netlists:
        for blk_id, _ in netlists[net_id]:
            g.add_edge(net_id, blk_id)
    for edge in g.edges():
        g[edge[0]][edge[1]]['weight'] = 1
    return g.to_undirected()


def prune_netlist(raw_netlist):
    new_netlist = {}
    for net_id in raw_netlist:
        new_net = []
        for entry in raw_netlist[net_id]:
            new_net.append(entry[0])
        new_netlist[net_id] = new_net
    return new_netlist

