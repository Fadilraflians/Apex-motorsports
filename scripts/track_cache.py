"""Cache peta permukaan tiap sirkuit (agar langkah berikutnya cepat) + gambar peta untuk memeriksa rute.

Pakai: python scripts/track_cache.py [id ...]
Hasil: scripts/.cache/track{id}.npz dan scripts/.cache/track{id}.png
"""
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from track_glb import ROOT, Track
from track_course import RES, Surfaces, road_masks
from track_glb_raster import Grid
from track_files import FILES

CACHE = Path(__file__).resolve().parent / '.cache'


def build_cache(track_id, track=None):
    CACHE.mkdir(exist_ok=True)
    track = track or Track(ROOT / 'Track' / FILES[track_id])
    surfaces = Surfaces(track)
    low, high = surfaces.region()
    grid = Grid(low, high, RES)
    masks = road_masks(surfaces, grid)
    p = surfaces.points
    i, j, ok = grid.cell(p[:, 0], p[:, 2])
    ground = np.full((grid.h, grid.w), np.inf, np.float32)
    np.minimum.at(ground, (j[ok], i[ok]), p[ok, 1].astype(np.float32))
    np.savez_compressed(
        CACHE / f'track{track_id}.npz',
        x0=grid.x0, z0=grid.z0, res=RES, w=grid.w, h=grid.h,
        road=masks['road'], kerb=masks['kerb'], white=masks['white'], material=masks['material'], ground=ground,
    )
    return track, surfaces, grid, masks


def load_cache(track_id):
    data = np.load(CACHE / f'track{track_id}.npz')
    grid = Grid((float(data['x0']), float(data['z0'])), (0, 0), float(data['res']))
    grid.w, grid.h = int(data['w']), int(data['h'])
    return grid, {k: data[k] for k in ('road', 'kerb', 'white', 'material', 'ground')}


def draw_map(track_id, grid, masks, path=None, points=(), out=None):
    img = np.zeros((grid.h, grid.w, 3), np.uint8) + 18
    img[masks['road']] = 95
    img[masks['white']] = 200
    img[masks['kerb']] = (220, 40, 40)
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)
    to_px = lambda x, z: ((x - grid.x0) / grid.res, (z - grid.z0) / grid.res)
    for x in np.arange(np.ceil(grid.x0 / 100) * 100, grid.x0 + grid.w * grid.res, 100):
        cx = to_px(x, 0)[0]
        d.line([(cx, 0), (cx, grid.h)], fill=(25, 60, 110) if x % 500 else (40, 110, 200))
        d.text((cx + 2, 2), str(int(x)), fill=(255, 230, 0))
    for z in np.arange(np.ceil(grid.z0 / 100) * 100, grid.z0 + grid.h * grid.res, 100):
        cz = to_px(0, z)[1]
        d.line([(0, cz), (grid.w, cz)], fill=(25, 60, 110) if z % 500 else (40, 110, 200))
        d.text((2, cz + 2), str(int(z)), fill=(255, 230, 0))
    if path is not None:
        pix = [to_px(x, z) for x, z in path]
        n = len(pix)
        for k in range(n):
            f = k / n
            d.line([pix[k], pix[(k + 1) % n]], fill=(int(255 * (1 - f)), int(255 * f), 255), width=3)
    for k, (x, z) in enumerate(points):
        px, pz = to_px(x, z)
        d.ellipse([px - 5, pz - 5, px + 5, pz + 5], outline=(255, 255, 0), width=2)
        d.text((px + 6, pz - 6), str(k), fill=(255, 255, 0))
    im.save(out or CACHE / f'track{track_id}.png')


if __name__ == '__main__':
    for track_id in [int(v) for v in sys.argv[1:]] or range(1, 11):
        t = time.time()
        _, _, grid, masks = build_cache(track_id)
        draw_map(track_id, grid, masks)
        print(track_id, grid.w, grid.h, f'{time.time() - t:.0f}s', flush=True)
