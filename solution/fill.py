from queue import Queue
from threading import Thread, Lock
from PIL import Image
from pathlib import Path

TilePosition = tuple[int, int]
TileDimension = tuple[int, int]
Color = tuple[int, int, int, int]


def fill(image: Image, position: TilePosition, color: Color):
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


def update_edges(edges: dict[str, set[TilePosition]], edge: str, pos: TilePosition):
    e = edges.get(edge, set())
    e.add(pos)
    edges[edge] = e


def tile_fill(file: Path, tile_positions: set[TilePosition], from_color: Color,
              to_color: Color) -> dict[Path, set[TilePosition]]:
    edges = dict()
    with Image.open(file) as im:
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
        im.save(file)
    return edges


# fills color across multiple tiles. Each tile is stored in a file
# 'tile_{x}_{y}.png'. The fill starts from the local x, y position in that
# tile.
def world_fill(dir: Path, world_position: TilePosition, world_dimension: TileDimension,
               tile_position: TilePosition, tile_dimension: TileDimension,
               color: Color):
    fx, fy = world_position
    fw, fh = world_dimension
    w, h = tile_dimension
    file = dir / f'tile_{fx}_{fy}.png'
    with Image.open(file) as im:
        original_color = im.getpixel(tile_position)
    work = Queue()
    in_process = set()
    mutex = Lock()
    work.put(((fx, fy), {tile_position}, original_color, color))
    Worker(dir, fh, fw, h, w, work, in_process, mutex).start()
    Worker(dir, fh, fw, h, w, work, in_process, mutex).start()
    Worker(dir, fh, fw, h, w, work, in_process, mutex).start()
    Worker(dir, fh, fw, h, w, work, in_process, mutex).start()
    work.join()


class Worker(Thread):
    def __init__(self, dir: Path, fh, fw, h, w, work, in_process, mutex):
        Thread.__init__(self, daemon=True)
        self.dir = dir
        self.fh = fh
        self.fw = fw
        self.h = h
        self.w = w
        self.work = work
        self.in_process = in_process
        self.mutex = mutex
    
    def run(self):
        while True:
            (fx, fy), tp, from_color, to_color = self.work.get()
            f = self.dir / f'tile_{fx}_{fy}.png'
            with self.mutex:
                if f in self.in_process:
                    self.work.put(((fx, fy), tp, from_color, to_color))
                    self.work.task_done()
                    continue
                else:
                    self.in_process.add(f)
            edges = tile_fill(f, tp, from_color, to_color)
            with self.mutex:
                self.in_process.remove(f)
            if 'left' in edges and fx > 0:
                new_positions = {(self.w - 1, y) for (x, y) in edges['left']}
                self.work.put(((fx - 1, fy), new_positions, from_color, to_color))
            if 'top' in edges and fy > 0:
                new_positions = {(x, self.h - 1) for (x, y) in edges['top']}
                self.work.put(((fx, fy - 1), new_positions, from_color, to_color))
            if 'right' in edges and fx + 1 < self.fw:
                new_positions = {(0, y) for (x, y) in edges['right']}
                self.work.put(((fx + 1, fy), new_positions, from_color, to_color))
            if 'bottom' in edges and fy + 1 < self.fh:
                new_positions = {(x, 0) for (x, y) in edges['bottom']}
                self.work.put(((fx, fy + 1), new_positions, from_color, to_color))
            self.work.task_done()


def crop(f: Path):
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


def combine(p: Path):
    with Image.new('RGBA', (1600, 1440)) as out:
        for x in range(0, 10):
            for y in range(0, 10):
                with Image.open(p / f'tile_{x}_{y}.png') as i:
                    tx = x * 160
                    ty = y * 144
                    out.paste(i, (tx, ty))
        out.save(p / 'result.png')


def main():
    with Image.open('../part_1/dsa_challenge.png') as im:
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
    
    crop(Path('../part_2/dsa_challenge_2.png'))
    world_fill(Path('../part_2'), (6, 9), (10, 10), (0, 0), (160, 144), (255, 0, 0, 255))
    world_fill(Path('../part_2'), (0, 1), (10, 10), (0, 50), (160, 140), (32, 160, 137, 255))
    world_fill(Path('../part_2'), (2, 2), (10, 10), (80, 62), (160, 144), (58, 212, 109, 255))
    world_fill(Path('../part_2'), (6, 1), (10, 10), (140, 56), (160, 144), (58, 118, 221, 255))
    combine(Path('../part_2'))


if __name__ == '__main__':
    main()
