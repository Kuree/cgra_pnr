from __future__ import print_function
from lxml import etree
import sys
import os
import pythunder


"""
Arch parser that supports different type of circuits, i.e., either FPGA (VPR)
or CGRA
"""


def convert_vpr_type(vpr_type):
    if vpr_type == "io":
        return 'i'
    elif vpr_type == "EMPTY":
        return None
    elif vpr_type == "clb":
        return "c"
    elif vpr_type == "mult_36":
        return "u"
    elif vpr_type == "memory":
        return "m"
    else:
        # unknown type
        return None


def parse_vpr(filename):
    root = etree.parse(filename)
    # we are only interested in the fixed layout
    layouts = {}
    for layout in root.iter("fixed_layout"):
        layout_attr = layout.attrib
        layout_name = layout_attr["name"]
        width = int(layout_attr["width"])
        height = int(layout_attr["height"])

        # create the board
        layout_board = []
        for h in range(height):
            row = [None] * width
            layout_board.append(row)

        available_blk_types = set()
        # filling in tile types
        # fill first
        fill_priority = 0
        for fill in layout.iter("fill"):
            priority = int(fill.attrib["priority"])
            if priority < fill_priority:
                continue
            else:
                fill_priority = priority
            raw_blk_type = fill.attrib["type"]
            blk_type = convert_vpr_type(raw_blk_type)
            available_blk_types.add(blk_type)
            for y in range(height):
                for x in range(width):
                    layout_board[y][x] = blk_type

        peri_priority = fill_priority
        for peri in layout.iter("perimeter"):
            priority = int(peri.attrib["priority"])
            if priority < peri_priority:
                continue
            else:
                # update the priority
                peri_priority = priority
            raw_blk_type = peri.attrib["type"]
            blk_type = convert_vpr_type(raw_blk_type)
            available_blk_types.add(blk_type)
            # fill in
            for x in range(width):
                layout_board[0][x] = blk_type
                layout_board[height - 1][x] = blk_type
            for y in range(height):
                layout_board[y][0] = blk_type
                layout_board[y][width - 1] = blk_type
        corners_priority = fill_priority
        for corners in layout.iter("corners"):
            priority = int(corners.attrib["priority"])
            if priority < corners_priority:
                continue
            else:
                # update the priority
                corners_priority = priority
            raw_blk_type = corners.attrib["type"]
            blk_type = convert_vpr_type(raw_blk_type)
            available_blk_types.add(blk_type)
            layout_board[0][0] = blk_type
            layout_board[0][width - 1] = blk_type
            layout_board[height - 1][0] = blk_type
            layout_board[height - 1][width - 1] = blk_type

        cols_priority = {}
        for col in layout.iter("col"):
            priority = int(col.attrib["priority"])
            startx = int(col.attrib["startx"])
            if (startx in cols_priority and
                priority < cols_priority[startx]) or \
               (priority < fill_priority):
                continue
            else:
                cols_priority[startx] = priority
            starty = int(col.attrib["starty"])
            repeatx = int(col.attrib["repeatx"])
            raw_blk_type = col.attrib["type"]
            blk_type = convert_vpr_type(raw_blk_type)
            available_blk_types.add(blk_type)
            xx = startx
            while xx < width:
                # we have peri defined already
                for y in range(starty, height - 1):
                    layout_board[y][xx] = blk_type
                xx += repeatx

        # need to figure out the height
        # we are not concerned with routing in VPR for now
        blk_height = {}
        blk_capacity = {}
        for blk_type in available_blk_types:
            blk_height[blk_type] = 1
            blk_capacity[blk_type] = 1

        # search for blk heights
        for directlist in root.iter("complexblocklist"):
            for pb_type in directlist.iter("pb_type"):
                pb_name = pb_type.attrib["name"]
                blk_type = convert_vpr_type(pb_name)
                if blk_type not in available_blk_types:
                    continue
                if "height" in pb_type.attrib:
                    pb_height = int(pb_type.attrib["height"])
                    blk_height[blk_type] = pb_height
                if "capacity" in pb_type.attrib:
                    pb_capacity = int(pb_type.attrib["capacity"])
                    blk_capacity[blk_type] = pb_capacity
            break

        # some other info that's useful for SA placer
        layout = get_layout(layout_board)

        layouts[layout_name] = layout
    return layouts


