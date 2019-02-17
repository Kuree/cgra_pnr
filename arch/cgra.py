from __future__ import print_function, division
import arch
import json
import six

from . import load_packed_file, read_netlist_json
from .parser import parse_routing


def save_placement(board_pos, id_to_name, _, place_file):
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
    if len(placement_file) == 0:
        return {}, {}
    with open(placement_file) as f:
        lines = f.readlines()
    lines = lines[2:]
    placement = {}
    id_to_name = {}
    for line in lines:
        raw_line = line.split()
        assert (len(raw_line) == 4)
        blk_name = raw_line[0]
        x = int(raw_line[1])
        y = int(raw_line[2])
        blk_id = raw_line[-1][1:]
        placement[blk_id] = (x, y)
        id_to_name[blk_id] = blk_name
    return placement, id_to_name


def place_special_blocks(board, blks, board_pos, netlists,
                         place_on_board, layout):
    # put IO in fixed blocks
    one_bit_io_layer = layout.get_layer("i")
    one_bit_io_locations = one_bit_io_layer.produce_available_pos()
    sixteen_bit_io_layer = layout.get_layer("I")
    sixteen_bit_io_locations = sixteen_bit_io_layer.produce_available_pos()

    blks = list(blks)
    blks.sort(key=lambda b: int(b[1:]))
    io_blks = []
    for blk_id in blks:
        if blk_id[0] == "i" or blk_id[0] == "I":
            io_blks.append(blk_id)
    # we assign 16-bit first so that we can apply masksk
    io_blks.sort(key=lambda x: x[0] == "i")
    io_mask = layout.get_layer_masks()["I"]

    for blk_id in io_blks:
        if blk_id[0] == "i":
            pos = sixteen_bit_io_locations.pop()
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
        elif blk_id[0] == "I":
            pos = sixteen_bit_io_locations.pop()
            place_on_board(board, blk_id, pos)
            board_pos[blk_id] = pos
            # disbale io_mask for now
            # assert pos in io_mask.mask_pos
            # bit1_ios = io_mask.mask_pos[pos]
            # for pos in bit1_ios:
            #     if pos in one_bit_io_locations:
            #         one_bit_io_locations.remove(pos)
        else:
            raise Exception("Unknown block type", blk_id)


def get_blks(netlist):
    result = set()
    for _, blks in netlist.items():
        for blk in blks:
            if blk[0][0] != "I" and blk[0][0] != "i":
                result.add(blk[0])
    return result


def generate_bitstream(board_filename, netlist_filename,
                       packed_filename, placement_filename,
                       routing_filename, output_filename,
                       io_json):
    netlists, folded_blocks, id_to_name, changed_pe = \
        load_packed_file(packed_filename)
    blks = get_blks(netlists)
    board_meta = arch.parse_cgra(board_filename, True)["CGRA"]
    placement, _ = parse_placement(placement_filename)
    tile_mapping = board_meta[-1]
    board_layout = board_meta[0]
    io_pad_name = board_meta[-2]["io_pad_name"]
    io_pad_bit = board_meta[-2]["io_pad_bit"]
    io16_tile = board_meta[-2]["io16_tile"]

    connections, instances = read_netlist_json(netlist_filename)

    output_string = ""

    # TODO: refactor this
    name_to_id = {}
    for blk_id in id_to_name:
        name_to_id[id_to_name[blk_id]] = blk_id

    # build PE tiles types
    pe_tiles = {}
    type_str = "mpirI"
    for name in instances:
        instance = instances[name]
        blk_id = name_to_id[name]
        if blk_id in folded_blocks:
            continue
        blk_id = name_to_id[name]
        # it might be absorbed already
        if blk_id not in blks:
            continue
        # it has to be a PE tile
        assert (blk_id[0] in type_str)
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
            output_string += "Tx{:04X}_{}{}#{}\n".format(tile, op,
                                                         tab,
                                                         id_to_name[blk_id])
        else:
            output_string += "Tx{:04X}_{}({}){}# {}\n".format(tile, op,
                                                              ",".join(pins),
                                                              tab,
                                                              id_to_name[
                                                                  blk_id])
    # IO info
    io_pad_info, io_strings = generate_io(id_to_name, io16_tile, io_pad_bit,
                                          io_pad_name, placement, tile_mapping)

    assert len(io_strings) > 0
    output_string += "\n\n#IO\n"
    output_string += "\n".join(io_strings)

    output_string += "\n\n#ROUTING\n"

    routes = generate_routing(routing_filename, tile_mapping, board_layout)
    net_id_list = list(routes.keys())
    net_id_list.sort(key=lambda x: int(x[1:]))

    for net_id in net_id_list:
        output_string += "\n# net id: {}\n".format(net_id)
        netlist = netlists[net_id]
        for p in netlist:
            output_string += "# {}: {}::{}\n".format(p[0], id_to_name[p[0]],
                                                     p[1])
        output_string += routes[net_id]

        output_string += "\n"

    with open(output_filename, "w+") as f:
        f.write(output_string)

    with open(io_json, "w+") as f:
        json.dump(io_pad_info, f, indent=2, separators=(',', ': '))


