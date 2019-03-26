"""
This tool designed to pack as much as possible for CGRA, yet gives placer
and router flexibility to choose their algorithm.

Because the current CGRA flow does not have packing tools. This might be the
very first packing/clustering tools for AHA group
"""
from __future__ import print_function
import sys
import json
import os
from .netlist import is_conn_out, is_conn_in


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
            if is_conn_in(raw_splits):
                return 2
            elif is_conn_out(raw_splits):
                return 0
            else:
                return 1
        # rearrange the net so that it's src -> sink
        net.sort(key=lambda p: sort_value(p))
        # sanity check to make sure that the first one is indeed an out
        assert (is_conn_out(net[0]))
        netlists.append(net)
    # print("INFO: before conversion connections", len(connections),
    #       "after conversion netlists:", len(netlists))
    return netlists


def rename_id_changed(id_to_name, changed_pe):
    new_changed_pe = set()
    for blk_id in changed_pe:
        # need to make sure ID to name is correct
        blk_name = id_to_name.pop(blk_id, None)
        assert (blk_name is not None)
        new_blk_id = "p" + blk_id[1:]
        id_to_name[new_blk_id] = blk_name
        new_changed_pe.add(new_blk_id)
    changed_pe.clear()
    changed_pe.update(new_changed_pe)


def determine_track_bus(netlists, id_to_name):
    track_mode = {}
    for net_id in netlists:
        net = netlists[net_id]
        bus = 16
        for blk_id, port in net:
            if "bit" in port or "en" in port:
                bus = 1
                break
            blk_name = id_to_name[blk_id]
            if "io1_" in blk_name:
                bus = 1
                break
        track_mode[net_id] = bus
    return track_mode


def save_packing_result(netlist_filename, pack_filename, fold_reg=True):
    netlists, folded_blocks, id_to_name, changed_pe = \
        parse_and_pack_netlist(netlist_filename, fold_reg=fold_reg)

    rename_id_changed(id_to_name, changed_pe)
    track_mode = determine_track_bus(netlists, id_to_name)

    write_packing_result(changed_pe, folded_blocks, id_to_name, netlists,
                         pack_filename, track_mode)


def write_packing_result(changed_pe, folded_blocks, id_to_name, netlists,
                         pack_filename, track_mode):
    with open(pack_filename, "w+") as f:
        def tuple_to_str(t_val):
            return "(" + ", ".join([str(val) for val in t_val]) + ")"

        f.write("# It has three sections: netlists, folded_blocks, " +
                "and id_to_name\n\n")
        # netlists
        f.write("Netlists:\n")
        net_ids = list(netlists.keys())
        net_ids.sort(key=lambda x: int(x[1:]))
        for net_id in net_ids:
            f.write("{}: ".format(net_id))
            f.write("\t".join([tuple_to_str(entry)
                               for entry in netlists[net_id]]))

            f.write("\n")
        f.write("\n")

        # folded blocks
        f.write("Folded Blocks:\n")
        for entry in folded_blocks:
            folded = folded_blocks[entry]
            f.write(tuple_to_str(entry) + " -> " + tuple_to_str(folded) + "\n")

        f.write("\n")
        # ID to names
        f.write("ID to Names:\n")
        ids = list(id_to_name.keys())
        ids.sort(key=lambda x: int(x[1:]))
        for blk_id in ids:
            f.write(str(blk_id) + ": " + id_to_name[blk_id] + "\n")

        f.write("\n")
        # registers that have been changed to PE
        f.write("Changed to PE:\n")
        for blk_id in changed_pe:
            f.write(str(blk_id) + ": " + id_to_name[blk_id] + "\n")

        f.write("\n")
        # registers that have been changed to PE
        f.write("Netlist Bus:\n")
        for net_id in track_mode:
            f.write(str(net_id) + ": " + str(track_mode[net_id]) + "\n")