def convert_cgra_type(tile_type):
    if tile_type == "pe_tile_new":
        return 'p'
    elif tile_type == "memory_tile":
        return 'm'
    elif tile_type == "empty":
        return None
    elif tile_type == "io1bit":
        return 'i'
    elif tile_type == "io16bit":
        return 'I'
    else:
        raise Exception("Unknown tile type " + tile_type)


def get_layout(board_layout):
    new_layout = []
    for y in range(len(board_layout)):
        row = []
        for x in range(len(board_layout[y])):
            if board_layout[y][x] is None:
                row.append(' ')
            else:
                row.append(board_layout[y][x])
        new_layout.append(row)

    default_priority = pythunder.Layout.DEFAULT_PRIORITY
    # not the best practice to use the layers here
    # but this requires minimum amount of work to convert the old
    # code to the new codebase
    # FIXME: change the CGRA_INFO parser to remove the changes
    layout = pythunder.Layout(new_layout)
    # add a reg layer to the layout, the same as PE
    clb_layer = layout.get_layer('p')
    reg_layer = pythunder.Layer(clb_layer)
    reg_layer.blk_type = 'r'
    layout.add_layer(reg_layer, default_priority, 0)
    # bit_layer = pythunder.Layer(clb_layer)
    # bit_layer.blk_type = "B"
    # layout.add_layer(bit_layer, default_priority, 1)
    # set different layer priorities
    layout.set_priority_major(' ', 0)
    layout.set_priority_major('i', 1)
    layout.set_priority_major("I", 2)
    # memory is a DSP-type, so lower priority
    layout.set_priority_major('m', default_priority - 1)
    return layout

def set_io_mask(layout, io_mask_table):
    mask = pythunder.LayerMask()
    mask.blk_type = "I"
    mask.mask_blk_type = "i"
    io16_layer = layout.get_layer("I")
    io16_pos = io16_layer.produce_available_pos()
    for _, pos_list in io_mask_table.items():
        for pos in io16_pos:
            if pos in pos_list:
                io1bit = []
                for b1_pos in pos_list:
                    io1bit.append(b1_pos)
                mask.add_mask_pos(pos, io1bit)
                io16_pos.remove(pos)
    layout.add_layer_mask(mask)


