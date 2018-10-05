from __future__ import print_function


def parse_raw_netlist(netlist_file):
    with open(netlist_file) as f:
        lines = f.readlines()
    netlists = {}
    instances = set()
    meta_netlists = {}
    line_count = 0
    while line_count < len(lines):
        line = lines[line_count].strip()
        if len(line) == 0:
            break
        tag, net_name, num = line.split()
        num = int(num)
        assert tag == "net"
        net = []
        for i in range(1, num + 1):
            line = lines[line_count + i].strip()
            instance_name, _ = line.split()
            instances.add(instance_name)
            net.append(instance_name)
        end_tag = lines[line_count + num + 1].strip()
        assert end_tag == "endnet"
        line_count += num + 2
        if "clk" in net_name or "control" in net_name:
            meta_netlists[net_name] = net
        else:
            netlists[net_name] = net
    return netlists, meta_netlists, instances


def parse_ripple_placer(placement_file):
    sites = {}
    fixed_sites = {}
    with open(placement_file) as f:
        lines = f.readlines()
    for line in lines:
        line = line.strip()
        raw_inputs = line.split()
        fixed = False
        if len(raw_inputs) == 5:
            assert raw_inputs[-1] == "FIXED"
            raw_inputs.pop(4)
            fixed = True
        assert len(raw_inputs) == 4
        instance_name, x, y, slot = raw_inputs
        x = int(x)
        y = int(y)
        slot = int(slot)
        pos = (x, y)
        if fixed:
            if pos not in fixed_sites:
                fixed_sites[pos] = set()
            fixed_sites[pos].add((instance_name, slot))
        else:
            if pos not in sites:
                sites[pos] = set()
            sites[pos].add((instance_name, slot))
    return sites, fixed_sites


def convert_netlist(board_layout, raw_result, ripple_result, skip_clk_net=True):
    # assign numbers for international usage
    # first build packing table
    raw_netlist, clk_netlists, instances = raw_result
    sites, fixed_sites = ripple_result
    # assign ble ids
    count = 0
    instance_table = {}
    # this is used for final placement output
    instance_slot_index = {}
    sites = sites.copy()
    sites.update(fixed_sites)

    blk_to_site = {}

    for x, y in sites:
        blk_type = board_layout[y][x]
        blk_id = blk_type + str(count)
        count += 1
        for instance_name, slot in sites[(x, y)]:
            instance_table[instance_name] = blk_id
            instance_slot_index[instance_name] = slot
        blk_to_site[blk_id] = (x, y)

    # first pass to convert instance to block id
    if not skip_clk_net:
        raw_netlist = raw_result.copy()
        raw_netlist.update(clk_netlists)

    final_netlist = {}
    for net_name in raw_netlist:
        net = set()
        for instance in raw_netlist[net_name]:
            net.add(instance_table[instance])
        if len(net) > 1:
            net_id = "e" + str(len(final_netlist))
            final_netlist[net_id] = list(net)
    print("Before packing num nets:", len(raw_netlist))
    print("After packing num nets: ", len(final_netlist))

    # produce blk_pos
    blk_pos = {}
    for pos in fixed_sites:
        blks = list(fixed_sites[pos])
        blk_id = None
        for blk, _ in blks:
            if blk_id is None:
                blk_id = instance_table[blk]
            assert blk_id == instance_table[blk]
        assert blk_id[0] == "i"
        blk_pos[blk_id] = pos
        assert blk_id in blk_to_site
    return final_netlist, blk_pos, blk_to_site


def save_packed_netlist(arch_file, design_net_file, placement_file,
                        output_file):
    board_layout = arch.parse_fpga(arch_file)["fpga"][0]

    raw_result = parse_raw_netlist(design_net_file)
    ripple_result = parse_ripple_placer(placement_file)
    netlist, blk_pos, blk_to_site = \
        convert_netlist(board_layout, raw_result, ripple_result)

    with open(output_file, "w+") as f:
        f.write("Netlist {0}\n".format(len(netlist)))
        for net_id in netlist:
            f.write("{}: {}\n".format(net_id, " ".join(netlist[net_id])))
        f.write("Fixed Block {0}\n".format(len(blk_pos)))
        for blk_id in blk_pos:
            x, y = blk_pos[blk_id]
            f.write("{} {} {}\n".format(blk_id, x, y))
        f.write("Block to Site: {0}\n".format(len(blk_to_site)))
        for blk_id in blk_to_site:
            x, y = blk_to_site[blk_id]
            f.write("{} {} {}\n".format(blk_id, x, y))


def load_packed_fpga_netlist(packed_filename):
    netlists = {}
    blk_pos = {}
    blk_to_site = {}
    with open(packed_filename) as f:
        line = f.readline().strip()
        assert "Netlist" in line
        num_nets = int(line[8:])
        for i in range(num_nets):
            line = f.readline().strip()
            net_id, net = line.split(":")
            net = net.split()
            net = [x for x in net if len(x) > 0]
            netlists[net_id] = net
        line = f.readline()
        assert "Fixed Block" in line
        num_blocks = int(line[len("Fixed Block "):])
        for i in range(num_blocks):
            line = f.readline().strip()
            blk_id, x, y = line.split()
            x, y = int(x), int(y)
            blk_pos[blk_id] = (x, y)
        line = f.readline()
        assert "Block to Site: " in line
        num_blocks = int(line[len("Block to Site: "):])
        for i in range(num_blocks):
            line = f.readline()
            blk, x, y = line.split()
            x, y = int(x), int(y)
            blk_to_site[blk] = (x, y)

    return netlists, blk_pos, blk_to_site


def convert_to_ispd_placement(ripple_placement_fn, fpga_placement_fn,
                              output_fn):
    from .cgra import parse_placement
    sites, fixed_sites = parse_ripple_placer(ripple_placement_fn)
    sites.update(fixed_sites)
    placements, _ = parse_placement(fpga_placement_fn)
    packing_file = fpga_placement_fn.replace(".place", ".packed")
    _, _, blk_to_site = load_packed_fpga_netlist(packing_file)
    with open(output_fn, "w+") as f:
        for blk_id in placements:
            pos = placements[blk_id]
            site_pos = blk_to_site[blk_id]
            x, y = pos
            for instance in sites[site_pos]:
                f.write("{} {} {} {}\n".format(instance[0], x, y, instance[1]))


if __name__ == "__main__":
    import sys
    import arch

    if len(sys.argv) == 4:
        convert_to_ispd_placement(sys.argv[1], sys.argv[2], sys.argv[3])
        exit(0)

    if len(sys.argv) != 5:
        print("Usage:", sys.argv[0], "<design.scl>", "<design.nets>",
              "<placement.pl>", "<output_file>", file=sys.stderr)
        exit(1)
    save_packed_netlist(*sys.argv[1:])