def load_packed_file(pack_filename, load_track_mode=False):
    with open(pack_filename) as f:
        lines = f.readlines()

    def remove_comment(str_val):
        if "#" in str_val:
            return str_val[:str_val.index("#")]
        return str_val.strip()

    def convert_net(net_entry):
        result = []
        raw_net = net_entry.split("\t")
        for entry in raw_net:
            entry = entry.strip()
            assert (entry[0] == "(" and entry[-1] == ")")
            entry = entry[1:-1]
            entries = [x.strip() for x in entry.split(",")]
            result.append(tuple(entries))
        return result

    def find_next_block(ln):
        while True:
            line_info = lines[ln]
            line_info = remove_comment(line_info)
            if len(line_info) == 0:
                ln += 1
            else:
                break
        return ln

    line_num = find_next_block(0)

    line = remove_comment(lines[line_num])
    assert(line == "Netlists:")
    line_num += 1

    netlists = {}
    while True:
        line = remove_comment(lines[line_num])
        if len(line) == 0:
            break
        net_id, net = line.split(":")
        assert ("\t" in net)
        net = convert_net(net)
        netlists[net_id] = net

        line_num += 1

    line_num = find_next_block(line_num)
    line = remove_comment(lines[line_num])
    assert (line == "Folded Blocks:")
    line_num += 1
    folded_blocks = {}
    while True:
        line = remove_comment(lines[line_num])
        if len(line) == 0:
            break

        entry1, entry2 = line.split("->")
        entry1, entry2 = convert_net(entry1)[0], convert_net(entry2)[0]
        folded_blocks[entry1] = entry2

        line_num += 1

    line_num = find_next_block(line_num)
    line = remove_comment(lines[line_num])
    assert (line == "ID to Names:")
    line_num += 1
    id_to_name = {}
    while line_num < len(lines):
        line = remove_comment(lines[line_num])
        if len(line) == 0:
            break
        blk_id, name = line.split(":")
        blk_id, name = blk_id.strip(), name.strip()
        id_to_name[blk_id] = name

        line_num += 1

    line_num = find_next_block(line_num)
    line = remove_comment(lines[line_num])
    assert (line == "Changed to PE:")
    line_num += 1
    changed_pe = set()
    while line_num < len(lines):
        line = remove_comment(lines[line_num])
        if len(line) == 0:
            break
        blk_id, _ = line.split(":")
        blk_id = blk_id.strip()
        changed_pe.add(blk_id)

        line_num += 1

    line_num = find_next_block(line_num)
    line = remove_comment(lines[line_num])
    assert (line == "Netlist Bus:")
    line_num += 1
    track_mode = {}
    while line_num < len(lines):
        line = remove_comment(lines[line_num])
        if len(line) == 0:
            break
        net_id, mode = line.split(":")
        net_id = net_id.strip()
        mode = int(mode)
        assert mode in [1, 16]
        track_mode[net_id] = mode

        line_num += 1
    if load_track_mode:
        return netlists, folded_blocks, id_to_name, changed_pe, track_mode
    else:
        return netlists, folded_blocks, id_to_name, changed_pe


def parse_and_pack_netlist(netlist_filename, fold_reg=True):
    connections, instances = read_netlist_json(netlist_filename)
    netlists, name_to_id = generate_netlists(connections, instances)
    before_packing = len(netlists)
    netlists, folded_blocks, changed_pe = pack_netlists(netlists, name_to_id,
                                                        fold_reg=fold_reg)
    after_packing = len(netlists)
    print("Before packing: num of netlists:", before_packing,
          "After packing: num of netlists:", after_packing)

    pes = set()
    ios = set()
    mems = set()
    regs = set()

    id_to_name = {}
    for name in name_to_id:
        blk_id = name_to_id[name]
        id_to_name[blk_id] = name

    for net_id in netlists:
        net = netlists[net_id]
        for blk_id, _ in net:
            if blk_id[0] == "p":
                pes.add(blk_id)
            elif blk_id[0] == "i" or blk_id[0] == "I":
                ios.add(blk_id)
            elif blk_id[0] == "m":
                mems.add(blk_id)
            elif blk_id[0] == "r":
                regs.add(blk_id)
    print("PE:", len(pes), "IO:", len(ios), "MEM:", len(mems), "REG:",
          len(regs))
    return netlists, folded_blocks, id_to_name, changed_pe


