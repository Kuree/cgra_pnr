def get_alu_str(instance):
    op_type = 1
    signed = False
    if op_type == 0:
        return "add"
    elif op_type == 1:
        # FIXME
        return "sub"
    elif op_type == 3:
        return"abs"
    elif op_type == 4 and signed:
        return "sge"
    elif op_type == 4 and not signed:
        return "uge"
    elif op_type == 5 and signed:
        return "sle"
    elif op_type == 5 and not signed:
        return "ule"
    elif op_type == 0xB:
        return "mul"
    elif op_type == 0xF:
        return "ashr"
    elif op_type == 0x11:
        return "shl"
    elif op_type == 0x12:
        return "or"
    elif op_type == 0x13:
        return "and"
    elif op_type == 0x14:
        return "xor"
