from __future__ import print_function
import arch
import networkx as nx
import random

from . import load_packed_file, read_netlist_json


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
        for blk_id in blk_keys:
            x, y = board_pos[blk_id]
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


def place_special_blocks(board, blks, board_pos, netlists, id_to_name,
                         place_on_board):
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

    blks = list(blks)
    blks.sort(key=lambda x: int(x[1:]))

    for blk_id in blks:
        if blk_id[0] == "i":
            is_input = io_mapping[blk_id]
            if is_input:
                pos = input_io_locations.pop(0)
            else:
                # FIXME
                # Hard-code position since Steve's simulation only handles
                # pad_S1_T0 1-bit output
                io_name = id_to_name[blk_id]
                if "io1_" in io_name:
                    assert (2, 18) in output_io_locations
                    pos = (2, 18)
                    output_io_locations.remove(pos)
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


def save_routing_result(route_result, output_file):
    with open(output_file, "w+") as f:
        # write header
        f.write("# Path format:\n")
        f.write("# (BUS, IN (0) | OUT(1), SIDE, TRACK)\n\n")
        net_id_list = list(route_result.keys())
        net_id_list.sort(key=lambda x: int(x[1:]))
        for net_id in net_id_list:
            f.write("Net ID: {}\n".format(net_id))
            path = route_result[net_id]
            node_index = 0
            for index, conn in enumerate(path):
                if len(conn) == 1:
                    # src
                    p, port, dir_out, dir_in = conn[0]
                    f.write("Node {}: SOURCE {}::{} -> {} -> {}\n".format(
                        node_index,
                        p,
                        port,
                        dir_out,
                        dir_in))
                elif len(conn) == 2:
                    # passing through
                    p1, dir_out = conn[0]
                    p2, dir_in = conn[1]
                    f.write("Node {}: {} -> {}\t{} -> {}\n".format(node_index,
                                                                   p1,
                                                                   p2,
                                                                   dir_out,
                                                                   dir_in))
                elif len(conn) == 3:
                    # direct sink
                    conn, pos, port = conn
                    if isinstance(port, str):
                        f.write("Node {}: SINK {}::{} <- {}\n".format(
                            node_index,
                            pos,
                            port,
                            conn))
                    else:
                        assert (isinstance(port, tuple))
                        f.write(
                            "Node {}: SINK {}::{}\t{} <- {}\n".format(
                                node_index,
                                pos,
                                "reg",
                                port,
                                conn))
                elif len(conn) == 4:
                    # self-connection sink
                    # [dir_in, conn, current_point, port]
                    dir_in, conn, pos, port = conn
                    f.write("Node {}: {} -> {}\t{} -> {}\n".format(node_index,
                                                                   pos,
                                                                   pos,
                                                                   dir_in,
                                                                   conn))
                    f.write("Node {}: SINK {}::{} <- {}\n".format(node_index,
                                                                  pos,
                                                                  port,
                                                                  conn))
                node_index += 1

            f.write("\n")


