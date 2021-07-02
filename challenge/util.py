from PIL import Image
from pathlib import Path


def crop(file: Path):
    with Image.open(file) as im:
        w, h = im.size
        tw = w // 10
        th = h // 10
        p = file.parent
        for x in range(0, 10):
            for y in range(0, 10):
                tx = x * tw
                ty = y * th
                box = (tx, ty, tx + tw, ty + th)
                out = im.crop(box)
                out.save(p / f'tile_{x}_{y}.png')


def combine(path: Path):
    with Image.new('RGBA', (1600, 1440)) as out:
        for x in range(0, 10):
            for y in range(0, 10):
                with Image.open(path / f'tile_{x}_{y}.png') as i:
                    tx = x * 160
                    ty = y * 144
                    out.paste(i, (tx, ty))
        out.save(path / 'result.png')
