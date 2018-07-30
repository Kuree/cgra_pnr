def save_placement(placement_filename, placenet_filename, board, board_pos):
    _, _, block_names, header = parse_raw_placement(placement_filename,
                                                           True)
    # this is indexed by ID
    new_board_pos = {}
    for blk_id in board_pos:
        new_id = int(blk_id[1:])
        new_board_pos[new_id] = board_pos[blk_id]

    working_set = set(block_names.keys())
    with open(placenet_filename, "w+") as f:
        for line in header:
            f.write(line)
        for blk_id in new_board_pos:
            pos = new_board_pos[blk_id]
            x, y = pos
            entry = board[y][x]
            for sub_index in range(len(entry)):
                if int(entry[sub_index][1:]) == blk_id:
                    break
            assert(sub_index != len(entry))
            f.write("{0}\t\t{1}\t{2}\t{3}\t#{4}\n".format(block_names[blk_id],
                                                          x,
                                                          y,
                                                          sub_index,
                                                          blk_id))
            working_set.remove(blk_id)
    #for blk in working_set:
    #    print("WARN: missing", blk)


def parse_placement(filename):
    return parse_raw_placement(filename)


def parse_raw_placement(filename, all_info = False):
    with open(filename) as f:
        lines = f.readlines()
    line = lines[1]
    raw_data = line.split()
    X, Y = raw_data[2], raw_data[4]
    X, Y = int(X), int(Y)
    header = lines[:5]
    lines = lines[5:]
    blk_pos = {}
    block_names = {}

    for line in lines:
        raw_data = line.split()
        x, y, sub_index = int(raw_data[1]), int(raw_data[2]), int(raw_data[3])
        blk_id = int(raw_data[-1][1:])
        block_names[blk_id] = raw_data[0]
        if all_info:
            blk_pos[blk_id] = (x, y, sub_index)
        else:
            blk_pos[blk_id] = (x, y)
    if all_info:
        return (X, Y), blk_pos, block_names, header
    else:
        return (X, Y), blk_pos


def set_node_id(block_id, block_type):
    if block_type == "clb":
        block_type = "c"
    elif block_type == "io":
        block_type = "i"
    elif block_type == "memory":
        block_type = "m"
    elif block_type == "mult_36":
        block_type = "u"
    else:
        raise Exception("unknown type " + block_type)
    return block_type + str(block_id)


def parse_packed(filename):
    with open(filename) as f:
        lines = f.readlines()
    num_nets, num_blocks = [int(x) for x in lines[-1].split()]

    netlist = {}
    block_types = {}
    for line_num in range(num_nets):
        line = lines[line_num]
        raw_data = line.split()
        # assert(int(raw_data[0]) == net_id)
        # global net doesn't count in VPR
        net_id = "e" + raw_data[0]
        netlist[net_id] = []
        raw_data = raw_data[1:]
        for i in range(0, len(raw_data), 2):
            block_id = raw_data[i]
            block_type = raw_data[i + 1]
            block_id = set_node_id(block_id, block_type)
            netlist[net_id].append(block_id)
            if block_id not in block_types:
                block_types[block_id] = block_type
    return netlist, block_types
