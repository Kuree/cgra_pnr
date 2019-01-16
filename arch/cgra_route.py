from __future__ import print_function
from lxml import etree
import sys


def parse_routing_resource(cgra_file):
    """build routing resource files based on the CGRA definition
       returns resources indexed by """
    root = etree.parse(cgra_file)
    result = {}
    for tile_elem in root.iter("tile"):
        tile_attr = tile_elem.attrib
        if tile_attr["type"] == "gst":
            # don't care about gst for now
            break
        address = int(tile_attr["tile_addr"], 16)
        # random gst stuff
        if "row" not in tile_attr:
            raise Exception("Unable to find row/col at tile " + str(address))
        row = int(tile_attr["row"])
        col = int(tile_attr["col"])
        # get tri elem
        tri = tile_elem.find("tri")
        if tri is None:
            # more complicated routing is here

            # connection box
            cb_bus = {}
            for cb_elem in tile_elem.iter("cb"):
                bus = cb_elem.attrib["bus"]
                mux_elem = cb_elem.find("mux")
                if mux_elem is None:
                    raise Exception("mux is none for tile " + str(address))
                sink = mux_elem.attrib["snk"]
                sink_connections = set()
                # find all tracks connected to the sink
                for src_elem in mux_elem.iter("src"):
                    sink_connections.add(src_elem.text)

                # add it to cb bus collection
                if bus not in cb_bus:
                    cb_bus[bus] = {}
                cb_bus[bus][sink] = sink_connections

            # switch box
            sb_bus = {}
            for sb_elem in tile_elem.iter("sb"):
                bus = sb_elem.attrib["bus"]
                sb_entry = {"mux": {}, "reg": set()}
                # we will have reg and mux
                for mux_elem in sb_elem.iter("mux"):
                    sink = mux_elem.attrib["snk"]
                    sink_connections = set()
                    # find all tracks connected to the sink
                    for src_elem in mux_elem.iter("src"):
                        sink_connections.add(src_elem.text)
                    sb_entry["mux"][sink] = sink_connections
                for reg_elem in sb_elem.iter("reg"):
                    src = reg_elem.attrib["src"]
                    sb_entry["reg"].add(src)

                if bus in sb_bus:
                    sb_bus[bus]["mux"].update(sb_entry["mux"])
                    sb_bus[bus]["reg"] = sb_bus[bus]["reg"].union(
                        sb_entry["reg"]
                    )
                else:
                    sb_bus[bus] = sb_entry

            # put into result, using (col, row) as an index
            result[(col, row)] = {"cb": cb_bus, "sb": sb_bus}

        else:
            # IO direction
            io_entry = {}
            directions = set()
            for direction in tri.iter("direction"):
                directions.add(direction.text)
            io_entry["directions"] = directions

            # IO input and outputs
            input_elem = tile_elem.find("f2p_1bit")
            assert input_elem is not None, "tile " + str(address) + \
                                           " does not have f2p_1bit element"

            io_entry["input"] = set()
            io_entry["input"].add(input_elem.text)
            io_entry["output"] = set()
            for output_elem in tile_elem.iter("p2f_1bit"):
                io_entry["output"].add(output_elem.text)

            # 16 bit IO
            if tile_elem.find("p2f_wide") is not None:
                for elem in tile_elem.findall("p2f_wide"):
                    io_entry["output"].add(elem.text)
                assert tile_elem.find("f2p_wide") is not None
                for elem in tile_elem.findall("f2p_wide"):
                    io_entry["input"].add(elem.text)
            else:
                assert tile_elem.find("p2f_1bit") is not None
                for elem in tile_elem.findall("p2f_1bit"):
                    io_entry["output"].add(elem.text)
                assert tile_elem.find("f2p_1bit") is not None
                for elem in tile_elem.findall("f2p_1bit"):
                    io_entry["input"].add(elem.text)

            result[(col, row)] = io_entry
    return result


def convert_bus_to_tuple(wire):
    raw_data = wire.split("_")
    # Keyi: whoever did this doesn't think the naming through.
    side_offset = 0
    if len(raw_data) == 7:
        if raw_data[0] == "sb" and raw_data[1] == "wire":
            # e.g. 'sb_wire_out_1_BUS16_S3_T4'
            raw_data.pop(0)
            raw_data.pop(0)
    if len(raw_data) == 5:
        if raw_data[0] in ["in", "out"]:
            row_index = int(raw_data[1])
            if row_index == 1:
                side_offset += 4
            raw_data.pop(1)
    # TODO: FIX THIS
    if len(raw_data) != 4:
        return None
    if raw_data[0] == "in":
        in_out = 0
    elif raw_data[0] == "out":
        in_out = 1
    elif raw_data[0] == "pe":
        return None
    else:
        raise Exception("Unknown wire " + wire)
    if raw_data[1][:3] == "BUS":
        bus = int(raw_data[1][3:])
    elif raw_data[1][-3:] == "BIT":
        bus = int(raw_data[1][0:len(raw_data[1]) - 3])
    else:
        raise Exception("Unknown BUS " + raw_data[1][:3])
    assert(raw_data[2][0] == "S")
    assert(len(raw_data[2]) == 2)
    side = int(raw_data[2][1]) + side_offset
    assert(raw_data[3][0] == "T")
    assert(len(raw_data[3]) == 2)
    track = int(raw_data[3][1])

    return bus, in_out, side, track


