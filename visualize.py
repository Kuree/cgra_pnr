from PIL import Image, ImageDraw

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


