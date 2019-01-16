"""Operating on bookshelf format"""
from __future__ import print_function
import sys
import os

from .arch import get_layout
from .cgra import parse_placement, load_packed_file


def write_scl(filename, board_layout, placement):
    with open(filename, "w+") as f:
        f.write("UCLA scl 1.0\n")

        # first pass to figure out if all the IO's are being used
        io_pos = []
        pos_set = set()
        for blk_id in placement:
            pos = placement[blk_id]
            if blk_id[0] == "i":
                io_pos.append(pos)
            pos_set.add(pos)

        top_row = False
        bottom_row = False
        for x, y in io_pos:
            if y == 0:
                top_row = True
            elif y == len(board_layout) - 1:
                bottom_row = True
        num_rows = len(board_layout) - (2 - int(top_row) - int(bottom_row))

        f.write("\n\nNumRows : {}\n\n".format(num_rows))
        range_start = 0 if top_row else 1
        range_end = range_start + num_rows
        assert range_end == len(board_layout) - int(not bottom_row)

        for y in range(range_start, range_end):
            f.write("CoreRow Horizontal\n")
            f.write(" Coordinate :          {}\n".format(y))
            f.write(" Height :                1\n")
            f.write(" Sitewidth    :          1\n")
            f.write(" Sitespacing  :          1\n")
            f.write(" Siteorient   :          N\n")
            f.write(" Sitesymmetry :          Y\n")

            sub_row = []
            for x in range(len(board_layout[y])):
                if board_layout[y][x] is None:
                    sub_row = write_sub_row(f, sub_row)
                elif board_layout[y][x] == "m":
                    if (x, y) in pos_set:
                        sub_row.append(x)
                    else:
                        sub_row = write_sub_row(f, sub_row)
                elif board_layout[y][x] == "i":
                    if (x, y) in pos_set:
                        sub_row.append(x)
                    else:
                        sub_row = write_sub_row(f, sub_row)
                else:
                    sub_row.append(x)
            f.write("End\n")


def write_sub_row(f, sub_row):
    if len(sub_row) > 0:
        # close it up
        f.write(" SubrowOrigin :          {} ".format(
            sub_row[0]))
        f.write(" Numsites :       {}\n".format(len(sub_row)))
        sub_row = []
    return sub_row


def check_placement(placement):
    for blk_id in placement:
        if blk_id[0] == "r":
            raise Exception("It has to be unpacked!")


def write_nodes(nodes_filename, placement):
    with open(nodes_filename, "w+") as f:
        f.write("UCLA nodes 1.0\n\n")

        blks = list(placement.keys())
        blks.sort(key=lambda x: 1 if x[0] == "i" else 0)

        num_io = len([x for x in blks if x[0] == "i"])
        f.write("NumNodes: {}\n".format(len(blks)))
        f.write("NumTerminals : {}\n".format(num_io))

        for blk in blks:
            if blk[0] == "i":
                f.write("{} 1 1 terminal\n".format(blk))
            else:
                f.write("{} 1 1\n".format(blk))


def write_nets(net_filename, netlist):
    with open(net_filename, "w+") as f:
        f.write("UCLA nets 1.0\n\n")

        num_nets = len(netlist)
        num_pins = sum([len(netlist[net_id]) for net_id in netlist])

        f.write("NumNets : {}\n".format(num_nets))
        f.write("NumPins : {}\n".format(num_pins))

        for net_id in netlist:
            net = netlist[net_id]
            f.write("NetDegree : {}\n".format(len(net)))

            for i in range(len(net)):
                if i == 0:
                    f.write("{} O\n".format(net[i][0]))
                else:
                    f.write("{} I\n".format(net[i][0]))


def write_pl(pl_name, placement):
    with open(pl_name, "w+") as f:
        f.write("UCLA pl 1.0\n\n")

        for blk_id in placement:
            x, y = placement[blk_id]
            if blk_id[0] == "i" or blk_id[0] == "m":
                f.write("{} {} {} fixed\n".format(blk_id, x, y))
            else:
                f.write("{} {} {}\n".format(blk_id, 1, 1))


def write_aux(aux_filename, design_name):
    # file_nodes, file_nets, file_wts, file_pl, file_scl
    ext = [".nodes", ".nets", ".wts", ".pl", ".scl"]
    with open(aux_filename, "w+") as f:
        f.write("{} : ".format(design_name))
        names = [design_name + e for e in ext]
        f.write(" ".join(names))


def mock_board_meta(size, memory_repeat=5):
    height = size
    width = size

    margin = 1

    board_layout = []
    io_tiles = []
    for y in range(height):
        row = []
        for x in range(width):
            row.append(None)
        for x in range(width):
            if (x == 0 and y == 0) or (x == width - 1 and y == height - 1):
                continue
            if (y == 0 and x == margin) or (y == 0 and x == (width - margin)):
                row[x] = "i"
                io_tiles.append((x, y))
            elif (y == (height - margin) and x == margin) or \
                 (y == (height - margin) and (x == width - margin - 1)):
                row[x] = "i"
                io_tiles.append((x, y))
            elif x % memory_repeat == margin and x != margin:
                row[x] = "m"
            else:
                row[x] = "p"
        board_layout.append(row)
    layout = get_layout(board_layout)
    layouts = {"cgra": layout}
    return layouts


def main():
    if len(sys.argv) != 4:
        print("Usage:", sys.argv[0], "<arch_size> <placement> <output_dir>",
              file=sys.stderr)
        exit(1)
    arch_size = int(sys.argv[1])
    placement_file = sys.argv[2]
    output_dir = sys.argv[3]

    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)

    design_name, _ = os.path.splitext(os.path.basename(placement_file))
    placement, _ = parse_placement(placement_file)
    check_placement(placement)

    # packed file
    packed_filename = placement_file.replace(".place", ".packed")
    netlists, _, _, _ = load_packed_file(packed_filename)

    # scl files
    scl_filename = os.path.join(output_dir, design_name + ".scl")
    board_layout, _, _, _ = mock_board_meta(arch_size)["CGRA"]
    write_scl(scl_filename, board_layout, placement)

    # net and nodes files
    node_filename = os.path.join(output_dir, design_name + ".nodes")
    write_nodes(node_filename, placement)
    net_filename = os.path.join(output_dir, design_name + ".nets")
    write_nets(net_filename, netlists)

    # pl file
    pl_filename = os.path.join(output_dir, design_name + ".pl")
    write_pl(pl_filename, placement)

    # write aux file. we don't care about weight
    aux_filename = os.path.join(output_dir, design_name + ".aux")
    write_aux(aux_filename, design_name)


if __name__ == "__main__":
    main()