def build_routing_resource(parsed_resource):
    """build routing resource so that we can pass it to a generic router
       raw string representation will be changed to
       (bus, in/out, side, track), which can be directly used in the bitstream
       generator
    """
    # indexed by pos (x, y)
    result = {}
    for x, y in parsed_resource:
        entry = parsed_resource[(x, y)]
        if "cb" not in entry:
            # io entry
            operands = {"in": set(), "out": set(), "inb": set(), "outb": set()}
            port_io = {"in": 0, "out": 1, "inb": 0, "outb": 1}
            input_channels = entry["input"]
            output_channels = entry["output"]
            for wire_info in input_channels:
                wire = convert_bus_to_tuple(wire_info)
                if wire is not None:
                    assert wire[1] == 0
                    if wire[0] == 1:
                        sink = "inb"
                    else:
                        sink = "in"
                    operands[sink].add(wire)
            for wire_info in output_channels:
                wire = convert_bus_to_tuple(wire_info)
                if wire is not None:
                    assert wire[1] == 1
                    if wire[0] == 1:
                        sink = "outb"
                    else:
                        sink = "out"
                    operands[sink].add(wire)

            # clean up
            if len(operands["out"]) == 0:
                operands.pop("out", None)
            if len(operands["outb"]) == 0:
                operands.pop("outb", None)
            if len(operands["in"]) == 0:
                operands.pop("in", None)
            if len(operands["inb"]) == 0:
                operands.pop("inb", None)

            result[(x, y)] = {"route_resource": set(),
                              "port": operands,
                              "port_io": port_io}
            continue
        # build operand connection
        operands = {"out": set(), "outb": set(), "rdata": set(), "valid": set()}
        port_io = {}
        for port in operands:
            port_io[port] = 1
        connections = {}
        for bus in entry["cb"]:
            for sink in entry["cb"][bus]:
                assert sink not in operands
                operands[sink] = set()
                wires = entry["cb"][bus][sink]
                for wire in wires:
                    wire_info = convert_bus_to_tuple(wire)
                    if wire_info is not None:
                        operands[sink].add(wire_info)
                        port_io[sink] = 0

        for bus in entry["sb"]:
            muxes = entry["sb"][bus]["mux"]
            for sink in muxes:
                sink_wire = convert_bus_to_tuple(sink)
                if sink not in connections:
                    connections[sink] = set()
                for wire in muxes[sink]:
                    sink_info = convert_bus_to_tuple(wire)
                    if sink_info is not None:
                        connections[sink].add(sink_info)
                    elif wire == "pe_out_res":
                        operands["out"].add(sink_wire)
                    elif wire == "pe_out_res_p":
                        operands["outb"].add(sink_wire)
                    elif wire == "rdata":
                        operands["rdata"].add(sink_wire)
                    elif wire == "valid":
                        operands["valid"].add(sink_wire)

        if len(operands["out"]) == 0:
            operands.pop("out", None)
        if len(operands["rdata"]) == 0:
            operands.pop("rdata", None)
        if len(operands["valid"]) == 0:
            operands.pop("valid", None)

        # build real routing resources on the chip
        route_resource = set()
        for w1 in connections:
            w1_info = convert_bus_to_tuple(w1)
            for w2 in connections[w1]:
                # NOTE:
                # we might not use all the mem routing resource, which allows
                # in -> in on different rows
                route_resource.add((w2, w1_info))
        result[(x, y)] = {"route_resource": route_resource,
                          "port": operands,
                          "port_io": port_io}

    return result


def simple_route_stats(parsed_routing_resource):
    """This one takes parsed routing resource, not the ones
       built for router
    """
    buses = {}
    for x, y in parsed_routing_resource:
        entry = parsed_routing_resource[(x, y)]
        if "sb" not in entry:
            continue
        for bus in entry["sb"]:
            if bus not in buses:
                buses[bus] = 0
            muxes = entry["sb"][bus]["mux"]
            for sink in muxes:
                buses[bus] += len(muxes[sink])
    for bus in buses:
        print(bus + ":", "Num of SB connections:", buses[bus])

    # compute routing resources
    r = build_routing_resource(parsed_routing_resource)
    routable_channel = 0
    operand_connection = 0
    for x, y, in r:
        entry = r[(x, y)]
        routable_channel += len(entry["route_resource"])
        operand_connection += len(entry["operand"])
    print("Routable channel pairs (A -> B):", routable_channel)
    print("Operand channels: (A -> OP)", operand_connection)


def main():
    if len(sys.argv) != 2:
        print("Usage", sys.argv[0], "<cgra_info>", file=sys.stderr)
        exit(0)
    r = parse_routing_resource(sys.argv[1])
    simple_route_stats(r)
    build_routing_resource(r)


if __name__ == "__main__":
    main()