def parse_routing_result(routing_file):
    with open(routing_file) as f:
        lines = f.readlines()
    result = {}
    net_id = -1
    total_lines = len(lines)
    line_num = 0

    def remove_comment(str_val):
        if "#" in str_val:
            return str_val[:str_val.index("#")]
        return str_val

    def parse_conn(str_val):
        str_val = str_val.strip()
        assert str_val[0] == "("
        assert str_val[-1] == ")"
        str_val = str_val[1:len(str_val) - 1]
        return tuple([int(x) for x in str_val.split(",") if x])

    while line_num < total_lines:
        line = lines[line_num].strip()
        line_num += 1
        line = remove_comment(line)
        if len(line) < 7:
            # don't care
            continue
        if line[:7] == "Net ID:":
            net_id = line[8:]
            assert net_id[1:].isdigit()
            # read through the net
            conns = []
            # sanity check
            has_src = False
            has_sink = False
            node_index = 0
            while True:
                line = lines[line_num].strip()
                if len(line) == 0:
                    break
                line = remove_comment(line)
                line_num += 1
                if len(line) == 0:
                    continue    # don't care about comments
                node_id = "Node {}:".format(node_index)
                pre_node_id = "Node {}:".format(node_index - 1)
                # make sure it exists
                if pre_node_id in line:
                    start_index = line.index(pre_node_id)
                    self_connected_sink = True
                else:
                    start_index = line.index(node_id)
                    self_connected_sink = False
                    node_index += 1
                line = line[start_index + len(node_id):].strip()

                if line[:6] == "SOURCE":
                    # source
                    has_src = True
                    line = line[6:].strip()
                    assert ("->" in line)
                    assert (not self_connected_sink)
                    src, conn_in, conn_out = line.split("->")
                    src_pos, src_port = src.split("::")
                    src_pos = parse_conn(src_pos)
                    src_port = src_port.strip()
                    conn_in, conn_out = parse_conn(conn_in),\
                                        parse_conn(conn_out)
                    conns.append(("src", (src_pos, src_port),
                                  (conn_in, conn_out)))
                elif line[:4] == "SINK":
                    # sink
                    has_sink = True
                    line = line[4:].strip()
                    assert ("<-" in line)
                    if "\t" in line:
                        pos_port, link = line.split("\t")
                        dst_pos, dst_port = pos_port.split("::")
                        dst_pos = parse_conn(dst_pos)
                        assert (dst_port == "reg")
                        conn_in, conn_out = link.split("<-")
                        conn_in, conn_out = parse_conn(conn_in),\
                            parse_conn(conn_out)
                        conns.append(("sink", (conn_in, conn_out),
                                      (dst_pos, dst_port)))
                        pass
                    else:
                        dst, conn = line.split("<-")
                        dst_pos, dst_port = dst.split("::")
                        dst_pos = parse_conn(dst_pos)
                        dst_port = dst_port.strip()
                        conn = parse_conn(conn)
                        if self_connected_sink:
                            conns[-1] = ("sink", conns[-1][1:], conn,
                                         (dst_pos, dst_port))
                        else:
                            conns.append(("sink", conn, (dst_pos, dst_port)))
                else:
                    # links
                    assert ("\t" in line)
                    assert (not self_connected_sink)
                    positions, chan_connection = line.split("\t")
                    src_pos, dst_pos = positions.split("->")
                    src_pos, dst_pos = parse_conn(src_pos), parse_conn(dst_pos)
                    conn1, conn2 = chan_connection.split("->")
                    conn1, conn2 = parse_conn(conn1), parse_conn(conn2)
                    conns.append(("link", (src_pos, dst_pos), (conn1, conn2)))

            # make sure it's an actual net
            assert has_sink
            result[net_id] = conns

    return result


