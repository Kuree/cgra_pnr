from __future__ import division
import json
import random
import string
from argparse import ArgumentParser

# minimal netlist generation

alu_types_16 = ("mul", "sub", "add", "ashr", "smax", "sub")


def create_alu(alu_type):
    assert alu_type in alu_types_16
    data = {"genref": "cgralib.PE",
            "genargs": {"op_kind": ["String", "alu"],
                        },
            "modargs": {"alu_op_debug": ["String", alu_type]}
            }
    return data


def create_mux():
    data = {
        "genref": "cgralib.PE",
        "genargs": {"op_kind": ["String", "combined"]},
        "modargs": {"alu_op": [["BitVector", 6], "6'h08"],
                    "alu_op_debug": ["String", "mux"],
                    "lut_value": [["BitVector", 8], "8'h00"]
                    }
    }
    return data


def create_mem(fifo_depth):
    data = {
        "genref": "cgralib.Mem",
        "genargs": {"total_depth": ["Int", 1024], "width": ["Int", 16]},
        "modargs": {"almost_count": ["Int", 0],
                    "depth": ["Int", fifo_depth]
                    }
    }
    return data


def create_bit_const(bool_value):
    assert isinstance(bool_value, bool)
    data = {
        "modref": "corebit.const",
        "modargs": {"value": ["Bool", bool_value]}
    }
    return data


def create_const(const_value):
    data = {
        "genref": "coreir.const",
        "genargs": {"width": ["Int", 16]},
        "modargs": {"value": [["BitVector", 16],
                              "16'h{0:04x}".format(const_value)]}

    }
    return data


def create_reg():
    data = {
        "genref": "coreir.reg",
        "genargs": {"width": ["Int", 16]},
        "modargs": {"clk_posedge": ["Bool", True],
                    "init": [["BitVector", 16], "16'hxxxx"]}
    }
    return data


def create_io():
    data = {
        "genref": "cgralib.IO",
        "genargs": {"width": ["Int", 16]}
    }
    return data


def create_lut(lut_value):
    data = {
        "genref": "cgralib.PE",
        "genargs": {"op_kind": ["String", "bit"]},
        "modargs": {
            "bit0_mode": ["String", "BYPASS"], "bit0_value": ["Bool", False],
            "bit1_mode": ["String", "BYPASS"], "bit1_value": ["Bool", False],
            "bit2_mode": ["String", "BYPASS"], "bit2_value": ["Bool", False],
            "lut_value": [["BitVector", 8],
                          "8'h{0:02x}".format(lut_value)]}
    }
    return data


def open_ports(names, used_ports):
    result = set()
    for name in names:
        op = name.split("_")[0]
        if "lb" == op or "lut" == op:
            continue
        if "reg" == op:
            if (name, "in") not in used_ports:
                result.add((name, "in"))
        else:
            if (name, "data.in.0") not in used_ports:
                result.add((name, "data.in.0"))
            if (name, "data.in.1") not in used_ports:
                result.add((name, "data.in.1"))
    return result


def random_name():
    return "".join(random.sample(string.ascii_letters, 4)).lower()