def parse_cgra(filename, use_tile_addr=False):
    root = etree.parse(filename)
    layout_name = "CGRA"
    # only one layout in CGRA files
    board_dict = {}     # because CGRA file doesn't tell the size beforehand
    available_types = set()
    tile_mapping = {}
    io_pad_name = {}
    io_pad_bit = {}
    io16_tile = {}
    io_mask_table = {}

    for tile in root.iter("tile"):
        if "type" not in tile.attrib or tile.attrib["type"] == "gst":
            continue
        tile_type = tile.attrib["type"]
        x = int(tile.attrib["col"])
        y = int(tile.attrib["row"])
        tile_addr = int(tile.attrib["tile_addr"], 16)
        blk_type = convert_cgra_type(tile_type)
        board_dict[(x, y)] = blk_type
        available_types.add(blk_type)
        tile_mapping[(x, y)] = tile_addr
        # figure out where the 16 bit IO tiles
        if tile_type == "io1bit":
            # only 16 bit IO tiles has this
            if tile.find("p2f_wide") is not None:
                board_dict[(x, y)] = "I"
            pad_name = tile.attrib["name"]
            io_pad_name[(x, y)] = pad_name
            # obtain the io pad bit number
            io_bit_elem = tile.find("io_bit")
            assert io_bit_elem is not None
            io_pad_bit[(x, y)] = io_bit_elem.text

            # add it to the io 16 tiles
            if pad_name not in io16_tile:
                io16_tile[pad_name] = []
                io_mask_table[pad_name] = []
            io16_tile[pad_name].append(tile_addr)
            io_mask_table[pad_name].append((x, y))

    positions = list(board_dict.keys())
    positions.sort(key=lambda entry: entry[0], reverse=True)
    width = positions[0][0] + 1
    positions.sort(key=lambda entry: entry[1], reverse=True)
    height = positions[0][1] + 1
    layout_board = []
    for h in range(height):
        row = [' '] * width
        layout_board.append(row)
    for x, y in board_dict:
        layout_board[y][x] = board_dict[(x, y)]

    blk_height = {}
    blk_capacity = {}
    for blk in available_types:
        blk_height[blk] = 1
        blk_capacity[blk] = 1

    info = {"io_pad_name": io_pad_name,
            "io_pad_bit": io_pad_bit, "io16_tile": io16_tile}

    # NOTE:
    # the CGRA file sets the height for each tiles implicitly
    # no need to worry about the height
    layouts = {}
    layout = get_layout(layout_board)
    set_io_mask(layout, io_mask_table)
    if use_tile_addr:
        layouts[layout_name] = (layout, info,
                                tile_mapping)
    else:
        layouts[layout_name] = layout
    return layouts


def parse_fpga(fpga_file):
    """parse ISPD FPGA benchmark"""
    with open(fpga_file) as f:
        lines = f.readlines()

    board_layout = []

    io_tiles = set()
    read_site = False

    for line in lines:
        if not read_site:
            if "SITEMAP" in line:
                read_site = True
                _, raw_width, raw_height = line.split()
                width = int(raw_width)
                height = int(raw_height)
                for j in range(height):
                    row = [None] * width
                    board_layout.append(row)
        else:
            line = line.strip()
            if len(line) == 0 or "END" in line:
                break
            raw_x, raw_y, site_type = line.split()
            x = int(raw_x)
            y = int(raw_y)
            if site_type == "IO":
                board_layout[y][x] = "i"
                io_tiles.add((x, y))
            elif site_type == "SLICE":
                board_layout[y][x] = "c"
            elif site_type == "BRAM":
                board_layout[y][x] = "m"
            elif site_type == "DSP":
                board_layout[y][x] = "d"
            else:
                raise Exception("Unknown SITE " + site_type)
    layout_name = "fpga"
    layouts = {layout_name: pythunder.Layout(board_layout)}
    return layouts


def main():
    use_vpr = False
    use_cgra = False
    use_fpga = False
    if len(sys.argv) < 2:
        print("Usage:", sys.argv[0], "[OPTION]", "<arch_file>",
              "\n[OPTION]: -vpr, -cgra", file=sys.stderr)
        exit(1)
    elif len(sys.argv) > 2:
        for opt in sys.argv[1:]:
            if opt == "-vpr":
                use_cgra = False
                break
            elif opt == "-cgra":
                use_cgra = True
                break
            elif opt == "-fpga":
                use_fpga = True
                break
    filename = sys.argv[1]
    if (not use_vpr) and (not use_cgra) and not use_fpga:
        _, ext = os.path.splitext(filename)
        if ext == ".xml":
            use_vpr = True
        elif ext == ".txt":
            use_cgra = True
        elif ext == ".scl":
            use_fpga = True
    layout = None
    if use_vpr:
        print("Parsing VPR arch file", filename)
        layout = parse_vpr(filename)
    if use_cgra:
        print("Parsing CGRA arch file", filename)
        layout = parse_cgra(filename)
    if use_fpga:
        print("Parsing FPGA arch file", filename)
        layout = parse_fpga(filename)
    if layout is None:
        print("Unexpected state", file=sys.stderr)
        exit(1)
    for board_name in layout:
        print(layout[board_name])


if __name__ == "__main__":
    main()
