"""Operating on bookshelf format"""
from __future__ import print_function, division
import sys
import os
import random

from .cgra import parse_placement, load_packed_file


def compute_bbox(cells):
    xmin = 10000
    xmax = 0
    ymin = 10000
    ymax = 0

    x_sum = 0
    y_sum = 0

    for x, y in cells:
        if x < xmin:
            xmin = x
        if x > xmax:
            xmax = x
        if y < ymin:
            ymin = y
        if y > ymax:
            ymax = y
        x_sum += x
        y_sum += y

    return xmin, xmax, ymin, ymax


def write_scl(filename, board_layout, placement):
    with open(filename, "w+") as f:
        f.write("UCLA scl 1.0\n")

        # write memory lanes
        # a quick hack since the margin is always 1
        mem_lanes = []
        for x in range(1, len(board_layout[0])):
            if board_layout[1][x] == 'm':
                mem_lanes.append(str(x))
        f.write("{}\n".format(" ".join(mem_lanes)))

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

            for x in range(1, len(board_layout[y])):
                if board_layout[y][x] is None:
                    break
                else:
                    write_sub_row(f, [x])
            f.write("End\n")


def write_scl_cluster(filename, cluster_cells, fixed_locations):
    # need to figure out each available rows
    cells = cluster_cells.copy()

    for blk_id in fixed_locations:
        cells.add(fixed_locations[blk_id])

    rows = {}
    for x, y in cells:
        if y not in rows:
            rows[y] = []
        rows[y].append(x)
    for y in rows:
        rows[y].sort()

    row_keys = list(rows.keys())
    row_keys.sort()

    num_sites = 0

    # write the scl
    with open(filename, "w+") as f:
        f.write("UCLA scl 1.0\n")
        f.write("\n\nNumRows : {}\n\n".format(len(rows)))

        for y in row_keys:
            f.write("CoreRow Horizontal\n")
            f.write(" Coordinate :          {}\n".format(y))
            f.write(" Height :                1\n")
            f.write(" Sitewidth    :          1\n")
            f.write(" Sitespacing  :          1\n")
            f.write(" Siteorient   :          N\n")
            f.write(" Sitesymmetry :          Y\n")

            sub_row = []
            for x in rows[y]:
                # TODO: optimize this
                # write_sub_row(f, [x])
                if len(sub_row) == 0:
                    sub_row.append(x)
                else:
                    # test if it's continuous
                    diff = x - sub_row[-1]
                    assert diff > 0
                    if diff > 1:
                        num_sites += len(sub_row)
                        sub_row = write_sub_row(f, sub_row)
                    sub_row.append(x)
            write_sub_row(f, sub_row)
            num_sites += len(sub_row)
            f.write("End\n")

    assert num_sites == len(cluster_cells) + len(fixed_locations)


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


def write_nets(net_filename, netlist, raw_net=True):
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
                    if raw_net:
                        f.write("{} O\n".format(net[i][0]))
                    else:
                        f.write("{} O\n".format(net[i]))
                else:
                    if raw_net:
                        f.write("{} I\n".format(net[i][0]))
                    else:
                        f.write("{} I\n".format(net[i]))


def write_pl(pl_name, placement):
    with open(pl_name, "w+") as f:
        f.write("UCLA pl 1.0\n\n")

        for blk_id in placement:
            x, y = placement[blk_id]
            if blk_id[0] == "i": # or blk_id[0] == "m":
                f.write("{} {} {} fixed\n".format(blk_id, x, y))
            else:
                f.write("{} {} {}\n".format(blk_id, 0, 0))


def write_aux(aux_filename, design_name):
    # file_nodes, file_nets, file_wts, file_pl, file_scl
    ext = [".nodes", ".nets", ".cls", ".pl", ".scl"]
    with open(aux_filename, "w+") as f:
        f.write("{} : ".format(design_name))
        names = [design_name + e for e in ext]
        f.write(" ".join(names))


def write_detailed_placement(cluster_cells, netlists, init_placement, fixed_pos,
                             design_name, output_dir):

    check_placement(init_placement)

    # compute the bounding box
    xmin, xmax, ymin, ymax = compute_bbox(cluster_cells)
    # recompute the fixed location so that the NTU placer won't complain about
    # the illegal position (because the way it calculates the bbox for clusters)
    new_fixed_pos = {}
    available_locations = set()
    for x in range(xmin - 1, xmax + 1 + 1):
        available_locations.add((x, ymax + 1))
        available_locations.add((x, ymin - 1))
    for y in range(ymin - 1, ymax + 1 + 1):
        available_locations.add((xmin - 1, y))
        available_locations.add((xmax + 1, y))

    for blk_id in fixed_pos:
        old_x, old_y = fixed_pos[blk_id]
        # search for the closest location
        candidates = list(available_locations)
        candidates.sort(key=lambda pos: abs(pos[0] - old_x) +
                        abs(pos[1] - old_y))
        new_pos = candidates[0]
        available_locations.remove(new_pos)
        new_fixed_pos[blk_id] = new_pos

    # scl files
    scl_filename = os.path.join(output_dir, design_name + ".scl")
    write_scl_cluster(scl_filename, cluster_cells, new_fixed_pos)

    # net and nodes files
    placement = init_placement.copy()
    placement.update(new_fixed_pos)
    node_filename = os.path.join(output_dir, design_name + ".nodes")
    write_nodes(node_filename, placement)
    net_filename = os.path.join(output_dir, design_name + ".nets")
    write_nets(net_filename, netlists, raw_net=False)

    # pl file
    pl_filename = os.path.join(output_dir, design_name + ".pl")
    write_pl(pl_filename, placement)

    # write aux file. we don't care about weight
    aux_filename = os.path.join(output_dir, design_name + ".aux")
    write_aux(aux_filename, design_name)


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
            if x % memory_repeat == margin and x != margin:
                row[x] = "m"
            else:
                row[x] = "p"
        board_layout.append(row)

    # second pass to insert io tiles
    # random IO tiles
    random.seed(0)
    y_range = [random.randrange(margin - 1, width - margin + 1) for _
               in range(4)]
    for y in y_range:
        x = margin - 1
        board_layout[y][x] = "i"
        io_tiles.append((x, y))

        x = width - margin
        board_layout[y][x] = "i"
        io_tiles.append((x, y))

    info = {"margin": margin, "clb_type": "p", "arch_type": "cgra",
            "height": height, "width": width, "id_remap": {},
            "io": io_tiles, "io_pad_name": {},
            "io_pad_bit": {}, "io16_tile": {}}
    blk_height = {"i": 1, "p": 1, "m": 1}
    blk_capacity = {"i": 1, "p": 1, "m": 1}
    layouts = {"CGRA": (board_layout, blk_height, blk_capacity, info)}
    return layouts


def parse_pl(pl_filename):
    with open(pl_filename) as f:
        lines = f.readlines()
    lines = lines[2:]
    placement = {}

    for line in lines:
        line = line.strip()
        place = line.split(":")[0].strip()
        entries = place.split()
        entries = [x for x in entries if len(x) > 0]
        if len(entries) == 0:
            continue
        if len(entries) != 3:
            print(entries)
        assert len(entries) == 3
        blk_id, x, y = entries
        x = int(float(x))
        y = int(float(y))
        placement[blk_id] = (x, y)

    return placement


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
