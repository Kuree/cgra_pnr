"""
This tool designed to pack as much as possible for CGRA, yet gives placer
and router flexibility to choose their algorithm.

Because the current CGRA flow does not have packing tools. This might be the
very first packing tools for AHA group
"""
from __future__ import print_function
import pickle
import json
import os
import sys

import networkx as nx


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


def save_packing_result(netlist_filename, pack_filename):
    netlists, folded_blocks, id_to_name = \
        parse_and_pack_netlist(netlist_filename)
    data = {"netlists": netlists,
            "folded_blocks": folded_blocks,
            "id_to_name": id_to_name}

    with open(pack_filename, "w+") as f:
        pickle.dump(data, f)


def load_packed_file(pack_filename):
    with open(pack_filename) as f:
        data = pickle.load(f)
    return data["netlists"], data["folded_blocks"], data["id_to_name"]


def parse_and_pack_netlist(netlist_filename):
    connections, instances = read_netlist_json(netlist_filename)
    netlists, name_to_id = generate_netlists(connections, instances)
    before_packing = len(netlists)
    netlists, folded_blocks = pack_netlists(netlists, name_to_id)
    after_packing = len(netlists)
    print("Before packing: num of netlists:", before_packing,
          "After packing: num of netlists:", after_packing)

    id_to_name = {}
    for name in name_to_id:
        id_to_name[name_to_id[name]] = name
    return netlists, folded_blocks, id_to_name


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
            if port == "ren" or port == "cg_en":
                continue

            if port == "data.in.0":
                port = "data0"
            elif port == "data.in.1":
                port = "data1"
            elif port == "in":
                # either a reg or IO
                if "reg" in blk_name:
                    port = "reg"
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
            elif "out" in port:
                port = "out"
            else:
                raise Exception("Unrecognized port " + port)
            hyper_edge.append((blk_id, port))
        netlists[edge_id] = hyper_edge
    return netlists, name_to_id


def pack_netlists(raw_netlists, name_to_id):
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
                folded_blocks[(blk_id, port)] = (next_blk, id_to_name[blk_id])
                # override the port to its name with index
                net[next_index] = (next_blk, id_to_name[blk_id])
            # NOTE:
            # disable reg folding to the same block that i's connected to
            elif blk_id[0] == "r":
                if blk_id not in dont_absorb and next_blk is not None:
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
            print("Absorb", id_to_name[blk_id], "to", entry[1])
            item = (entry[0], entry[2])
            net.remove(item)
            if blk_id in changed_pe:
                # this is actually can be folded
                changed_pe.remove(blk_id)
        assert(len(net) > 0)
        #if len(net) == 1:
        #    # a net got removed
        #    netlists_to_remove.add(net_id)

    for net_id in nets_to_remove:
        print("Remove net_id:", net_id, "->".join(
            ["{}::{}".format(id_to_name[blk], port)
             for blk, port in raw_netlists[net_id]]))
        raw_netlists.pop(net_id, None)

    # second pass to reconnect nets
    for net_id in raw_netlists:
        net = raw_netlists[net_id]
        for index, (blk_id, port) in enumerate(net):
            if port == "reg" and (blk_id, "out") in folded_blocks:
                # replace with new folded blocks
                net[index] = folded_blocks[(blk_id, "out")]

    for blk_id in changed_pe:
        print("Change", id_to_name[blk_id], "to a PE tile")
        # rewrite the nets
        for net_id in raw_netlists:
            net = raw_netlists[net_id]
            for index, (b_id, port) in enumerate(net):
                if b_id == blk_id and port == "reg":
                    # always fold at data0 port
                    net[index] = (blk_id, "data0")

    # sanity check. shouldn't be any reg left
    assert(len(changed_pe) == len(dont_absorb))
    for net_id in raw_netlists:
        net = raw_netlists[net_id]
        for blk_id, port in net:
            assert (port != "reg")

    return raw_netlists, folded_blocks


def change_name_to_id(instances):
    name_to_id = {}
    id_count = 0
    for name in instances:
        attrs = instances[name]
        if "genref" not in attrs:
            assert ("modref" in attrs)
            assert (attrs["modref"] == u"corebit.const")
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
    design = namespace["global"]["modules"]["DesignTop"]
    instances = design["instances"]
    connections = design["connections"]
    # the standard json input is not a netlist
    connections = convert2netlist(connections)
    return connections, instances
