from collections import namedtuple
from pathlib import Path
from threading import Thread, Lock, Condition

from PIL import Image

from challenge.util import crop, combine

Position = namedtuple('Position', 'x, y')
Color = namedtuple('Color', 'r, g, b, a')


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
    start_color = pixels[position.x, position.y]
    while frontier:
        p = frontier.pop()
        visited.add(p)
        c = pixels[p.x, p.y]
        if c != start_color:
            continue
        pixels[p.x, p.y] = color
        neighbors = [Position(x, y) for x in range(p.x - 1, p.x + 2)
                     for y in range(p.y - 1, p.y + 2)
                     if 0 <= x < image.size[0]
                     and 0 <= y < image.size[1]
                     and not (x == p.x and y == p.y)]
        for neighbor in neighbors:
            if neighbor not in visited:
                frontier.add(neighbor)


class Edges:
    """
    Contains sets of changed edge positions.

    Attributes
    ----------
    top : set[Position]
    left : set[Position]
    bottom : set[Position]
    right : set[Position]
    """

    def __init__(self, top=None, right=None, bottom=None, left=None):
        if top is None:
            top = set()
        if right is None:
            right = set()
        if bottom is None:
            bottom = set()
        if left is None:
            left = set()
        self.top = top
        self.right = right
        self.bottom = bottom
        self.left = left


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
    Edges
        Sets of edge positions that were modified.
    """
    edges = Edges()
    pixels = im.load()
    w, h = im.size

    visited = set()
    frontier = tile_positions
    while frontier:
        px, py = frontier.pop()
        visited.add(Position(px, py))
        c = pixels[px, py]
        if c != from_color:
            continue
        pixels[px, py] = to_color
        # check if it is an edge
        if px == 0:
            edges.left.add(Position(px, py))
        elif py == 0:
            edges.top.add(Position(px, py))
        elif px == w - 1:
            edges.right.add(Position(px, py))
        elif py == h - 1:
            edges.bottom.add(Position(px, py))
        neighbors = [Position(x, y) for x in range(px - 1, px + 2)
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


def world_fill(path, fills):
    fw, fh = (10, 10)
    w, h = (160, 144)
    work_queue = []
    img_map = dict()
    for fl, tl, to_color in fills:
        from_color = get_pixel_color(path, fl, tl)
        work_queue.append((fl, {tl}, from_color, to_color))
    while work_queue:
        work = work_queue.pop()
        (fx, fy), tl, from_color, to_color = work
        file = path / f'tile_{fx}_{fy}.png'
        im = img_map.get((fx, fy), Image.open(file))
        edges = tile_fill(im, tl, from_color, to_color)
        if edges.left and fx > 0:
            new_positions = {(w - 1, y) for (x, y) in edges.left}
            work_queue.append(((fx - 1, fy), new_positions, from_color, to_color))
        if edges.top and fy > 0:
            new_positions = {(x, h - 1) for (x, y) in edges.top}
            work_queue.append(((fx, fy - 1), new_positions, from_color, to_color))
        if edges.right and fx + 1 < fw:
            new_positions = {(0, y) for (x, y) in edges.right}
            work_queue.append(((fx + 1, fy), new_positions, from_color, to_color))
        if edges.bottom and fy + 1 < fh:
            new_positions = {(x, 0) for (x, y) in edges.bottom}
            work_queue.append(((fx, fy + 1), new_positions, from_color, to_color))
        img_map[(fx, fy)] = im
    for (fx, fy), im in img_map.items():
        file = path / f'tile_{fx}_{fy}.png'
        im.save(file)


class WorkItems:
    def __init__(self, data=None):
        if data is None:
            data = dict()
        self.data = data
        self.processing = set()
        self.mu = Lock()
        self.all_tasks_done = Condition(self.mu)
        self.not_empty = Condition(self.mu)
        self.unfinished_tasks = 0

    def put(self, path, work=None):
        if work is None:
            work = (set(), (0, 0, 0, 255), (0, 0, 0, 255))
        with self.mu:
            if path not in self.data:
                self.unfinished_tasks += 1
                self.data[path] = {(work[1], work[2]): work[0]}
            else:
                w = self.data[path]
                s = w.get((work[1], work[2]), set())
                w[(work[1], work[2])] = s | work[0]
                self.data[path] = w
            self.not_empty.notify()

    def get(self):
        with self.not_empty:
            while len(self.data) == 0:
                self.not_empty.wait()
            while not self.data.keys() - self.processing:
                self.not_empty.wait()
            keys = self.data.keys() - self.processing
            k = keys.pop()
            w = self.data.pop(k)
            self.processing.add(k)
            return k, w

    def task_done(self, f):
        with self.all_tasks_done:
            self.processing.remove(f)
            unfinished = self.unfinished_tasks - 1
            if unfinished <= 0:
                if unfinished < 0:
                    raise ValueError('task_done() called too many times')
                self.all_tasks_done.notify_all()
            self.unfinished_tasks = unfinished

    def join(self):
        with self.all_tasks_done:
            while self.unfinished_tasks:
                self.all_tasks_done.wait()


class Worker(Thread):
    def __init__(self, path, fh, fw, h, w, work):
        Thread.__init__(self, daemon=True)
        self.path = path
        self.fh = fh
        self.fw = fw
        self.h = h
        self.w = w
        self.work = work

    def run(self):
        while True:
            f, work = self.work.get()
            fx, fy = f
            file = self.path / f'tile_{fx}_{fy}.png'
            with Image.open(file) as im:
                for (from_color, to_color), tp in work.items():
                    edges = tile_fill(im, tp, from_color, to_color)
                    if edges.left and fx > 0:
                        new_positions = {(self.w - 1, y) for (x, y) in edges.left}
                        self.work.put((fx - 1, fy), (new_positions, from_color, to_color))
                    if edges.top and fy > 0:
                        new_positions = {(x, self.h - 1) for (x, y) in edges.top}
                        self.work.put((fx, fy - 1), (new_positions, from_color, to_color))
                    if edges.right and fx + 1 < self.fw:
                        new_positions = {(0, y) for (x, y) in edges.right}
                        self.work.put((fx + 1, fy), (new_positions, from_color, to_color))
                    if edges.bottom and fy + 1 < self.fh:
                        new_positions = {(x, 0) for (x, y) in edges.bottom}
                        self.work.put((fx, fy + 1), (new_positions, from_color, to_color))
                im.save(file)
            self.work.task_done(f)


def concurrent_world_fill(path, fills, num_workers=None):
    if num_workers is None:
        num_workers = 10
    fw, fh = (10, 10)
    w, h = (160, 144)
    work = WorkItems()
    for i in range(num_workers):
        Worker(path, fh, fw, h, w, work).start()
    for fl, tl, to_color in fills:
        from_color = get_pixel_color(path, fl, tl)
        work.put(fl, ({tl}, from_color, to_color))
    work.join()


def main():
    with Image.open('part_1/dsa_challenge.png') as im:
        fills = [
            (Position(35, 30), Color(63, 0, 0, 255)),
            (Position(95, 30), Color(127, 0, 0, 255)),
            (Position(125, 30), Color(191, 0, 0, 255)),
            (Position(20, 65), Color(255, 0, 0, 255)),
            (Position(43, 82), Color(0, 63, 0, 255)),
            (Position(60, 90), Color(0, 127, 0, 255)),
            (Position(65, 80), Color(0, 191, 0, 255)),
            (Position(77, 80), Color(0, 255, 0, 255)),
            (Position(101, 102), Color(0, 0, 63, 255)),
            (Position(110, 90), Color(0, 0, 127, 255)),
            (Position(120, 90), Color(0, 0, 191, 255)),
            (Position(150, 102), Color(0, 0, 255, 255)),
        ]
        for p, c in fills:
            fill(im, p, c)
        im.show()

    fills = [(Position(6, 9), Position(0, 0), Color(255, 0, 0, 255)),
             (Position(0, 1), Position(0, 50), Color(32, 160, 137, 255)),
             (Position(2, 2), Position(80, 62), Color(58, 212, 109, 255)),
             (Position(6, 1), Position(140, 56), Color(58, 118, 221, 255))]

    crop(Path('part_2/dsa_challenge_2.png'))
    world_fill(Path('part_2'), fills)
    combine(Path('part_2'))

    crop(Path('part_2/dsa_challenge_2.png'))
    concurrent_world_fill(Path('part_2'), fills)
    combine(Path('part_2'))


if __name__ == '__main__':
    main()