def generate_netlists(connections, instances):
    """
    convert connection to netlists with (id, port).
    port is something like reg, data0, or const, or value, which will be packed
    later
    """
    name_to_id = change_name_to_id(instances)
    h_edge_count = 0
    netlists = {}
    for conn in connections:
        edge_id = "e" + str(h_edge_count)
        h_edge_count += 1
        hyper_edge = []
        for idx, v in enumerate(conn):
            raw_names = v.split(".")
            blk_name = raw_names[0]
            blk_id = name_to_id[blk_name]
            port = ".".join(raw_names[1:])
            # FIXME: don't care about these so far
            if port == "ren" or port == "cg_en" or port == "clk_en":
                continue
            if port == "data.in.0" or port == "data0" or port == "in0":
                port = "data0"
            elif port == "data.in.1" or port == "data1" or port == "in1":
                port = "data1"
            elif port == "in" and "io1_" in v:
                port = "inb"
            elif port == "in":
                # either a reg or IO
                port = "in"
            elif port == "bit.in.0":
                port = "bit0"
            elif port == "bit.in.1":
                port = "bit1"
            elif port == "bit.in.2":
                port = "bit2"
            # need to be change to mem_in/mem_out in bitstream writer
            elif port == "wen":
                port = "wen"
            elif port == "rdata":
                port = "rdata"
            elif port == "wdata":
                port = "wdata"
            elif port == "data.out" or (port == "out" and "io1in" not in v):
                port = "out"
            elif port == "bit.out" or (port == "out" and "io1in" in v):
                port = "outb"
            elif port == "res":
                port = "res"
            elif port == "alu_res":
                port = "alu_res"
            elif port == "res_p":
                port = "res_p"
            elif "valid" in port:
                port = "valid"
            elif port == "io2f_16" or port == "tofab":
                port = "io2f_16"
            elif port == "f2io_16" or port == "fromfab":
                port = "f2io_16"
            else:
                raise Exception("Unrecognized port " + port + " for name " +
                                v)
            hyper_edge.append((blk_id, port))
        netlists[edge_id] = hyper_edge
    return netlists, name_to_id