def generate_bitstream(board_filename, packed_filename, placement_filename,
                       routing_filename, output_filename,
                       fold_reg=True):
    netlists, folded_blocks, id_to_name, changed_pe =\
        load_packed_file(packed_filename)
    g = build_graph(netlists)
    board_meta = arch.parse_cgra(board_filename, True)["CGRA"]
    placement, _ = parse_placement(placement_filename)
    route_result = parse_routing_result(routing_filename)
    tile_mapping = board_meta[-1]
    board_layout = board_meta[0]
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
        tile_op, print_order = get_tile_op(instance, blk_id, changed_pe)
        if tile_op is None:
            continue
        pins = get_tile_pins(blk_id, tile_op, folded_blocks, instances,
                             changed_pe, id_to_name, connections)

        # parse pins from the packing

        pe_tiles[blk_id] = (tile, tile_op, pins, print_order)

    tab = "\t" * 6
    # generate tile mapping
    # sort them for pretty printing
    pe_keys = list(pe_tiles.keys())
    pe_keys.sort(key=lambda x: int(pe_tiles[x][0]))
    pe_keys.sort(key=lambda x: pe_tiles[x][-1])
    output_string += "# PLACEMENT\n"
    for blk_id in pe_keys:
        tile, op, pins, _ = pe_tiles[blk_id]
        if "mem" in op:
            output_string += "T{}_{}{}#{}\n".format(tile, op,
                                                    tab,
                                                    id_to_name[blk_id])
        else:
            output_string += "T{}_{}({}){}# {}\n".format(tile, op,
                                                         ",".join(pins),
                                                         tab,
                                                         id_to_name[blk_id])

    # FIXME 1-bit IO hack
    for blk_id in id_to_name:
        if blk_id[0] == "i" and "io1_" in id_to_name[blk_id]:
            output_string += "\n\n#IO\n"
            output_string += "Tx136_pad(out,1)\n"
            break

    output_string += "\n\n#ROUTING\n"
    net_id_list = list(route_result.keys())
    net_id_list.sort(key=lambda x: int(x[1:]))
    for net_id in net_id_list:
        path = route_result[net_id]
        output_string += "\n# net id: {}\n".format(net_id)
        netlist = netlists[net_id]
        for p in netlist:
            output_string += "# {}: {}::{}\n".format(p[0], id_to_name[p[0]],
                                                     p[1])
        track_in = None
        for index, entry in enumerate(path):
            if index == len(path) - 1:
                # sink
                break
            path_type = entry[0]
            if index == 0:
                assert (path_type == "src")
                s, track_in = handle_src(entry[1], entry[2], tile_mapping,
                                         board_layout,
                                         fold_reg=fold_reg)
                output_string += s
            else:
                if path_type == "link":
                    s, track_in = handle_link(entry[1], entry[2],
                                              track_in,
                                              tile_mapping,
                                              board_layout)
                    output_string += s
                elif path_type == "sink":
                    s, track_in = handle_sink_entry(entry, track_in,
                                                    tile_mapping, board_layout,
                                                    folded_blocks, placement,
                                                    fold_reg=fold_reg)
                    output_string += s
                else:
                    raise Exception("Unknown stage: " + path_type)

        entry = path[-1]
        s, _ = handle_sink_entry(entry, track_in,
                                 tile_mapping, board_layout,
                                 folded_blocks, placement,
                                 fold_reg=fold_reg)
        output_string += s

        output_string += "\n"

    with open(output_filename, "w+") as f:
        f.write(output_string)


def make_track_string(pos, track, tile_mapping, board_layout, track_str=""):
    bus, is_out, side, chan = track
    # if board_layout[pos[1]][pos[0]] is None:
    #     # TODO: USE MEM CAPACITY
    #    assert(board_layout[pos[1] - 1][pos[0]] == "m")
    #    pos = pos[0], pos[1] - 1
    tile = tile_mapping[pos]
    result = "T{}_{}_s{}t{}{}{}".format(
        tile,
        "out" if is_out else "in",
        side,
        chan,
        "" if bus == 16 else "b",
        track_str
    )
    return result


def handle_sink_entry(entry, track_in, tile_mapping, board_layout,
                      folded_blocks, placement, fold_reg=True):
    if len(entry) == 4:
        s, track_in = handle_sink(entry[1], entry[2], entry[3],
                                  track_in,
                                  tile_mapping,
                                  board_layout,
                                  folded_blocks,
                                  placement)
    elif len(entry) == 3:
        if entry[-1][-1] == "reg":
            assert fold_reg
            s, track_in = handle_reg_sink(entry[1:], track_in, tile_mapping,
                                          board_layout)
        else:
            s, track_in = handle_sink(None, entry[1], entry[2],
                                      track_in,
                                      tile_mapping,
                                      board_layout,
                                      folded_blocks,
                                      placement)
    else:
        raise Exception("Unknown entry " + str(entry))
    return s, track_in