def generate_routing(routing_file, tile_mapping, board_layout):
    routes = parse_routing(routing_file)
    result = {}
    for net_id in routes:
        lines = []
        line = ""
        for segment in routes[net_id]:
            last_node = ""
            seg_index = 0
            while seg_index < len(segment):
                seg = segment[seg_index]
                node_type = seg[0]
                if node_type == "PORT" and seg_index == 0:
                    port_name = seg[1]
                    if port_name == "out" or port_name == "outb":
                        port_name = "pe_" + port_name
                    elif port_name == "valid":
                        port_name = "validb"
                    x, y = seg[2], seg[3]
                    pos = (x, y)
                    blk_type = board_layout.get_blk_type(x, y)
                    if blk_type == "i" or blk_type == "I":
                        seg_index += 2
                        line = ""
                        continue
                    last_node = "Tx{:04X}".format(tile_mapping[pos]) \
                                + "_" + port_name

                    line += last_node + " -> "
                elif node_type == "REG" and seg_index != 0:
                    # in BSB we actually don't care about the reg node
                    # since it's implicit
                    # we rewind the last line and add (r) to it
                    # FIXME: change it back once steve fixed it
                    assert seg_index == len(segment) - 1
                    lines[-1] = lines[-1] + " (r)"
                    line = ""
                elif node_type == "SB":
                    track = seg[1]
                    pos = (seg[2], seg[3])
                    side = seg[4]
                    io = seg[5]
                    one_bit = seg[6] != 16
                    last_node = "Tx{:04X}".format(tile_mapping[pos]) \
                                + "_{}_".format("out" if io else "in") \
                                + "s{}t{}{}".format(side, track,
                                                    "b" if one_bit else "")
                    line += last_node
                    if io == 0:
                        # coming in
                        line += " -> "
                    else:
                        lines.append(line)
                        line = ""
                elif node_type == "PORT" and seg_index != 0:
                    # this is sink
                    # we need to double check if the previous one is coming
                    # in or out
                    # FIXME:
                    # fix this hack
                    pre_node = segment[seg_index - 1]
                    port_name = seg[1]
                    one_bit = seg[-1] != 16
                    x, y = seg[2], seg[3]
                    pos = (x, y)
                    blk_type = board_layout.get_blk_type(x, y)
                    if blk_type == "i" or blk_type == "I":
                        seg_index += 1
                        continue
                    if pre_node[0] == "SB":
                        if pre_node[2] != seg[2] or pre_node[3] != seg[3]:
                            # we need to produce a fake one
                            side = (pre_node[4] + 2) % 4
                            track = pre_node[1]
                            last_node = "Tx{:04X}".format(tile_mapping[pos]) \
                                        + "_in_" \
                                        + "s{}t{}{}".format(side, track,
                                                            "b" if one_bit
                                                            else "")
                            line += last_node + " -> "
                        else:
                            line += last_node + " -> "
                    elif pre_node[0] == "REG":
                        # FIXME: hack an input track
                        #        by using the register name
                        _, reg_io, reg_side = pre_node[1].split("_")
                        reg_track = int(reg_io)
                        reg_side = (int(reg_side) + 2) % 4
                        one_bit = False
                        track = pre_node[2]
                        assert reg_track == track
                        last_node = "Tx{:04X}".format(tile_mapping[pos]) \
                                    + "_in_" \
                                    + "s{}t{}{}".format(reg_side, track,
                                                        "b" if one_bit
                                                        else "")
                        line += last_node + " -> "
                    else:
                        raise Exception("Unknown node " + str(pre_node))
                    line += "Tx{:04X}".format(tile_mapping[pos]) \
                            + "_" + port_name
                    lines.append(line)
                    line = ""

                seg_index += 1
        result[net_id] = "\n".join(lines)

    return result


