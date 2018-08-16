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
                    linked_nets[net_id] = merged_nets

    # make sure we've merged every nets
    assert(len(resolved_net) == len(net_id_to_remove))

    return linked_nets, net_id_to_remove