def pack_netlists(raw_netlists, name_to_id, fold_reg=True):
    netlist_ids = set(raw_netlists.keys())
    folded_blocks = {}
    id_to_name = {}
    for name in name_to_id:
        id_to_name[name_to_id[name]] = name

    print("Absorbing constants and registers")
    changed_pe = set()
    dont_absorb = set()
    nets_to_remove = set()

    # first pass to figure out the reg's net connections
    connected_pe_tiles = {}
    for net_id in netlist_ids:
        net = raw_netlists[net_id]
        for index, (blk_id, port) in enumerate(net):
            if blk_id[0] == "r" and port == "out":
                for b_id, b_port in net:
                    if b_id == blk_id and port == b_port:
                        continue
                    if b_id[0] == "r":
                        # oh damn
                        dont_absorb.add(blk_id)
                    elif b_id[0] == "p":
                        if blk_id not in connected_pe_tiles:
                            connected_pe_tiles[blk_id] = set()
                        connected_pe_tiles[blk_id].add((b_id, b_port))

    for blk_id in connected_pe_tiles:
        connected = connected_pe_tiles[blk_id]
        if len(connected) > 1:
            # you can't drive two PE tiles. damn
            dont_absorb.add(blk_id)

    for net_id in netlist_ids:
        net = raw_netlists[net_id]
        remove_blks = set()
        for index, (blk_id, port) in enumerate(net):
            if index != len(net) - 1:
                next_index = index + 1
            else:
                next_index = None
            if next_index is None:
                next_blk, next_port = None, None
            else:
                next_blk, next_port = net[next_index]
            # replace them if they're already folded
            if (blk_id, port) in folded_blocks:
                net[index] = folded_blocks[blk_id]
                continue
            if blk_id[0] == "c" or blk_id[0] == "b":
                # FIXME:
                # it happens when a const connected to something
                # we don't care about yet
                if next_blk is None:
                    nets_to_remove.add(net_id)
                    break
                assert (next_blk is not None and
                        next_blk[0] != "c" and next_blk[0] != "r"
                        and next_blk[0] != "b")
                # absorb blk to the next one
                remove_blks.add((blk_id, id_to_name[next_blk], port))
                folded_blocks[(blk_id, port)] = (next_blk, id_to_name[blk_id],
                                                 next_port)
                # override the port to its name with index
                net[next_index] = (next_blk, id_to_name[blk_id])
            # NOTE:
            # disable reg folding to the same block that i's connected to
            elif blk_id[0] == "r":
                if blk_id not in dont_absorb and next_blk is not None and  \
                        len(net) == 2:
                    # only PE blocks can absorb registers
                    new_port = next_port
                    remove_blks.add((blk_id, id_to_name[next_blk], port))
                    folded_blocks[(blk_id, port)] = (next_blk, new_port)
                    # override the port to reg
                    net[next_index] = (next_blk, new_port)
                elif blk_id in dont_absorb:
                    changed_pe.add(blk_id)

        for entry in remove_blks:
            blk_id = entry[0]
            # print("Absorb", id_to_name[blk_id], "to", entry[1])
            item = (entry[0], entry[2])
            net.remove(item)
            assert (blk_id not in changed_pe)

        assert(len(net) > 0)

        # remove netlists
        if len(net) == 1:
            # a net got removed
            nets_to_remove.add(net_id)

    for net_id in nets_to_remove:
        # print("Remove net_id:", net_id, "->".join(
        #     ["{}::{}".format(id_to_name[blk], port)
        #     for blk, port in raw_netlists[net_id]]), file=sys.stderr)
        raw_netlists.pop(net_id, None)

    # second pass to reconnect nets
    for net_id in raw_netlists:
        net = raw_netlists[net_id]
        for index, (blk_id, port) in enumerate(net):
            if port == "in" and (blk_id, "out") in folded_blocks:
                # replace with new folded blocks
                net[index] = folded_blocks[(blk_id, "out")]

    # Keyi:
    # Improved routing so that we are able to allow src -> reg -> reg
    # remove the code while keep it in the git history in case in the future
    # we do need this kind of way to cope with long reg chains.
    if fold_reg:
        # re-do the change_pe
        changed_pe.clear()

    for blk_id in changed_pe:
        print("Change", id_to_name[blk_id], "to a PE tile")
        # rewrite the nets
        for net_id in raw_netlists:
            net = raw_netlists[net_id]
            for index, (b_id, port) in enumerate(net):
                if b_id == blk_id and port == "in":
                    # always fold at data0 port
                    b_id = "p" + b_id[1:]
                    net[index] = (b_id, "data0")
                elif b_id == blk_id and port == "out":
                    b_id = "p" + b_id[1:]
                    net[index] = (b_id, "out")

    if fold_reg:
        # last pass to change any un-folded register's port to "reg"
        for net_id in raw_netlists:
            net = raw_netlists[net_id]
            for index, (blk_id, port) in enumerate(net):
                if blk_id[0] == "r" and blk_id not in changed_pe:
                    net[index] = (blk_id, "reg")
    else:
        assert (len(changed_pe) == len(dont_absorb))
        for net_id in raw_netlists:
            net = raw_netlists[net_id]
            for blk_id, port in net:
                assert (port != "reg")

    return raw_netlists, folded_blocks, changed_pe


def change_name_to_id(instances):
    name_to_id = {}
    id_count = 0
    instances_name = list(instances.keys())
    instances_name.sort()
    for name in instances_name:
        attrs = instances[name]
        if "genref" not in attrs:
            assert ("modref" in attrs)
            if attrs["modref"] == u"corebit.const":
                blk_type = "b"
            elif attrs["modref"] == u"cgralib.BitIO":
                blk_type = "i"
            elif attrs["modref"] == "alu_ns.PE" or attrs["modref"] == "lassen.PE":
                blk_type = "p"
            elif attrs["modref"] == "alu_ns.io16" or attrs["modref"] == "lassen.io16":
                blk_type = "I"
            else:
                raise Exception("Unknown instance type " + str(attrs))
        else:
            # TODO: stupid 1 bit IO thing need to take care of
            instance_type = attrs["genref"]
            if instance_type == "cgralib.PE":
                blk_type = "p"
            elif instance_type == "cgralib.IO":
                blk_type = "I"
            elif instance_type == "cgralib.Mem":
                blk_type = "m"
            elif instance_type == "coreir.const":
                blk_type = "c"
            elif instance_type == "coreir.reg":
                blk_type = "r"
            else:
                raise Exception("Unknown instance type", instance_type)
        blk_id = blk_type + str(id_count)
        id_count += 1
        name_to_id[name] = blk_id
    return name_to_id