def generate_io(id_to_name, io16_tile, io_pad_bit, io_pad_name, placement,
                tile_mapping):
    io_strings = []
    io_pad_info = {}
    for blk_id in id_to_name:
        if blk_id[0] == "i" or blk_id[0] == "I":
            pos = placement[blk_id]
            pad_name = io_pad_name[pos]
            if "io1_" in id_to_name[blk_id]:
                # hack to make it consistent with run_tbg.csh
                id_to_name[blk_id] = "io1_out_0_0"
                io_bit = io_pad_bit[pos]
                io_pad_info[id_to_name[blk_id]] = {"bits":
                                                       {"0": {"pad_bit":
                                                                  io_bit}},
                                                   "mode": "out",
                                                   "width": 1}
                tile = tile_mapping[pos]
                io_strings.append("Tx{:04X}_pad(out,1)".format(tile))
            elif "reset" in id_to_name[blk_id]:
                io_bit = io_pad_bit[pos]
                io_pad_info[id_to_name[blk_id]] = {"bits":
                                                       {"0": {"pad_bit":
                                                                     io_bit}},
                                                   "mode": "reset",
                                                   "width": 1}
                tile = tile_mapping[pos]
                io_strings.append("Tx{:04X}_pad(in,1)".format(tile))
            elif "io16_out" in id_to_name[blk_id]:
                io_pad_info[id_to_name[blk_id]] = {"mode": "out",
                                                   "width": 16}
                for tile_addr in io16_tile[pad_name]:
                    io_strings.append("Tx{:04X}_pad(out,16)".format(tile_addr))

            elif "io16in" in id_to_name[blk_id]:
                io_pad_info[id_to_name[blk_id]] = {"mode": "in",
                                                   "width": 16}
                for tile_addr in io16_tile[pad_name]:
                    io_strings.append("Tx{:04X}_pad(in,16)".format(tile_addr))
            else:
                raise Exception("Unrecognized io name " + id_to_name[blk_id])
            # get bus pad name
            io_pad_info[id_to_name[blk_id]]["pad_bus"] = pad_name
    return io_pad_info, io_strings


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
    elif op[:3] == "mux" or op[:3] == "sel":
        pins = [None, None, None]
    else:
        pins = [None, None]

    # second pass to write wires
    for net in connections:
        for conn in net:
            pin_name = conn.split(".")[0]
            pin_port = ".".join(conn.split(".")[1:])
            if pin_name == instance_name and "out" not in pin_port:
                if (op == "mux" or op == "sel") and "bit.in.0" == pin_port:
                    index = 2
                elif pin_port != "in":
                    index = int(pin_port[-1])
                else:
                    index = 0
                pins[index] = "wire"

    # third pass to determine the consts/regs
    for entry in folded_block:
        entry_data = folded_block[entry]
        if len(entry_data) == 2:
            # reg folding
            assert (entry[0][0] == "r")
            b_id, port = entry_data
            pin_name = "reg"
        elif len(entry_data) == 3:
            b_id, pin_name, port = entry_data
            # it's constant
            pin_name = get_const_value(instances[pin_name])
        else:
            raise Exception("Unknown folded block data " + str(entry_data))
        if b_id == blk_id:
            # mux is very special
            if port == "bit0" and (op == "mux" or op == "sel"):
                index = 2
            else:
                index = int(port[-1])
            assert (pin_name is not None)
            pins[index] = pin_name
    if blk_id in changed_pe:
        pins[0] = "reg"
        pins[1] = "const0_0"

    # sanity check
    for pin in pins:
        if pin is None:
            raise Exception("pin is none for blk_id: " + blk_id)

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
        return None, None  # don't care yet
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
            # get signed or unsigned
            if "signed" in instance["modargs"]:
                signed = instance["modargs"]["signed"][-1]
                if type(signed) != bool:
                    assert isinstance(signed, six.string_types)
                    signed = False if signed[-1] == "0" else True
                if signed and rename_op:
                    op = "s" + op
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


def prune_netlist(raw_netlist):
    new_netlist = {}
    for net_id in raw_netlist:
        new_net = []
        for entry in raw_netlist[net_id]:
            new_net.append(entry[0])
        new_netlist[net_id] = new_net
    return new_netlist