def create_kernel(kernel_size, num_mem, num_reg, const_rate, reg_reg_rate,
                  kernel_num):
    # create kernels
    names = list()
    for i in range(kernel_size):
        names.append("{}${}".format(random_name(), kernel_num + i))
    kernel_num += kernel_size
    working_set = names[:]
    mems = []
    regs = []
    wens = []
    names = set()
    has_input = {}
    # mem assignment
    for i in range(num_mem):
        raw_name = working_set.pop(0)
        mem_name = "lb_" + str(kernel_num) + "$" + raw_name
        mems.append(mem_name)
        names.add(mem_name)

    # reg assignment
    for i in range(num_reg):
        raw_name = working_set.pop(0)
        reg_name = "reg_" + str(kernel_num) + "_" + raw_name
        names.add(reg_name)
        regs.append(reg_name)

    # wen lut assignment
    for i in range(num_mem):
        raw_name = working_set.pop(0)
        lut_name = "lut_" + str(kernel_num) + "_" + raw_name
        wens.append(lut_name)
        names.add(lut_name)

    # alu assignment
    while len(working_set) > 0:
        alu_type = random.choice(alu_types_16)
        raw_name = working_set.pop(0)
        alu_name = alu_type + "_" + str(kernel_num) + "_" + raw_name
        names.add(alu_name)

    names = list(names)
    names.sort(key=lambda x: int(x.split("$")[-1]))
    random.shuffle(names)
    # mem has to be the first
    # so we do an in-place sort

    def reverse_topo_sort(x):
        if "lb" == x[:2]:
            return 0
        if "lut" in x[:3]:
            return 1
        elif "reg" in x[:3]:
            return 2
        else:
            return 3
    names.sort(key=reverse_topo_sort)

    # sort special blocks
    mems.sort(key=lambda x: names.index(x))
    regs.sort(key=lambda x: names.index(x))
    # set up the connection
    # it's strictly src -> sink
    connections = []
    used_ports = set()
    # handle memory
    for i in range(num_mem - 1):
        out_port = (mems[i], "rdata")
        in_port = (mems[i + 1], "wdata")
        add_ports(in_port, used_ports)
        connections.append([".".join(out_port), ".".join(in_port)])
        assert(mems[i + 1] not in has_input)
        has_input[mems[i + 1]] = 1
    # mem wen
    for i in range(num_mem):
        lut_name = wens[i]
        out_port = (lut_name, "bit.out")
        in_port = (mems[i], "wen")
        add_ports(in_port, used_ports)
        connections.append([".".join(out_port), ".".join(in_port)])
        has_input[mems[i]] = 1

    # reg to reg
    for i in range(num_reg - 1):
        if random.random() < reg_reg_rate:
            # reg to reg!
            out_port = (regs[i], "out")
            in_port = (regs[i + 1], "in")
            add_ports(in_port, used_ports)
            connections.append([".".join(out_port), ".".join(in_port)])
            assert (regs[i + 1] not in has_input)
            has_input[regs[i + 1]] = 1

    # first pass
    # this pass making sure that every blk has an output connection
    for i in range(len(names) - 2, -1, -1):
        # working backwards so that the DAG only has one input and one output
        current_name = names[i]
        if "lb" == current_name[:2]:
            out_port = "rdata"
        elif "reg" == current_name[:3]:
            out_port = "out"
        elif "lut" == current_name[:3]:
            continue
        else:
            out_port = "data.out"
        made_connection = False
        while not made_connection:
            j = random.randrange(i + 1, len(names))

            # trying to make connections
            in_name = names[j]
            if "lb" == in_name[:2] or "lut" == in_name[:3]:
                # we have taken care of this one
                continue
            if "reg" in in_name:
                if (in_name, "in") in used_ports:
                    continue
                in_port = "in"
                # make the connection
                connections.append((".".join((current_name, out_port)),
                                    ".".join((in_name, in_port))))
                add_ports((in_name, in_port), used_ports)
                made_connection = True
            else:
                if (in_name, "data.in.0") in used_ports:
                    if (in_name, "data.in.1") in used_ports:
                        continue
                    else:
                        in_port = "data.in.1"
                else:
                    in_port = "data.in.0"
                connections.append((".".join((current_name, out_port)),
                                    ".".join((in_name, in_port))))
                add_ports((in_name, in_port), used_ports)
                made_connection = True

    # second pass
    # randomly connect nets
    available_ports = open_ports(names, used_ports)
    available_ports = list(available_ports)
    available_ports.sort(key=lambda x: int(x[0].split("$")[-1]))
    random.shuffle(available_ports)
    new_names = []
    while len(available_ports) > 0:
        in_name, in_port = available_ports.pop(0)
        in_index = names.index(in_name)

        # chance to have a const connection!
        if "reg" != in_name[:3]:
            if random.random() < const_rate:
                # yay!
                new_name = "const_" + str(kernel_num) + "_" + random_name() +\
                    str(len(names) + len(new_names))
                connections.append((".".join((new_name, "out")),
                                   ".".join((in_name, in_port))))
                used_ports.add((in_name, in_port))
                new_names.append(new_name)
                continue

        out_name_index = random.randrange(0, in_index)
        out_name = names[out_name_index]
        if "lut" == out_name[:3]:
            # put it back in
            available_ports.append((in_name, in_port))
            continue
        else:
            out_port = get_out_port(out_name)
        connections.append((".".join((out_name, out_port)),
                            ".".join((in_name, in_port))))
        used_ports.add((in_name, in_port))

    # sanity check
    available_ports = open_ports(names, used_ports)
    assert (len(available_ports) == 0)
    names = names[:-1] + new_names + [names[-1]]
    return names, connections


def add_ports(in_port, used_ports):
    assert (in_port not in used_ports)
    used_ports.add(in_port)


