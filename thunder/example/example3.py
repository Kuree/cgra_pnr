import pythunder


def main():
    layout = pythunder.Layout()
    size = 2
    # 3x3 layout
    layer = pythunder.Layer('p', size, size)
    for x in range(size):
        for y in range(size):
            layer.mark_available(x, y)
    layout.add_layer(layer)

    # two nets
    netlist = {"e0": ["p0", "p1"], "e1": ["p1", "p2", "p3"]}
    # don't do clustering here
    clusters = {"x0": {"p0", "p1", "p2", "p3"}}
    # no fixed position
    fixed_pos = {}

    # global placement
    gp = pythunder.GlobalPlacer(clusters, netlist, fixed_pos, layout)
    # place in gp
    gp.solve()
    gp.anneal()
    gp_result = gp.realize()

    dp_result = pythunder.detailed_placement(clusters, netlist, fixed_pos, gp_result,
                                             layout)
    # global refine
    refine_dp = pythunder.DetailedPlacer(dp_result, netlist,
                                         layout.produce_available_pos(),
                                         fixed_pos, 'p', True)
    refine_dp.refine(1000, 0.001, True)
    result = refine_dp.realize()
    # print it out
    for blk_id, (x, y) in result.items():
        print(blk_id + ": x", x, "y ", y)

if __name__ == "__main__":
    main()
