from __future__ import print_function
from lxml import etree
import sys
import os


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
        # fillling in tile types
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
            raw_blk_type == corners.attrib["type"]
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
            if (startx in cols_priority and priority < cols_priority[startx]) or \
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
        info = {"margin": 1, "clb_type": 'c', "arch_type": "fpga"}
        layouts[layout_name] = (layout_board, blk_height, blk_capacity,
                                info)
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
        # TODO:
        # maybe a different one?
        return 'i'
    else:
        raise Exception("Unknown tile type " + tile_type)

def parse_cgra(filename):
    root = etree.parse(filename)
    layout_name = "CGRA"
    # only one layout in CGRA files
    board_dict = {}     # because CGRA file doesn't tell the size beforehand
    available_types = set()
    for tile in root.iter("tile"):
        if "type" not in tile.attrib or tile.attrib["type"] == "gst":
            continue
        tile_type = tile.attrib["type"]
        x = int(tile.attrib["col"])
        y = int(tile.attrib["row"])
        # TODO
        # need to parse track info for routing
        blk_type = convert_cgra_type(tile_type)
        board_dict[(x, y)] = blk_type
        available_types.add(blk_type)
    positions = list(board_dict.keys())
    positions.sort(key=lambda pos: pos[0] + pos[1], reverse=True)
    pos = positions[0]
    width, height = pos[0] + 1, pos[1] + 1
    layout_board = []
    for h in range(height):
        row = [None] * width
        layout_board.append(row)
    for x, y in board_dict:
        layout_board[y][x] = board_dict[(x, y)]

    blk_height = {}
    blk_capacity = {}
    for blk in available_types:
        blk_height[blk] = 1
        blk_capacity[blk] = 1

    # find pe margin
    pe_margin = -1
    for ii in range(min(height, height)):
        if layout_board[ii][ii] == "p":
            pe_margin = ii
            break
    if pe_margin == -1:
        print("Failed to get PE margin, use default value 2", file=sys.stderr)
        pe_margin = 2

    info = {"margin": pe_margin, "clb_type": "p", "arch_type": "cgra"}

    # NOTE:
    # the CGRA file sets the height for each tiles implicitly
    # no need to worry about the height
    layouts = {}
    layouts[layout_name] = (layout_board, blk_height, blk_capacity, info)
    return layouts


def make_board(board_meta):
    layout_board, blk_capacity, _, _ = board_meta
    height = len(layout_board)
    width = len(layout_board[0])
    capacity = 1
    for blk in blk_capacity:
        if blk_capacity[blk] > capacity:
            capacity = blk_capacity[capacity]
    if capacity > 1:
        board = []
        for y in range(height):
            row = [[]] * width
            board.append(row)
    else:
        board = []
        for y in range(height):
            row = [None] * width
            board.append(row)
    return board

def generate_is_cell_legal(board_meta):
    layout_board, blk_height, blk_capacity, _ = board_meta
    height = len(layout_board)
    width = len(layout_board[0])

    def is_legal(board, pos, blk):
        # if board is not defined, we only check the legitimacy
        x, y = pos
        blk_type = blk[0]
        if x < 0 or y < 0 or x >= width or y >= height:
            return False
        if layout_board[y][x] != blk_type:
            return False
        if board is not None:
            # for FPGA
            if type(board[y][x]) == list:
                capacity = blk_capacity[blk_type]
                if len(board[y][x]) >= capacity:
                    return False
                if blk_height[blk_type] != 1:
                    b_height = blk_height[blk_type]
                    y_min = max(0, y - b_height)
                    y_max = min(height, y + b_height)
                    for yy in range(y_min, y_max):
                        if len(board[y][x]) >= capacity:
                            return False
            else:
                if board[y][x] is not None:
                    return False
        return True
    return is_legal


def generate_place_on_board(board_meta):
    is_legal = generate_is_cell_legal(board_meta)

    def place_on_board(board, blk_id, pos):
        x, y = pos
        if type(board[y][x]) == list:
            if blk_id in board[y][x]:
                return
            if not is_legal(board, pos, blk_id):
                raise Exception("Illegal position for " + blk_id + " at " + \
                                str(pos))
            board[y][x].append(blk_id)
        else:
            if board[y][x] == blk_id:
                return
            if not is_legal(board, pos, blk_id):
                raise Exception("Illegal position for " + blk_id + " at " + \
                                str(pos))
            board[y][x] = blk_id
    return place_on_board


def print_board_info(board_name, board_meta):
    layout_board, blk_height, blk_capacity, info = board_meta
    height = len(layout_board)
    width = len(layout_board[0])
    print("Board", board_name, "Layout {}x{}:".format(width, height))
    _, columns = os.popen('stty size', 'r').read().split()
    columns = int(columns)
    if width < columns:
        space = " " if width * 2 < columns else ""
        for y in range(height):
            for x in range(width):
                t = layout_board[y][x]
                if t is None:
                    t = '-'
                print(t, end=(space if x < width - 1 else ""))
            print()
    print("Block info: ", end="")
    for blk in blk_height:
        print("blk-{} {}x{}-{}".format(blk, 1, blk_height[blk],
                                       blk_capacity[blk]),
              end="  ")
    print("\nCLB/PE margin:", info["margin"])


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:", sys.argv[0], "[OPTION]", "<arch_file>",
              "\n[OPTION]: -vpr, -cgra", file=sys.stderr)
        exit(1)
    elif len(sys.argv) > 2:
        for opt in sys.argv[1:]:
            if opt == "-vpr":
                use_vpr = True
                use_cgra = False
                break
            elif opt == "-cgra":
                use_vpr = False
                use_cgra = True
                break
    else:
        use_vpr = False
        use_cgra = False
    filename = sys.argv[1]
    if (not use_vpr) and (not use_cgra):
        _, ext = os.path.splitext(filename)
        if ext == ".xml":
            use_vpr = True
        elif ext == ".txt":
            use_cgra = True
    meta = None
    if use_vpr:
        print("Parsing VPR arch file", filename)
        meta = parse_vpr(filename)
    if use_cgra:
        print("Parsing CGRA arch file", filename)
        meta = parse_cgra(filename)
    if meta is None:
        print("Unexpected state", file=sys.stderr)
        exit(1)
    for board_name in meta:
        print_board_info(board_name, meta[board_name])
