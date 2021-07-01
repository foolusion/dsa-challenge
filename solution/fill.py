from threading import Thread, Lock, Condition
from PIL import Image
from pathlib import Path


def fill(image, position, color):
    pixels = image.load()
    visited = set()
    x, y = position
    frontier = {(x, y)}
    start_color = pixels[x, y]
    while frontier:
        px, py = frontier.pop()
        visited.add((px, py))
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


def update_edges(edges, edge, pos):
    e = edges.get(edge, set())
    e.add(pos)
    edges[edge] = e


def tile_fill(im, tile_positions, from_color, to_color):
    edges = dict()
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
            update_edges(edges, 'left', (px, py))
        elif py == 0:
            update_edges(edges, 'top', (px, py))
        elif px == w - 1:
            update_edges(edges, 'right', (px, py))
        elif py == h - 1:
            update_edges(edges, 'bottom', (px, py))
        neighbors = [(x, y) for x in range(px - 1, px + 2)
                     for y in range(py - 1, py + 2)
                     if 0 <= x < w
                     and 0 <= y < h
                     and not (x == px and y == py)]
        for neighbor in neighbors:
            if neighbor not in visited:
                frontier.add(neighbor)
    return edges


class Worker(Thread):
    def __init__(self, dir, fh, fw, h, w, work):
        Thread.__init__(self, daemon=True)
        self.dir = dir
        self.fh = fh
        self.fw = fw
        self.h = h
        self.w = w
        self.work = work

    def run(self):
        while True:
            f, work = self.work.get()
            fx, fy = f
            file = self.dir / f'tile_{fx}_{fy}.png'
            with Image.open(file) as im:
                for (from_color, to_color), tp in work.items():
                    edges = tile_fill(im, tp, from_color, to_color)
                    if 'left' in edges and fx > 0:
                        new_positions = {(self.w - 1, y) for (x, y) in edges['left']}
                        self.work.put((fx - 1, fy), (new_positions, from_color, to_color))
                    if 'top' in edges and fy > 0:
                        new_positions = {(x, self.h - 1) for (x, y) in edges['top']}
                        self.work.put((fx, fy - 1), (new_positions, from_color, to_color))
                    if 'right' in edges and fx + 1 < self.fw:
                        new_positions = {(0, y) for (x, y) in edges['right']}
                        self.work.put((fx + 1, fy), (new_positions, from_color, to_color))
                    if 'bottom' in edges and fy + 1 < self.fh:
                        new_positions = {(x, 0) for (x, y) in edges['bottom']}
                        self.work.put((fx, fy + 1), (new_positions, from_color, to_color))
                im.save(file)
            self.work.task_done(f)


def get_pixel_color(dir, world_position, tile_position):
    fx, fy = world_position
    file = dir / f'tile_{fx}_{fy}.png'
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
        if 'left' in edges and fx > 0:
            new_positions = {(w - 1, y) for (x, y) in edges['left']}
            work_queue.append(((fx - 1, fy), new_positions, from_color, to_color))
        if 'top' in edges and fy > 0:
            new_positions = {(x, h - 1) for (x, y) in edges['top']}
            work_queue.append(((fx, fy - 1), new_positions, from_color, to_color))
        if 'right' in edges and fx + 1 < fw:
            new_positions = {(0, y) for (x, y) in edges['right']}
            work_queue.append(((fx + 1, fy), new_positions, from_color, to_color))
        if 'bottom' in edges and fy + 1 < fh:
            new_positions = {(x, 0) for (x, y) in edges['bottom']}
            work_queue.append(((fx, fy + 1), new_positions, from_color, to_color))
        img_map[(fx, fy)] = im
    for (fx, fy), im in img_map.items():
        file = path / f'tile_{fx}_{fy}.png'
        im.save(file)


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


def crop(f):
    with Image.open(f) as im:
        w, h = im.size
        tw = w // 10
        th = h // 10
        p = f.parent
        for x in range(0, 10):
            for y in range(0, 10):
                tx = x * tw
                ty = y * th
                box = (tx, ty, tx + tw, ty + th)
                out = im.crop(box)
                out.save(p / f'tile_{x}_{y}.png')


def combine(p):
    with Image.new('RGBA', (1600, 1440)) as out:
        for x in range(0, 10):
            for y in range(0, 10):
                with Image.open(p / f'tile_{x}_{y}.png') as i:
                    tx = x * 160
                    ty = y * 144
                    out.paste(i, (tx, ty))
        out.save(p / 'result.png')


def main():
    with Image.open('part_1/dsa_challenge.png') as im:
        fill(im, (35, 30), (63, 0, 0, 255))
        fill(im, (95, 30), (127, 0, 0, 255))
        fill(im, (125, 30), (191, 0, 0, 255))
        fill(im, (20, 65), (255, 0, 0, 255))
        fill(im, (43, 82), (0, 63, 0, 255))
        fill(im, (60, 90), (0, 127, 0, 255))
        fill(im, (65, 80), (0, 191, 0, 255))
        fill(im, (77, 80), (0, 255, 0, 255))
        fill(im, (101, 102), (0, 0, 63, 255))
        fill(im, (110, 90), (0, 0, 127, 255))
        fill(im, (120, 90), (0, 0, 191, 255))
        fill(im, (150, 102), (0, 0, 255, 255))
        im.show()

    fills = [((6, 9), (0, 0), (255, 0, 0, 255)),
             ((0, 1), (0, 50), (32, 160, 137, 255)),
             ((2, 2), (80, 62), (58, 212, 109, 255)),
             ((6, 1), (140, 56), (58, 118, 221, 255))]

    crop(Path('part_2/dsa_challenge_2.png'))
    world_fill(Path('part_2'), fills)
    combine(Path('part_2'))

    crop(Path('part_2/dsa_challenge_2.png'))
    concurrent_world_fill(Path('part_2'), fills)
    combine(Path('part_2'))


if __name__ == '__main__':
    main()
