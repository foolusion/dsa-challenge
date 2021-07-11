from collections import namedtuple
from pathlib import Path

from PIL import Image

from util import crop, combine


def fill(image, position, color):
    """
    Fills image with color starting at position.

    This fills the image modifying the original image passed in. If you do not
    want to modify the image you should make a copy before calling fill.

    Parameters
    ----------
    image : PIL.Image.Image
        The image that you want to fill.
    position : Position
        The coordinates in the image to being the fill.
    color : Color
        The color you want to fill in. You can optionally pass an alpha value.
    """
    pixels = image.load()
    visited = set()
    frontier = {position}
    px, py = position
    start_color = pixels[px, py]
    if color == start_color:
        return
    while frontier:
        p = frontier.pop()
        px, py = p
        visited.add(p)
        c = pixels[px, py]
        if c != start_color:
            continue
        pixels[px, py] = color
        neighbors = [(x, y) for x in range(px - 1, px + 2)
                     for y in range(py - 1, py + 2)
                     if 0 <= x < image.size[0]
                     and 0 <= y < image.size[1]
                     and not (x == px and y == py)]
        for neighbor in neighbors:
            if neighbor not in visited:
                frontier.add(neighbor)


def tile_fill(im, tile_positions, from_color, to_color):
    """
    Fills image with to_color.

    This fills the image. It begins checking from the tile_positions. If the
    position is from_color it is changed to to_color. If tile_positions is
    empty then nothing will be done. It returns the edges that were changed so
    you can fill neighboring images.

    Parameters
    ----------
    im : PIL.Image.Image
    tile_positions : set[tuple[int, int]]
    from_color : tuple[int, int, int, optional[int]]
    to_color : tuple[int, int, int, optional[int]]

    Returns
    -------
    edges : list[set[int]]
        Sets of edge positions that were modified. The list contains edges
        starting with the left at position 0 and continues clockwise top = 1,
        right = 2, and bottom = 3).
    """
    edges = [set(), set(), set(), set()]
    pixels = im.load()
    w, h = im.size

    visited = set()
    frontier = tile_positions
    while frontier:
        px, py = frontier.pop()
        visited.add((px, py))
        c = pixels[px, py]
        if c != from_color:
            continue
        pixels[px, py] = to_color
        # check if it is an edge
        if px == 0:
            edges[0].add(py)
        elif py == 0:
            edges[1].add(px)
        elif px == w - 1:
            edges[2].add(py)
        elif py == h - 1:
            edges[3].add(px)
        neighbors = [(x, y) for x in range(px - 1, px + 2)
                     for y in range(py - 1, py + 2)
                     if 0 <= x < w
                     and 0 <= y < h
                     and not (x == px and y == py)]
        for neighbor in neighbors:
            if neighbor not in visited:
                frontier.add(neighbor)
    return edges


def get_pixel_color(path, world_position, tile_position):
    fx, fy = world_position
    file = path / f'tile_{fx}_{fy}.png'
    with Image.open(file) as im:
        original_color = im.getpixel(tile_position)
    return original_color


def world_fill(path, file_pos, tile_pos, color):
    """Fills across many files.

    This performs fill across many files. The files must be in a directory
    and png. They should be named tile_x_y.png. Where x and y are the column
    and row of the image. The images are assumed to be 0 indexed. This modifies
    the files.

    Parameters
    ----------
    path : string
    file_pos : tuple[int, int]
    tile_pos : tuple[int, int]
    color : tuple[int, int, int, int]
    """
    fw, fh = (10, 10)
    w, h = (160, 144)
    work_queue = []
    img_map = dict()
    from_color = get_pixel_color(Path(path), file_pos, tile_pos)
    if from_color == color:
        return
    work_queue.append((file_pos, {tile_pos}, from_color, color))
    while work_queue:
        work = work_queue.pop()
        (fx, fy), tl, from_color, to_color = work
        file = Path(path) / f'tile_{fx}_{fy}.png'
        im = img_map.get((fx, fy), Image.open(file))
        edges = tile_fill(im, tl, from_color, to_color)
        if edges[0] and fx > 0:
            new_positions = {(w - 1, y) for y in edges[0]}
            work_queue.append(((fx - 1, fy), new_positions, from_color, to_color))
        if edges[1] and fy > 0:
            new_positions = {(x, h - 1) for x in edges[1]}
            work_queue.append(((fx, fy - 1), new_positions, from_color, to_color))
        if edges[2] and fx + 1 < fw:
            new_positions = {(0, y) for y in edges[2]}
            work_queue.append(((fx + 1, fy), new_positions, from_color, to_color))
        if edges[3] and fy + 1 < fh:
            new_positions = {(x, 0) for x in edges[3]}
            work_queue.append(((fx, fy + 1), new_positions, from_color, to_color))
        img_map[(fx, fy)] = im
    for (fx, fy), im in img_map.items():
        file = Path(path) / f'tile_{fx}_{fy}.png'
        im.save(file)


def main():
    with Image.open('part_1/dsa_challenge.png') as im:
        fills = [
            ((35, 30), (63, 0, 0, 255)),
            ((95, 30), (127, 0, 0, 255)),
            ((125, 30), (191, 0, 0, 255)),
            ((20, 65), (255, 0, 0, 255)),
            ((43, 82), (0, 63, 0, 255)),
            ((60, 90), (0, 127, 0, 255)),
            ((65, 80), (0, 191, 0, 255)),
            ((77, 80), (0, 255, 0, 255)),
            ((101, 102), (0, 0, 63, 255)),
            ((110, 90), (0, 0, 127, 255)),
            ((120, 90), (0, 0, 191, 255)),
            ((150, 102), (0, 0, 255, 255)),
        ]
        for p, c in fills:
            fill(im, p, c)
        im.show()

    fills = [((6, 9), (0, 0), (255, 0, 0, 255)),
             ((0, 1), (0, 50), (32, 160, 137, 255)),
             ((2, 2), (80, 62), (58, 212, 109, 255)),
             ((6, 1), (140, 56), (58, 118, 221, 255))]

    crop(Path('part_2/dsa_challenge_2.png'))
    for fp, tp, c in fills:
        world_fill('part_2', fp, tp, c)
    combine(Path('part_2'))


if __name__ == '__main__':
    main()
