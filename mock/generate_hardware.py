from __future__ import division
from __future__ import print_function
from lxml import etree
from argparse import ArgumentParser


def revert_direction(direction):
    if direction == 0:
        return 2
    elif direction == 1:
        return 3
    elif direction == 2:
        return 0
    elif direction == 3:
        return 1
    raise Exception("Unknown direction " + str(direction))


def convert_conn_to_str(bus, direction, side, track):
    if direction == 0:
        return "in_{0}BIT_S{1}_T{2}".format(bus, side, track)
    elif direction == 1:
        return "out_{0}BIT_S{1}_T{2}".format(bus, side, track)
    else:
        raise Exception("Unknown direction " + str(direction))


def write_cb(element, num_chan, sinks):
    for sink in sinks:
        bus = sinks[sink][0]
        dir_collections = sinks[sink][1]
        cb_elem = etree.SubElement(element, "cb")
        cb_elem.attrib["bus"] = "BUS{}".format(bus)
        mux = etree.SubElement(cb_elem, "mux")
        mux.attrib["snk"] = sink
        for direction, side in dir_collections:
            for chan in range(num_chan):
                src_elem = etree.SubElement(mux, "src")
                src_elem.text = convert_conn_to_str(bus, direction, side, chan)


def write_sb(parent, bus, sources, num_chan):
    sb = etree.SubElement(parent, "sb")
    sb.attrib["bus"] = "BUS{}".format(bus)
    for chan in range(num_chan):
        for side in range(4):
            mux = etree.SubElement(sb, "mux")
            mux.attrib["snk"] = convert_conn_to_str(bus, 1, side, chan)
            for i in range(4):
                if i == side:
                    continue    # you can't can't go back
                src = etree.SubElement(mux, "src")
                src.text = convert_conn_to_str(bus, 0, i, chan)
            # sources
            for src in sources:
                links = sources[src]
                if (1, side) in links:
                    # connect them!
                    src_elem = etree.SubElement(mux, "src")
                    src_elem.text = src


