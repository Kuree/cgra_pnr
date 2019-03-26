import six


def group_reg_nets(netlists):
    net_id_to_remove = set()
    linked_nets = {}

    reg_srcs = {}
    reg_srcs_nets = set()
    # first pass to find any nets whose sources are a reg
    for net_id in netlists:
        net = netlists[net_id]
        if net[0][0][0] == "r":
            reg_id = net[0][0]
            reg_srcs[reg_id] = net_id
            reg_srcs_nets.add(net_id)
            # also means we have to remove it from the main netlists
            net_id_to_remove.add(net_id)

    # Keyi:
    # because a reg cannot drive more than one wire (otherwise they will be
    # merged together at the first place), it's safe to assume there is an
    # one-to-one relation between src -> reg -> other wire. However, because
    # it is possible to have reg (src) -> reg (sink) and both of them are
    # unfolded, we need to create a list of nets in order that's going to be
    # merged into the main net.

    def squash_net(nets, src_id):
        result = [src_id]
        for b_id, _ in nets[src_id][1:]:
            if b_id[0] == "r":
                # found another one
                next_id = reg_srcs[b_id]
                result += squash_net(nets, next_id)
        return result

    resolved_net = set()
    for reg_id in reg_srcs:
        r_net_id = reg_srcs[reg_id]
        if r_net_id in resolved_net:
            continue
        # search for the ultimate src
        reg = netlists[r_net_id][0][0]  # id for that reg
        for net_id in netlists:
            if net_id in reg_srcs_nets:
                continue
            net = netlists[net_id]
            for blk_id, _ in net:
                if blk_id == reg:
                    # found the ultimate src
                    # now do a squash to obtain the set of all nets
                    merged_nets = squash_net(netlists, r_net_id)
                    for m_id in merged_nets:
                        resolved_net.add(m_id)
                    if net_id in linked_nets:
                        linked_nets[net_id] += merged_nets
                    else:
                        linked_nets[net_id] = merged_nets

    # make sure we've merged every nets
    assert(len(resolved_net) == len(net_id_to_remove))

    # last pass to ensure the order of the linked nets is correct
    reg_net_order = {}
    for net_id in linked_nets:
        reg_nets = linked_nets[net_id]
        reg_net_index = {}
        index = 0
        working_set = [net_id]
        while len(working_set) > 0:
            n_id = working_set.pop(0)
            for blk, _ in netlists[n_id][1:]:
                if blk[0] == "r":
                    # find the reg_net that has it as src
                    for reg_net_id in reg_nets:
                        if netlists[reg_net_id][0][0] == blk:
                            working_set.append(reg_net_id)
                            reg_net_index[reg_net_id] = index
                            index += 1
                            reg_net_order[reg_net_id] = n_id
        reg_nets.sort(key=lambda x: reg_net_index[x])

    return linked_nets, net_id_to_remove, reg_net_order


def is_conn_out(raw_name):
    port_names = ["out", "outb", "valid", "rdata", "res", "res_p", "io2f_16",
                  "alu_res", "tofab"]
    if isinstance(raw_name, six.text_type):
        raw_name = raw_name.split(".")
    if len(raw_name) > 1:
        raw_name = raw_name[1:]
    for name in port_names:
        if name == raw_name[-1]:
            return True
    return False


def is_conn_in(raw_name):
    port_names = ["in", "wen", "cg_en", "ren", "wdata", "in0", "in1", "in",
                  "inb", "data0", "data1", "f2io_16", "clk_en", "fromfab"]
    if isinstance(raw_name, six.text_type):
        raw_name = raw_name.split(".")
    if len(raw_name) > 1:
        raw_name = raw_name[1:]
    for name in port_names:
        if name == raw_name[-1]:
            return True
    return False