def main():
    parser = ArgumentParser("Mock CGRA Flow. Please notice that the generated" +
                            " netlist is minimal\nfor PnR and cannot be " +
                            "simulated")
    parser.add_argument("-o", "--output", help="Output netlist file",
                        required=True, type=str, action="store",
                        dest="output_file")
    parser.add_argument("-s", "--seed", help="RND seed",
                        default=0, type=int, action="store", dest="seed")
    parser.add_argument("--const-rate", help="How often does const value " +
                        "appear", default=0.2, action="store",
                        dest="const_rate")
    parser.add_argument("--reg_reg_rate", help="How likely to build up " +
                        "reg to reg chain", default=0.2, action="store",
                        dest="reg_reg_rate")
    parser.add_argument("--num_kernel", help="Number of kernels",
                        default=5, type=int, action="store", dest="num_kernel")
    parser.add_argument("--kernel_size", help="Expected kernel size",
                        default=20, action="store", dest="kernel_size")
    parser.add_argument("--kernel_size_variance",
                        help="Variance of kernel size (uniform distribution)",
                        default=4, action="store",
                        dest="num_kernel_variance")
    parser.add_argument("--expected_num_reg",
                        help="Expected number of registers per kernel",
                        default=5, action="store",
                        dest="expected_num_reg")
    parser.add_argument("--num_reg_variance",
                        help="Variance of number of registers per kernel " +
                        "(uniform distribution)",
                        default=2, action="store",
                        dest="num_reg_variance")
    parser.add_argument("--expected_num_mem",
                        help="Expected number of line buffers per kernel",
                        default=2, action="store",
                        dest="expected_num_mem")
    parser.add_argument("--num_mem_variance",
                        help="Variance of number of line buffers per kernel " +
                        "(uniform distribution)", default=1, action="store",
                        dest="num_mem_variance")

    args = parser.parse_args()
    # random seed
    seed = args.seed
    random.seed(seed)

    const_rate = args.const_rate
    reg_reg_rate = args.reg_reg_rate
    num_kernels = args.num_kernel
    expected_kernel_size = args.kernel_size
    num_kernel_variance = args.num_kernel_variance
    # we have two places to connect to reg, so divide this by 2 to approximate
    # the actual reg usage.
    expected_num_reg = args.expected_num_reg // 2
    num_reg_variance = args.num_reg_variance
    expected_num_mem = args.expected_num_mem
    num_mem_variance = args.num_mem_variance

    # output file
    output_file = args.output_file

    names_list = []
    connections_list = []
    # first pass to create kernel connections
    num_blocks = 0
    for i in range(num_kernels):
        kernel_size = expected_kernel_size + random.randrange(
            -num_kernel_variance,
            num_kernel_variance
            + 1)
        num_reg = expected_num_reg + random.randrange(-num_reg_variance,
                                                      num_reg_variance + 1)
        num_mem = expected_num_mem + random.randrange(0,
                                                      num_mem_variance + 1)
        names, connections = create_kernel(kernel_size, num_mem, num_reg,
                                           const_rate, reg_reg_rate, num_blocks)
        names_list.append(names)
        connections_list.append(connections)
        num_blocks += len(names)
    kernel_connections = []
    working_num_kernels = list(range(num_kernels))
    random.shuffle(working_num_kernels)
    while len(working_num_kernels) > 0:
        kernel_limit = len(working_num_kernels) // 2
        kernels = []
        if kernel_limit > 1:
            num_k = random.randrange(1, kernel_limit + 1)
            # make sure we have enough
            num_k = min(num_k, len(working_num_kernels))
            for _ in range(num_k):
                kernels.append(working_num_kernels.pop(0))
        elif kernel_limit == 1:
            # either io -> 0 -> 1 -> io, or io -> 1/2 -> io
            if random.random() < 0.5:
                kernels.append(working_num_kernels.pop(0))
            else:
                entry1 = working_num_kernels.pop(0)
                entry2 = working_num_kernels.pop(0)
                kernels.append(entry1)
                kernels.append(entry2)
        else:
            kernels.append(working_num_kernels.pop(0))
        kernel_connections.append(kernels)

    # second pass to handle IO
    io_count = 0
    extra_names = []
    extra_connections = []
    for kernel_id in kernel_connections[0]:
        io_name = "io_16_{}".format(io_count)
        io_port = "out"
        io_count += 1
        extra_names.append(io_name)
        extra_connections.append((".".join((io_name, io_port)),
                                  ".".join((names_list[kernel_id][0],
                                            "wdata"))))
    for kernel_id in kernel_connections[-1]:
        io_name = "io_16_{}".format(io_count)
        io_count += 1
        io_port = "in"
        extra_names.append(io_name)
        out_name = names_list[kernel_id][-1]
        out_port = get_out_port(out_name)
        extra_connections.append((".".join((out_name, out_port)),
                                  ".".join((io_name, io_port))))

    # third pass, create random alu to glue them together
    for i in range(0, len(kernel_connections) - 1):
        kernel_from = kernel_connections[i]
        kernel_to = kernel_connections[i + 1]
        num_from = len(kernel_connections[i])
        num_to = len(kernel_connections[i + 1])
        if num_from > num_to:
            # connect the first chunk one-to-ont
            for k in range(0, num_to - 1):
                in_name = names_list[kernel_to[k]][0]
                assert "lb" in in_name
                direct_connect_kernel(extra_connections, k, k, kernel_from,
                                      kernel_to, names_list)
            new_alu = create_random_alu()
            for k in range(num_to - 1, num_from - 1):
                # left hand reduce
                if k == num_to - 1:
                    from_1 = names_list[kernel_from[k]][-1]
                else:
                    new_new_alu = create_random_alu()
                    from_1 = new_alu
                    new_alu = new_new_alu
                from_2 = names_list[kernel_from[k + 1]][-1]
                out_1 = get_out_port(from_1)
                out_2 = get_out_port(from_2)
                extra_connections.append((".".join((from_1, out_1)),
                                          ".".join((new_alu,
                                                    "data.in.0"))))
                extra_connections.append((".".join((from_2, out_2)),
                                          ".".join((new_alu,
                                                    "data.in.1"))))
                extra_names.append(new_alu)
            out_port = get_out_port(new_alu)
            in_name = names_list[kernel_to[num_to - 1]][0]
            in_port = "wdata"
            extra_connections.append((".".join((new_alu, out_port)),
                                      ".".join((in_name,
                                                in_port))))
        elif num_from == num_to:
            for j in range(0, num_to):
                direct_connect_kernel(extra_connections, j, j, kernel_from,
                                      kernel_to, names_list)
        else:
            for j in range(0, num_to):
                direct_connect_kernel(extra_connections, j % num_from, j,
                                      kernel_from,
                                      kernel_to, names_list)
    # flatten the names and connections
    result_names = []
    result_connections = []
    for entry in names_list:
        result_names += entry
    result_names += extra_names
    for entry in connections_list:
        result_connections += entry
    result_connections += extra_connections
    result = create_design_top(result_names, result_connections)

    with open(output_file, "w+") as f:
        json.dump(result, f, separators=(',', ': '))


