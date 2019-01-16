from __future__ import print_function
import os
from PIL import Image, ImageDraw
import sys

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


def visualize_placement_cgra(layout, board_pos, design_name, changed_pe):
    color_index = "imoprcdI"
    scale = 30
    height, width = layout.height(), layout.width()
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

    im.show()

    file_dir = os.path.dirname(os.path.realpath(__file__))
    output_dir = os.path.join(file_dir, "figures")
    if os.path.isdir(output_dir):
        output_png = design_name + "_place.png"
        output_path = os.path.join(output_dir, output_png)
        im.save(output_path)
        print("Image saved to", output_path)


def visualize_clustering_cgra(layout, cluster_cells):
    scale = 30
    height, width = layout.height(), layout.width()
    im, draw = draw_board(width, height, scale)
    for c_id in cluster_cells:
        cells = cluster_cells[c_id]
        color = color_palette[c_id % len(color_palette)]
        for blk_type in cells:
            for pos in cells[blk_type]:
                draw_cell(draw, pos, color, scale)

    im.show()


def visualize_board(cgra_file):
    from arch import parse_cgra
    color_index = "imoprI"
    layout = parse_cgra(cgra_file)["CGRA"]
    scale = 30
    height, width = layout.height(), layout.width()
    im, draw = draw_board(width, height, scale)
    for y in range(height):
        for x in range(width):
            blk_type = layout.get_blk_type(x, y)
            if blk_type is not None:
                index = color_index.index(blk_type)
                color = color_palette[index % len(color_palette)]
                draw_cell(draw, (x, y), color, scale)
    im.show()

    basename = os.path.basename(cgra_file)
    design_name, ext = os.path.splitext(basename)
    file_dir = os.path.dirname(os.path.realpath(__file__))
    output_dir = os.path.join(file_dir, "figures")
    if os.path.isdir(output_dir):
        output_png = design_name + "_cgra.png"
        output_path = os.path.join(output_dir, output_png)
        im.save(output_path)
        print("Image saved to", output_path)


def main():
    if len(sys.argv) == 2:
        cgra_info = sys.argv[1]
        visualize_board(cgra_info)
        return
    if len(sys.argv) != 4:
        print("[Usage]:", sys.argv[0], "<cgra_info>",
              "[<design.packed>", "<design.place|design.route>]",
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
    board_meta = parse_cgra(cgra_info)["CGRA"]
    if ext == ".place":
        from arch import parse_placement
        board_pos, _ = parse_placement(input_file)
        visualize_placement_cgra(board_meta, board_pos, design_name, changed_pe)


if __name__ == '__main__':
    main()