def handle_reg_sink(entry, track_in, tile_mapping, board_layout):
    (dir_out, dir_in), (pos, port) = entry
    assert (port == "reg")
    result, _ = handle_link((pos, pos), (dir_out, dir_in), dir_in, tile_mapping,
                         board_layout, track_str=" (r)")
    return result, track_in


def handle_sink(self_conn, conn, dst, track_in,
                tile_mapping, board_layout, folded_blocks, placement,
                track_str=""):
    result = ""
    dst_pos, dst_port = dst
    if self_conn is not None:
        # most of them
        start = make_track_string(dst_pos, track_in, tile_mapping, board_layout)
        end = make_track_string(dst_pos, conn, tile_mapping, board_layout)
        result = start + " -> " + end + "\n"
    start = make_track_string(dst_pos, conn, tile_mapping, board_layout)

    # need to find out if it's a folded register or not
    pos_to_id = {}
    for blk_id in placement:
        if blk_id[0] == "r":
            continue
        pos = placement[blk_id]
        assert (pos not in pos_to_id)
        pos_to_id[pos] = blk_id

    pos_port_set = set()
    for entry in folded_blocks:
        info = folded_blocks[entry]
        if len(info) == 2:
            blk_id, port = info
            pos = placement[blk_id]
            pos_port_set.add((pos, port))
    #if dst in pos_port_set:
    #    track_str = " (r)"
    #else:
    #    track_str = ""
    tile = tile_mapping[dst_pos]
    track = "" if conn[0] == 16 else "b"
    end = "T{}_{}{}{}\n".format(tile,
                                dst_port,
                                track,
                                track_str)

    result += start + " -> " + end

    # Keyi:
    # current bsbuilder doesn't like IO stuff
    if board_layout[dst_pos[1]][dst_pos[0]] == "i":
        result = ""
    return result, track_in


def handle_link(conn1, conn2, pre_in, tile_mapping, board_layout, track_str=""):
    src_pos, dst_pos = conn1
    track_out, track_in = conn2
    start = make_track_string(src_pos, pre_in, tile_mapping, board_layout)
    end = make_track_string(src_pos, track_out, tile_mapping, board_layout)
    result = start + " -> " + end + track_str + "\n"
    return result, track_in


def handle_src(src, conn, tile_mapping, board_layout, fold_reg=True):
    src_pos = src[0]
    src_port = src[1]
    tile = tile_mapping[src_pos]
    if src_port == "out":
        src_port = "pe_out"
    elif src_port == "reg":
        assert fold_reg
        return "", conn[1]
    track = "" if conn[0][0] == 16 else "b"
    start = "T{}_{}{}".format(tile, src_port, track)
    end = make_track_string(src_pos, conn[0], tile_mapping, board_layout)
    result = start + " -> " + end + "\n"
    # Keyi:
    # the bsbuilder doesn't like IO tiles
    # use board_layout to leave that black
    if board_layout[src_pos[1]][src_pos[0]] == "i":
        result = ""
    return result, conn[1]


def get_const_value(instance):
    if "modref" in instance:
        modref = instance["modref"]
        if modref == "corebit.const":
            val = instance["modargs"]["value"][-1]
            if val:
                return "const1_1"
            else:
                return "const0_0"
    elif "genref" in instance:
        genref = instance["genref"]
        if genref == "coreir.const":
            str_val = instance["modargs"]["value"][-1]
            if isinstance(str_val, int):
                int_val = str_val
            else:
                start_index = str_val.index("h")
                str_val = str_val[start_index + 1:]
                int_val = int(str_val, 16)
            return "const{0}_{0}".format(int_val)
    return None