def direct_connect_kernel(extra_connections, out_index, in_index,
                          kernel_from, kernel_to,
                          names_list):
    out_name = names_list[kernel_from[out_index]][-1]
    in_name = names_list[kernel_to[in_index]][0]
    assert "lb" in in_name
    out_port = get_out_port(out_name)
    in_port = "wdata"
    extra_connections.append((".".join((out_name, out_port)),
                              ".".join((in_name,
                                        in_port))))


def get_out_port(out_name):
    op = out_name.split("_")[0]
    if "lb" == op:
        out_port = "rdata"
    elif "reg" == op:
        out_port = "out"
    elif "lut" == op:
        out_port = "out"
    else:
        assert op in alu_types_16
        out_port = "data.out"
    return out_port


def create_random_alu():
    alu_op = random.choice(alu_types_16)
    name = random_name()
    return alu_op + "_" + name + "$" + str(random.randrange(100, 200))


def create_design_top(names, connections):
    instances = {}
    for name in names:
        op = name.split("_")[0]
        if "lb" == op:
            entry = create_mem(random.randrange(100, 200))
        elif "lut" == op:
            entry = create_lut(random.randrange(10, 100))
        elif "const" == op:
            entry = create_const(random.randrange(0, 100))
        elif "reg" == op:
            entry = create_reg()
        elif "io" == op:
            entry = create_io()
        else:
            assert op in alu_types_16
            entry = create_alu(op)
        instances[name] = entry

    list_connections = [list(entry) for entry in connections]
    result = {
        "top": "global.DesignTop",
        "namespaces": {
            "global": {
                "modules": {
                    "DesignTop": {
                        "instances": instances,
                        "connections": list_connections
                    }
                }
            }
        }
    }
    return result


if __name__ == '__main__':
    main()
