from __future__ import print_function
import os
from PIL import Image, ImageDraw
import sys

from matplotlib import pyplot as plt

SCALE_FACTOR = 10


color_palette = [(166, 206, 227),
                 (31, 120, 180),
                 (178, 223, 138),
                 (51, 160, 44),
                 (251, 154, 153),
                 (227, 26, 28),
                 (253, 191, 111),
                 (255, 127, 0),
                 (202, 178, 214),
                 (106, 61, 154),
                 (255, 255, 153),
                 (177, 89, 40)]


def draw_board(width=60, height=60, scale=None):
    if scale is None:
        scale = SCALE_FACTOR
    img_width = width * scale
    img_height = height * scale
    im = Image.new("RGB", (img_width, img_height))
    draw = ImageDraw.Draw(im)
    for i in range(0, height + 1):
        # horizontal lines
        draw.line((0, i * scale, img_width, i * scale),
                  fill=(255, 255, 255), width=1)
    for i in range(0, width + 1):
        # vertical lines
        draw.line((i * scale, 0, i * scale, img_height),
                  fill=(255, 255, 255), width=1)
    return im, draw


def draw_cell(draw, pos, color, scale=None, width_frac=1):
    if scale is None:
        scale = SCALE_FACTOR
    size = scale - 1
    width = size * width_frac
    x, y = pos
    draw.rectangle((x * scale + 1, y * scale + 1, x * scale + width,
                    y * scale + size), fill=color)


def visualize_placement_cgra(board_meta, board_pos, design_name, changed_pe):
    color_index = "imopr"
    scale = 30
    board_info = board_meta[-1]
    height, width = board_info["height"], board_info["width"]
    im, draw = draw_board(width, height, scale)
    pos_set = set()
    blk_id_list = list(board_pos.keys())
    blk_id_list.sort(key=lambda x: 1 if x[0] == "r" else 0)
    for blk_id in blk_id_list:
        pos = board_pos[blk_id]
        index = color_index.index(blk_id[0])
        color = color_palette[index]
        if blk_id in changed_pe:
            color = color_palette[color_index.index("r")]
        if blk_id[0] == "r":
            assert pos not in pos_set
            pos_set.add(pos)
            pos = pos[0] + 0.5, pos[1]
            width_frac = 0.5
        else:
            width_frac = 1
        draw_cell(draw, pos, color, scale, width_frac=width_frac)

    plt.imshow(im)
    plt.show()

    file_dir = os.path.dirname(os.path.realpath(__file__))
    output_dir = os.path.join(file_dir, "figures")
    if os.path.isdir(output_dir):
        output_png = design_name + "_place.png"
        output_path = os.path.join(output_dir, output_png)
        im.save(output_path)
        print("Image saved to", output_path)


def visualize_routing(cgra_filename, board_meta, packed_filename,
                      routing_result, fold_reg):
    from router import Router
    router = Router(cgra_filename, board_meta, packed_filename,
                    "", fold_reg=fold_reg)
    # update routing resource
    for net_id in routing_result:
        path = routing_result[net_id]
        # update it by hand because the format is different from
        # the one in
        track_in = None
        entry_to_remove = set()
        for entry in path:
            entry_type = entry[0]
            if entry_type == "src":
                (pos,_), (track_in, track_out) = entry[1:]
                entry_to_remove.add((pos, track_out))
            elif entry_type == "link":
                assert track_in is not None
                (src_pos, dst_pos), (conn_out, conn_in) = entry[1:]
                entry_to_remove.add((src_pos, conn_out))
                entry_to_remove.add((src_pos, track_in))
                track_in = conn_in
            elif entry_type == "sink":
                if len(entry[1:]) == 3:
                    (_, (conn_in, conn_out)), _, (pos, _) = entry[1:]
                    entry_to_remove.add((pos, conn_out))
                    entry_to_remove.add((pos, conn_in))
                    track_in = conn_in
                else:
                    conn, (dst_pos, _) = entry[1:]
                    if len(conn) == 2:
                        conn_in, conn_out = conn
                        entry_to_remove.add((dst_pos, conn_in))
                        entry_to_remove.add((dst_pos, conn_out))
                        track_in = conn_in
                    else:
                        entry_to_remove.add((dst_pos, conn))
                        track_in = conn
        for pos, conn in entry_to_remove:
            resource = router.routing_resource[pos]["route_resource"]
            remove_set = set()
            for conn1, conn2 in resource:
                if conn1 == conn or conn2 == conn:
                    remove_set.add((conn1, conn2))
            for entry in remove_set:
                resource.remove(entry)

    router.vis_routing_resource()


def main():
    if len(sys.argv) != 4:
        print("[Usage]:", sys.argv[0], "<cgra_info>",
              "<design.packed>", "<design.place|design.route>",
              file=sys.stderr)
        exit(1)
    cgra_info = sys.argv[1]
    packed_file = sys.argv[2]
    input_file = sys.argv[3]
    basename = os.path.basename(input_file)
    design_name, ext = os.path.splitext(basename)
    from arch import parse_cgra
    from arch import load_packed_file
    _, _, _, changed_pe = load_packed_file(packed_file)
    fold_reg = len(changed_pe) == 0
    board_meta = parse_cgra(cgra_info, fold_reg=fold_reg)["CGRA"]
    if ext == ".place":
        from arch import parse_placement
        board_pos, _ = parse_placement(input_file)
        visualize_placement_cgra(board_meta, board_pos, design_name, changed_pe)
    elif ext == ".route":
        from arch import parse_routing_result
        routing_result = parse_routing_result(input_file)
        visualize_routing(cgra_info, board_meta, packed_file, routing_result,
                          fold_reg=fold_reg)


if __name__ == '__main__':
    main()