def get_lut_pins(instance):
    assert ("genref" in instance and instance["genref"] == "cgralib.PE")
    assert ("genargs" in instance and
            instance["genargs"]["op_kind"][-1] == "bit")
    assert ("modargs" in instance)
    modargs = instance["modargs"]
    bit0_value = modargs["bit0_value"][-1]
    bit1_value = modargs["bit1_value"][-1]
    bit2_value = modargs["bit2_value"][-1]
    return int(bit0_value), int(bit1_value), int(bit2_value)


def get_tile_pins(blk_id, op, folded_block, instances, changed_pe,
                  id_to_name, connections):
    instance_name = id_to_name[blk_id]
    if op[:3] == "mem":
        return None
    if "lut" in op:
        lut_pins = get_lut_pins(instances[instance_name])
        pins = ["const{0}_{0}".format(i) for i in lut_pins]
        assert len(pins) == 3
    else:
        pins = [None, None]

    # second pass to write wires
    for net in connections:
        for conn in net:
            pin_name = conn.split(".")[0]
            pin_port = ".".join(conn.split(".")[1:])
            if pin_name == instance_name and "out" not in pin_port:
                if pin_port != "in":
                    index = int(pin_port[-1])
                else:
                    index = 0
                pins[index] = "wire"

    # third pass to determine the
    for entry in folded_block:
        entry_data = folded_block[entry]
        if len(entry_data) == 2:
            # reg folding
            assert(entry[0][0] == "r")
            b_id, port = entry_data
            pin_name = "reg"
        elif len(entry_data) == 3:
            b_id, pin_name, port = entry_data
            # it's constant
            pin_name = get_const_value(instances[pin_name])
        else:
            raise Exception("Unknown folded block data " + str(entry_data))
        if b_id == blk_id:
            index = int(port[-1])
            assert(pin_name is not None)
            pins[index] = pin_name
    if blk_id in changed_pe:
        pins[0] = "reg"
        pins[1] = "const0_0"

    # sanity check
    for pin in pins:
        assert (pin is not None)

    return tuple(pins)


def get_tile_op(instance, blk_id, changed_pe, rename_op=True):
    """rename_op (False) is used to calculate delay"""
    if "genref" not in instance:
        assert ("modref" in instance)
        assert (instance["modref"] == "cgralib.BitIO")
        return None, None
    pe_type = instance["genref"]
    if pe_type == "coreir.reg":
        # reg tile, reg in and reg out
        if blk_id in changed_pe:
            if rename_op:
                return "add", 0
            else:
                return "alu", 0
        else:
            return None, None
    elif pe_type == "cgralib.Mem":
        if rename_op:
            op = "mem_" + str(instance["modargs"]["depth"][-1])
        else:
            op = "mem"
        print_order = 3
    elif pe_type == "cgralib.IO":
        return None, None    # don't care yet
    else:
        op = instance["genargs"]["op_kind"][-1]
        if op == "bit":
            lut_type = instance["modargs"]["lut_value"][-1][3:].lower()
            print_order = 0
            if lut_type == "3f":
                print_order = 2
            if rename_op:
                op = "lut" + lut_type.upper()
            else:
                op = "alu"
        elif op == "alu" or op == "combined":
            if "alu_op_debug" in instance["modargs"]:
                op = instance["modargs"]["alu_op_debug"][-1]
            else:
                op = instance["modargs"]["alu_op"][-1]
            if not rename_op:
                op = "alu"
            print_order = 0

        else:
            raise Exception("Unknown PE op type " + op)
    return op, print_order


def determine_pin_ports(net, placement, fold_reg=True):
    pin_directions = set()
    # FIXME use the naming in the CGRA description file
    allowed_initial_ports = {"data0", "data1", "bit0", "bit1", "bit2", "wen",
                             "reg"}
    if not fold_reg:
        allowed_initial_ports.remove("reg")
    for index, (blk_id, port) in enumerate(net):
        if index == 0 and port not in allowed_initial_ports:
            # it's a a source
            continue
        pos = placement[blk_id]
        pin_directions.add((pos, port))

    return pin_directions


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