def write_io(root, x, y, num_chan, tile_address, margin, size):
    element = etree.SubElement(root, "tile")
    element.attrib["type"] = "io1bit"
    element.attrib["tile_addr"] = "0x{0:04X}".format(tile_address)
    element.attrib["row"] = str(y)
    element.attrib["col"] = str(x)

    # really don't care about its name
    element.attrib["name"] = "pad_{0:x}".format(tile_address)

    # io bit and group are just for the bitstream generator,
    # doesn't have to be accurate
    io_bit = etree.SubElement(element, "io_bit")
    io_bit.text = str(tile_address % 16)
    io_group = etree.SubElement(element, "io_group")
    io_group.text = str(tile_address // 16)

    # based on pos, compute output directions
    out_direction = -1
    if x == margin - 1:
        out_direction = 0
    elif x == size + margin:
        out_direction = 2
    elif y == margin - 1:
        out_direction = 1
    elif y == size + margin:
        out_direction = 3
    assert out_direction != -1
    # write tri info
    tri = etree.SubElement(element, "tri")
    elem_in = etree.SubElement(tri, "direction")
    elem_in.text = "in"
    elem_out = etree.SubElement(tri, "direction")
    elem_out.text = "out"

    # 1 bit
    elem = etree.SubElement(element, "f2p_1bit")
    # we only write 1 bit for io on track 0
    elem.text = convert_conn_to_str(1, 0, out_direction, 0)
    for i in range(num_chan):
        elem = etree.SubElement(element, "p2f_1bit")
        elem.text = convert_conn_to_str(1, 1, out_direction, i)

    # 16 bit
    elem = etree.SubElement(element, "f2p_wide")
    # we only write 16 bit for io on track 0
    elem.text = convert_conn_to_str(16, 0, out_direction, 0)
    for i in range(num_chan):
        elem = etree.SubElement(element, "p2f_wide")
        elem.text = convert_conn_to_str(16, 1, out_direction, i)


def write_empty(root, x, y):
    element = etree.SubElement(root, "tile")
    element.attrib["type"] = "empty"
    element.attrib["tile_addr"] = "0x{0:04X}".format(0)
    element.attrib["row"] = str(y)
    element.attrib["col"] = str(x)


def write_mem(root, x, y, num_chan, tile_address, wdata_dir, wen_dir,
              rdata_dir):
    element = etree.SubElement(root, "tile")
    element.attrib["type"] = "memory_tile"
    element.attrib["tile_addr"] = "0x{0:04X}".format(tile_address)
    element.attrib["row"] = str(y)
    element.attrib["col"] = str(x)

    sinks = {"wdata": (16, wdata_dir), "wen": (1, wen_dir)}
    write_cb(element, num_chan, sinks)

    # sb
    sources = {"rdata": rdata_dir}
    write_sb(element, 16, sources, num_chan)
    sources = {"valid": ((1, 0), (1, 1), (1, 2), (1, 3))}
    write_sb(element, 1, sources, num_chan)


def write_pe(root, x, y, num_chan, tile_addr, bit0_dir, bit1_dir, bit2_dir,
             data0_dir, data1_dir, pe_out_dir):
    element = etree.SubElement(root, "tile")
    element.attrib["type"] = "pe_tile_new"
    element.attrib["tile_addr"] = "0x{0:04X}".format(tile_addr)
    element.attrib["row"] = str(y)
    element.attrib["col"] = str(x)

    sinks = {"bit0": (1, bit0_dir), "bit1": (1, bit1_dir),
             "bit2": (1, bit2_dir), "data0": (16, data0_dir),
             "data1": (16, data1_dir)}
    write_cb(element, num_chan, sinks)
    sources = {"pe_out_res_p": pe_out_dir}
    write_sb(element, 16, sources, num_chan)
    write_sb(element, 1, sources, num_chan)


def determine_io_pos(num_io, pe_margin, size):
    io_pos = set()
    for i in range(num_io):
        offset = i // 8
        if i % 4 == 0:
            # top left corner. e.g., (1, 2) and (2, 1)
            # when margin is 2, and size is 16
            if i % 8 == 4:
                io_pos.add((pe_margin - 1, pe_margin + offset))
            else:
                io_pos.add((pe_margin + offset, pe_margin - 1))
        elif i % 4 == 1:
            # top right corner. e.g. (18, 2) and (17, 1)
            # when margin is 2, and size is 16
            if i % 8 == 5:
                io_pos.add((pe_margin + size - 1 - offset, pe_margin - 1))
            else:
                io_pos.add((pe_margin + size, pe_margin + offset))
        elif i % 4 == 2:
            # bottom left corner. e.g. (2, 18) and (1, 17)
            # when margin is 2, and size is 16
            if i % 8 == 6:
                io_pos.add((pe_margin + offset, pe_margin + size))
            else:
                io_pos.add((pe_margin - 1, pe_margin + size - offset - 1))
        elif i % 4 == 3:
            # bottom right corner. e.g. (18, 17) and (17, 18)
            # when margin is 2 and size is 16
            if i % 8 == 7:
                io_pos.add((pe_margin + size - 1 - offset, pe_margin + size))
            else:
                io_pos.add((pe_margin + size, pe_margin + size - offset - 1))
    return io_pos


def main():
    parser = ArgumentParser("Mock CGRA Generator. Please note that due to" +
                            " different IO pad \nplacement scheme, " +
                            "it cannot be used in the actual CGRAFlow.")
    parser.add_argument("-s", "--size", help="Board size (counting PE tiles)",
                        default=16, type=int, action="store", dest="size")
    parser.add_argument("--mem_start", help="Actual index about where MEM " +
                                            "tiles starts (including margin)",
                        default=5, type=int, action="store", dest="mem_start")
    parser.add_argument("--mem_repeat", help="How many columns will MEM tiles" +
                                             "be repeatedly placed on",
                        default=4, type=int, action="store", dest="mem_repeat")
    parser.add_argument("--pe_margin", help="How much padding space " +
                                            "(including IO) for PE tiles",
                        default=1, type=int, action="store", dest="pe_margin")
    parser.add_argument("--num_track", "--num_chan", help="Number of " +
                        "tracks/channels will be used in routing",
                        default=5, type=int, action="store", dest="num_chan")
    parser.add_argument("--num_io", help="Number of 16 bit IO tiles",
                        default=4, type=int, action="store", dest="num_io")
    parser.add_argument("-o", "--output", help="Output architecture file",
                        required=True, type=str, action="store",
                        dest="output_file")

    args = parser.parse_args()
    size = args.size
    mem_start = args.mem_start
    mem_repeat = args.mem_repeat
    pe_margin = args.pe_margin
    num_chan = args.num_chan
    num_io = args.num_io
    output_file = args.output_file

    # pe operand channels
    # (in, side)
    data0_dir = ((0, 2), (1, 2))
    data1_dir = ((0, 1), (1, 1))
    bit0_dir = ((0, 2), (1, 2))
    bit1_dir = ((0, 1), (1, 1))
    bit2_dir = ((0, 2), (1, 2))
    pe_out_dir = ((1, 0), (1, 1), (1, 2), (1, 3))

    # memory
    wdata_dir = ((0, 2), (1, 2))
    wen_dir = ((0, 2), (1, 2))
    rdata_dir = ((1, 0), (1, 1), (1, 2), (1, 3))

    # compute io tile address
    io_pos = determine_io_pos(num_io, pe_margin, size)

    # generate the doc
    root = etree.Element("CGRA")
    for y in range(size + pe_margin * 2):
        for x in range(size + pe_margin * 2):
            tile_addr = (y << 8) + x
            if (x, y) in io_pos:
                write_io(root, x, y, num_chan, tile_addr, pe_margin, size)
                continue
            if x < pe_margin or y < pe_margin or x >= pe_margin + size or \
               y >= pe_margin + size:
                write_empty(root, x, y)
                continue
            if (x - mem_start) % mem_repeat == 0:
                # mem tiles
                write_mem(root, x, y, num_chan, tile_addr, wdata_dir,
                          wen_dir, rdata_dir)
                continue
            # the rest is pe tiles
            write_pe(root, x, y, num_chan, tile_addr, bit0_dir,
                     bit1_dir, bit2_dir, data0_dir, data1_dir,
                     pe_out_dir)

    with open(output_file, "wb+") as f:
        s = etree.tostring(root, pretty_print=True)
        f.write(s)
        print("CGRA architecture file generated to", output_file)


if __name__ == '__main__':
    main()