def read_netlist_json(netlist_filename):
    assert (os.path.isfile(netlist_filename))
    with open(netlist_filename) as f:
        raw_data = json.load(f)
    namespace = raw_data["namespaces"]
    # load design names
    top = raw_data["top"].split(".")[-1]
    design = namespace["global"]["modules"][top]
    instances = design["instances"]
    connections = design["connections"]
    # the standard json input is not a netlist
    connections = convert2netlist(connections)
    return connections, instances


def load_unmapped_netlist(netlist_filename):
    with open(netlist_filename) as f:
        data = json.load(f)

    # load design names
    top = data["top"].split(".")[-1]
    design = data["namespaces"]["global"]["modules"][top]
    instances = design["instances"]
    connections = design["connections"]

    pe_count = 0
    name_to_id = {}
    for blk_name in instances:
        instance = instances[blk_name]
        if "genref" not in instance:
            assert "modref" in instance
            instance_type = instance["modref"]
        else:
            instance_type = instance["genref"]
        if instance_type == "coreir.mem":
            blk_type = "m"
        else:
            blk_type = "p"
        blk_id = blk_type + str(pe_count)
        pe_count += 1
        name_to_id[blk_name] = blk_id

    # produce the netlist
    io_count = 0
    connection_pairs = []
    io_names = {}
    for conn1, conn2 in connections:
        conn1_names = conn1.split(".")
        conn2_names = conn2.split(".")
        if len(conn2_names) != 2:
            if len(conn2_names) == 3:
                conn2_names.pop(2)
            assert len(conn2_names) == 2
        if len(conn1_names) != 2:
            if conn1_names[0] != "self":
                # print(conn1)
                continue
            assert conn1_names[0] == "self"
            if conn1 not in io_names:
                blk1_name = "io_" + str(io_count)
                blk1_id = "i" + str(io_count)
                io_count += 1
                name_to_id[blk1_name] = blk1_id
                io_names[conn1] = blk1_name
            else:
                blk1_name = io_names[conn1]

            port1 = conn1_names[1]
            assert port1 in ["in", "out"]
            # flip the port name
            if port1 == "in":
                port1 = "out"
            else:
                port1 = "in"
            blk1_id = name_to_id[blk1_name]
        else:
            blk1_id = name_to_id[conn1_names[0]]
            port1 = conn1_names[1]
        blk2_name, port2 = conn2_names
        blk2_id = name_to_id[blk2_name]
        connection_pairs.append([blk1_id + "." + port1, blk2_id + "." + port2])

    # convert to netlist
    temp_netlist = convert2netlist(connection_pairs)
    netlist = []
    for raw_net in temp_netlist:
        net = []
        for conn in raw_net:
            blk, port = conn.split(".")
            net.append((blk, port))
        netlist.append(net)

    # convert name_to_id to id_to_name
    id_to_name = {}
    for name in name_to_id:
        id_to_name[name_to_id[name]] = name

    return netlist, id_to_name


def save_unmapped_netlist(netlist_filename, packed_filename):
    raw_netlists, id_to_name = load_unmapped_netlist(netlist_filename)
    netlists = {}
    net_count = 0
    for net in raw_netlists:
        net_id = "e" + str(net_count)
        netlists[net_id] = net
        net_count += 1
    empty = {}
    write_packing_result(empty, empty, id_to_name, netlists,
                         packed_filename, empty)


if __name__ == "__main__" and len(sys.argv) == 3:
    save_unmapped_netlist(sys.argv[1], sys.argv[2])
