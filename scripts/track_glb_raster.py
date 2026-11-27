"""Rasterisasi segitiga dari atas (bidang XZ) untuk analisis lintasan."""
import numpy as np


def sample_triangles(a, b, c, spacing, bbox=None):
    """Titik sampel merata di permukaan tiap segitiga. Mengembalikan (titik, nomor segitiga).

    bbox = (xmin, zmin, xmax, zmax) membuang sampel di luar area (hemat memori)."""
    edges = np.maximum.reduce([
        np.linalg.norm((b - a)[:, [0, 2]], axis=1),
        np.linalg.norm((c - b)[:, [0, 2]], axis=1),
        np.linalg.norm((a - c)[:, [0, 2]], axis=1),
    ])
    k = np.clip(np.ceil(edges / spacing), 1, 900).astype(np.int64)
    points, owners = [], []
    for level in np.unique(k):
        chosen = np.nonzero(k == level)[0]
        # pusat sub-segitiga pada pembagian level x level
        uv = []
        for i in range(level):
            for j in range(level - i):
                uv.append(((i + 1 / 3) / level, (j + 1 / 3) / level))
                if i + j < level - 1:
                    uv.append(((i + 2 / 3) / level, (j + 2 / 3) / level))
        uv = np.array(uv)
        # batasi memori: proses per potongan
        step = max(1, 2_000_000 // len(uv))
        for start in range(0, len(chosen), step):
            idx = chosen[start:start + step]
            pa, pb, pc = a[idx], b[idx], c[idx]
            p = pa[:, None] + (pb - pa)[:, None] * uv[None, :, 0:1] + (pc - pa)[:, None] * uv[None, :, 1:2]
            p = p.reshape(-1, 3).astype(np.float32)
            o = np.repeat(idx, len(uv))
            if bbox is not None:
                keep = (p[:, 0] >= bbox[0]) & (p[:, 2] >= bbox[1]) & (p[:, 0] <= bbox[2]) & (p[:, 2] <= bbox[3])
                p, o = p[keep], o[keep]
            points.append(p)
            owners.append(o)
    if not points:
        return np.zeros((0, 3)), np.zeros(0, np.int64)
    return np.concatenate(points), np.concatenate(owners)


class Grid:
    def __init__(self, low, high, res):
        self.res = res
        self.x0, self.z0 = low[0], low[1]
        self.w = int(np.ceil((high[0] - low[0]) / res)) + 1
        self.h = int(np.ceil((high[1] - low[1]) / res)) + 1

    def cell(self, x, z):
        i = np.floor((x - self.x0) / self.res).astype(np.int64)
        j = np.floor((z - self.z0) / self.res).astype(np.int64)
        ok = (i >= 0) & (i < self.w) & (j >= 0) & (j < self.h)
        return i, j, ok

    def splat(self, points, values=None, mode='max'):
        out = np.zeros((self.h, self.w), np.float64) if mode != 'max' else np.full((self.h, self.w), -np.inf)
        i, j, ok = self.cell(points[:, 0], points[:, 2])
        v = np.ones(len(points)) if values is None else values
        if mode == 'max':
            np.maximum.at(out, (j[ok], i[ok]), v[ok])
        else:
            np.add.at(out, (j[ok], i[ok]), v[ok])
        return out
