"""Mencari garis balap langsung dari permukaan aspal model GLB.

1. Semua permukaan menghadap ke atas setinggi tanah dari material abu-abu
   (aspal), merah (kerb), dan putih (garis) menjadi peta jalan.
2. Peta jalan ditipiskan menjadi kerangka; jalan sempit (< 8 m) dan cabang buntu dibuang.
3. Dari sisa kerangka dipilih putaran tertutup yang paling "sirkuit": panjang,
   lebar, dan banyak kerb di sekitarnya.
4. Garis dihaluskan, diberi arah dan titik start (lihat SETTINGS di build_track_models.py),
   lalu ketinggian jalan dan batas dinding diukur dari model.
"""
import cv2
import numpy as np
from scipy import ndimage
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

from track_glb_raster import Grid, sample_triangles

RES = 1.5


def material_colours(track):
    colours = {}
    red_frac = {}
    for index, material in enumerate(track.materials):
        pbr = material.get('pbrMetallicRoughness', {})
        colour = np.array(pbr.get('baseColorFactor', [1, 1, 1, 1]), np.float64)
        rgb, alpha = colour[:3], colour[3]
        rf = 0.0
        texture = pbr.get('baseColorTexture')
        if texture is not None:
            source = track.document['textures'][texture['index']].get('source')
            if source is not None:
                image = track.open_image(source).convert('RGBA').resize((24, 24))
                pixels = np.asarray(image, np.float64).reshape(-1, 4) / 255
                rgb = rgb * pixels[:, :3].mean(0)
                alpha = alpha * pixels[:, 3].mean()
                pr = pixels[:, 0] * colour[0]
                pg = pixels[:, 1] * colour[1]
                pb = pixels[:, 2] * colour[2]
                rf = float(((pr - np.maximum(pg, pb)) > 0.15).mean())
        colours[index] = (rgb, alpha)
        red_frac[index] = rf
    return colours, red_frac


_NON_ROAD_KEYWORDS = (
    'box', 'roof', 'gstand', 'grandstand', 'wall', 'fence', 'vehicle', 'gantry',
    'pole', 'fpole', 'crowd', 'tent', 'build', 'bldg', 'hotel', 'house', 'glass', 'metal',
    'galvan', 'barrier', 'tyre', 'sign', 'tree', 'pine', 'branch', 'parking',
    'park', 'pitlane', 'seat', 'stair', 'rail', 'marshal', 'electric', 'garage',
    'grass', 'sand', 'dirt', 'water', 'curtain', 'top2', 'top_b', 'top-ext',
    'top_new', 'merged_materials', 'Vehicles',
)

_BUILDING_KEYWORDS = (
    'box', 'roof', 'gstand', 'grandstand', 'wall', 'fence', 'vehicle', 'gantry',
    'pole', 'fpole', 'crowd', 'tent', 'build', 'bldg', 'hotel', 'house', 'glass', 'metal',
    'galvan', 'barrier', 'tyre', 'sign', 'tree', 'pine', 'branch', 'seat',
    'stair', 'rail', 'marshal', 'electric', 'garage',
)


def _has_keyword(name, keywords):
    low = name.lower()
    return any(k.lower() in low for k in keywords)


class Surfaces:
    """Sampel permukaan menghadap atas beserta jenisnya."""

    ROAD, KERB, WHITE, OTHER = 1, 2, 3, 0

    def __init__(self, track, extra_road=(), not_road=()):
        colours, red_frac = material_colours(track)
        a, b, c, m = track.triangles()
        normal = np.cross(b - a, c - a)
        area = np.linalg.norm(normal, axis=1) / 2
        normal /= np.maximum(area[:, None] * 2, 1e-9)
        opaque = np.array([colours[i][1] >= 0.5 for i in range(len(track.materials))] + [True])
        up = (np.abs(normal[:, 1]) > 0.75) & opaque[m]
        kinds = np.zeros(len(track.materials) + 1, np.int8)
        buildings = np.zeros(len(track.materials) + 1, bool)
        for index, (rgb, alpha) in colours.items():
            name = track.materials[index].get('name', '')
            upward = area[up & (m == index)].sum()
            lum, sat = rgb.mean(), rgb.max() - rgb.min()
            if name in not_road or _has_keyword(name, _BUILDING_KEYWORDS):
                buildings[index] = True
            if alpha < 0.5 or upward == 0:
                continue
            if name in not_road or _has_keyword(name, _NON_ROAD_KEYWORDS):
                continue
            if name in extra_road or (0.08 <= lum <= 0.72 and sat < 0.1 and upward < 900_000):
                kinds[index] = self.ROAD
            elif ('curb' in name.lower() or 'kerb' in name.lower() or rgb[0] - max(rgb[1], rgb[2]) > 0.1 or red_frac[index] > 0.15) and upward < 200_000:
                kinds[index] = self.KERB
            elif lum > 0.72 and sat < 0.1 and upward < 200_000:
                kinds[index] = self.WHITE
        self.kinds = kinds
        self.buildings = buildings
        self.materials = track.materials
        self.colours = colours
        self.a, self.b, self.c, self.m = a[up], b[up], c[up], m[up]
        # Area kerja: sekitar permukaan jalan/kerb (tanah raksasa di kejauhan tidak perlu disampel).
        roadish = kinds[self.m] > 0
        centres = ((self.a + self.b + self.c) / 3)[roadish][:, [0, 2]]
        low = np.percentile(centres, 0.2, axis=0) - 200
        high = np.percentile(centres, 99.8, axis=0) + 200
        self.bbox = (low[0], low[1], high[0], high[1])
        pts_road, own_road = sample_triangles(self.a[roadish], self.b[roadish], self.c[roadish], RES * 0.6, self.bbox)
        other = ~roadish
        pts_other, own_other = sample_triangles(self.a[other], self.b[other], self.c[other], RES * 2.5, self.bbox)
        m_road = self.m[roadish][own_road]
        m_other = self.m[other][own_other]
        self.points = np.concatenate([pts_road, pts_other])
        self.material = np.concatenate([m_road, m_other])
        self.kind = kinds[self.material]

    def region(self, margin=150):
        roadish = self.points[self.kind > 0]
        low = np.percentile(roadish[:, [0, 2]], 0.2, axis=0) - margin
        high = np.percentile(roadish[:, [0, 2]], 99.8, axis=0) + margin
        return low, high


def road_masks(surfaces, grid):
    p = surfaces.points
    i, j, ok = grid.cell(p[:, 0], p[:, 2])
    ground = np.full((grid.h, grid.w), np.inf)
    np.minimum.at(ground, (j[ok], i[ok]), p[ok, 1])
    # Permukaan di dekat tanah (atap, jembatan, dan gerbang diabaikan).
    near_ground = ok.copy()
    near_ground[ok] = p[ok, 1] < ground[j[ok], i[ok]] + 2.5
    sel = np.nonzero(near_ground)[0]
    sel = sel[np.argsort(p[sel, 1])]
    top = np.full((grid.h, grid.w), -1, np.int8)
    top[j[sel], i[sel]] = surfaces.kind[sel]
    material = np.full((grid.h, grid.w), -1, np.int32)
    material[j[sel], i[sel]] = surfaces.material[sel]
    masks = {name: top == kind for name, kind in (('road', 1), ('kerb', 2), ('white', 3))}
    masks['material'] = material
    # Kehadiran tiap material di tiap sel, walau tertutup lapisan lain (marka, bekas ban).
    cells = (j[sel] * grid.w + i[sel]).astype(np.int64)
    pairs = np.unique(surfaces.material[sel].astype(np.int64) * (grid.h * grid.w) + cells)
    masks['pairs'] = (pairs // (grid.h * grid.w), pairs % (grid.h * grid.w))
    kerb_any = np.zeros(grid.h * grid.w, bool)
    kerb_any[cells[surfaces.kind[sel] == Surfaces.KERB]] = True
    masks['kerb_any'] = kerb_any.reshape(grid.h, grid.w)
    white_any = np.zeros(grid.h * grid.w, bool)
    white_any[cells[surfaces.kind[sel] == Surfaces.WHITE]] = True
    masks['white_any'] = white_any.reshape(grid.h, grid.w)
    return masks


def material_mask(masks, shape, chosen):
    mats, cells = masks['pairs']
    mask = np.zeros(shape[0] * shape[1], bool)
    mask[cells[np.isin(mats, chosen)]] = True
    return mask.reshape(shape)


def race_surface(masks, surfaces, verbose=False):
    """Aspal lintasan = material abu-abu yang paling sering bersebelahan dengan kerb."""
    shape = masks['road'].shape
    near_kerb = (ndimage.distance_transform_edt(~masks['kerb_any']) * RES < 4.5).reshape(-1)
    mats, cells = masks['pairs']
    names = {k: m.get('name', str(k)) for k, m in enumerate(surfaces.materials)}
    stats = []
    for k in np.unique(mats):
        if surfaces.kinds[k] != Surfaces.ROAD:
            continue
        rgb = surfaces.colours[k][0]
        if rgb[0] - rgb[2] > 0.06:  # kerikil/pasir kekuningan
            continue
        mine = cells[mats == k]
        touching = int(near_kerb[mine].sum())
        stats.append((touching, len(mine), int(k)))
    stats.sort(reverse=True)
    if not stats:
        return np.zeros(shape, bool), []
    # Aspal lintasan berbentuk pita: banyak menyentuh kerb dibanding luasnya.
    # Paddock/parkir yang luas hanya menyentuh kerb di sebagian kecil tepinya.
    ribbons = [s for s in stats if s[0] / max(s[1], 1) >= 0.05] or stats
    primary = ribbons[0][0] or 1
    chosen = [ribbons[0][2]]
    for touching, total, k in stats:
        ratio = touching / max(total, 1)
        if verbose:
            print(f'    {names[k][:30]:30} touch={touching:7} cells={total:8} ratio={ratio:.3f}')
        if k not in chosen and ratio >= 0.05 and touching >= 0.04 * primary:
            chosen.append(k)
    mask = material_mask(masks, shape, chosen)
    near = ndimage.distance_transform_edt(~mask) * RES < 5
    return mask | ((masks['kerb_any'] | masks['white_any']) & near), chosen


def _neighbours(skeleton):
    kernel = np.ones((3, 3), np.uint8)
    kernel[1, 1] = 0
    return cv2.filter2D(skeleton.astype(np.uint8), -1, kernel, borderType=cv2.BORDER_CONSTANT) * skeleton


def prune(skeleton, steps):
    skeleton = skeleton.copy()
    for _ in range(steps):
        ends = (_neighbours(skeleton) == 1)
        if not ends.any():
            break
        skeleton &= ~ends
    # sisa piksel tunggal
    skeleton &= _neighbours(skeleton) > 0
    return skeleton


OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def bridge_gaps(skeleton, max_gap, walk=10):
    """Sambung ujung-ujung kerangka yang saling berhadapan (celah garis start, jembatan, marka)."""
    skeleton = skeleton.copy()
    count = _neighbours(skeleton)
    ends = [tuple(p) for p in np.argwhere(skeleton & (count == 1))]
    info = []
    for end in ends:
        seen, cur = {end}, end
        for _ in range(walk):
            nxt = None
            for dr, dc in OFFSETS:
                cand = (cur[0] + dr, cur[1] + dc)
                if cand not in seen and 0 <= cand[0] < skeleton.shape[0] and 0 <= cand[1] < skeleton.shape[1] and skeleton[cand]:
                    nxt = cand
                    break
            if nxt is None:
                break
            seen.add(nxt)
            cur = nxt
        direction = np.array(end, float) - np.array(cur, float)
        norm = np.linalg.norm(direction)
        if norm < 3:
            continue
        info.append((np.array(end, float), direction / norm))
    used = set()
    pairs = []
    for a in range(len(info)):
        for b in range(a + 1, len(info)):
            pa, da = info[a]
            pb, db = info[b]
            gap = pb - pa
            dist = np.linalg.norm(gap)
            if dist < 1 or dist > max_gap:
                continue
            along_a = gap @ da / dist
            along_b = -gap @ db / dist
            if along_a > 0.75 and along_b > 0.75:
                pairs.append((dist, a, b))
    canvas = skeleton.astype(np.uint8)
    for dist, a, b in sorted(pairs):
        if a in used or b in used:
            continue
        used.update((a, b))
        pa, pb = info[a][0], info[b][0]
        cv2.line(canvas, (int(pa[1]), int(pa[0])), (int(pb[1]), int(pb[0])), 1, 1)
    # Ujung yang masih buntu: sambung ke kerangka terdekat di depannya (pertemuan bentuk T).
    pixels = np.argwhere(skeleton).astype(float)
    tree = cKDTree(pixels)
    for k, (pa, da) in enumerate(info):
        if k in used:
            continue
        best = None
        for q in tree.query_ball_point(pa, max_gap):
            gap = pixels[q] - pa
            dist = np.linalg.norm(gap)
            if dist < walk * 1.5:
                continue
            if gap @ da / dist > 0.8 and (best is None or dist < best[0]):
                best = (dist, pixels[q])
        if best is not None:
            cv2.line(canvas, (int(pa[1]), int(pa[0])), (int(best[1][1]), int(best[1][0])), 1, 1)
    return canvas > 0


def resample(points, spacing):
    closed = np.vstack([points, points[:1]])
    seg = np.linalg.norm(np.diff(closed[:, :2], axis=0), axis=1)
    cum = np.concatenate([[0], np.cumsum(seg)])
    n = max(16, int(round(cum[-1] / spacing)))
    t = np.linspace(0, cum[-1], n, endpoint=False)
    return np.column_stack([np.interp(t, cum, closed[:, k]) for k in range(points.shape[1])])


def smooth_loop(values, passes, weight=0.5):
    out = values.copy()
    for _ in range(passes):
        out = out * (1 - weight) + (np.roll(out, 1, 0) + np.roll(out, -1, 0)) * weight / 2
    return out


def find_loop(surfaces, min_width=7.0, debug=None, verbose=False, materials=None):
    low, high = surfaces.region()
    grid = Grid(low, high, RES)
    masks = road_masks(surfaces, grid)
    names = {k: m.get('name', str(k)) for k, m in enumerate(surfaces.materials)}
    if materials:
        chosen_materials = [k for k, n in names.items() if n in materials]
        road = material_mask(masks, masks['road'].shape, chosen_materials)
        near = ndimage.distance_transform_edt(~road) * RES < 5
        road |= (masks['kerb_any'] | masks['white_any']) & near
    else:
        road, chosen_materials = race_surface(masks, surfaces, verbose)
    if verbose:
        print('  aspal:', [names[k] for k in chosen_materials])
    road = ndimage.binary_closing(road, structure=np.ones((3, 3)), iterations=3)
    # pertahankan hanya bagian besar
    labels, n = ndimage.label(road, structure=np.ones((3, 3)))
    if n > 1:
        sizes = ndimage.sum(road, labels, range(1, n + 1))
        road = np.isin(labels, np.nonzero(sizes >= sizes.max() * 0.15)[0] + 1)
    holes = ndimage.binary_fill_holes(road) & ~road
    labels, n = ndimage.label(holes)
    if n:
        sizes = ndimage.sum(holes, labels, range(1, n + 1)) * RES * RES
        small = np.isin(labels, np.nonzero(sizes < 250)[0] + 1)
        road |= small
    depth = ndimage.distance_transform_edt(road) * RES
    # Celah pada aspal (garis start, sambungan material) ditutup lewat kerangka.
    skeleton = cv2.ximgproc.thinning(road.astype(np.uint8) * 255) > 0
    skeleton &= depth >= min_width / 2
    bridges = bridge_gaps(skeleton, 45 / RES) & ~skeleton
    road |= ndimage.binary_dilation(bridges, iterations=3)
    depth = ndimage.distance_transform_edt(road) * RES

    # Infield = lubang terbesar yang dikelilingi aspal. Garis tengah = titik aspal yang
    # sama jauhnya dari infield dan dari luar lintasan.
    holes = ndimage.binary_fill_holes(road) & ~road
    labels, n = ndimage.label(holes)
    if not n:
        raise RuntimeError('aspal tidak membentuk putaran tertutup')
    sizes = ndimage.sum(holes, labels, range(1, n + 1))
    infield = labels == np.argmax(sizes) + 1
    outside = ~road & ~infield
    to_in = ndimage.distance_transform_edt(~infield)
    to_out = ndimage.distance_transform_edt(~outside)
    inner = infield | (road & (to_in <= to_out))
    inner = ndimage.binary_opening(inner, iterations=1) | infield
    contours, _ = cv2.findContours(inner.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pixels = max(contours, key=cv2.contourArea)[:, 0, ::-1].astype(np.float64)
    skeleton = np.zeros_like(road)
    skeleton[pixels[:, 0].astype(int), pixels[:, 1].astype(int)] = True
    xz = np.column_stack([grid.x0 + (pixels[:, 1] + 0.5) * RES, grid.z0 + (pixels[:, 0] + 0.5) * RES])
    if debug is not None:
        debug.update(grid=grid, road=road, skeleton=skeleton, masks=masks, depth=depth, materials=[names[k] for k in chosen_materials])
    return xz, grid, road, depth


def _snap_road(mask, edt, grid, x, z, radius=24.0):
    i0 = int(np.clip(round((x - grid.x0) / grid.res - 0.5), 0, grid.w - 1))
    j0 = int(np.clip(round((z - grid.z0) / grid.res - 0.5), 0, grid.h - 1))
    r_px = int(np.ceil(radius / grid.res))
    j1, j2 = max(0, j0 - r_px), min(grid.h, j0 + r_px + 1)
    i1, i2 = max(0, i0 - r_px), min(grid.w, i0 + r_px + 1)
    sub = mask[j1:j2, i1:i2]
    if sub.any():
        sj, si = np.nonzero(sub)
        jj, ii = sj + j1, si + i1
    else:
        jj, ii = np.nonzero(mask)
    dist_m = np.hypot(ii - i0, jj - j0) * grid.res
    w_edt = edt[jj, ii]
    wide = w_edt >= 3.5
    score = np.where(wide, dist_m, dist_m + 100.0) if wide.any() else dist_m - np.minimum(w_edt, 8.0) * 1.5
    k = int(np.argmin(score))
    return int(jj[k]), int(ii[k])


def trace_waypoints(surfaces, waypoints, closing=3, radius=24.0):
    """Susun garis balap tertutup melalui daftar waypoint searah laju (wp0->wp1 = start)."""
    low, high = surfaces.region()
    grid = Grid(low, high, RES)
    masks = road_masks(surfaces, grid)
    road = masks['road'] | masks['white_any']
    near_r = ndimage.binary_dilation(road, iterations=2)
    road |= masks['kerb_any'] & near_r
    road = ndimage.binary_closing(road, structure=np.ones((3, 3)), iterations=closing)
    holes = ndimage.binary_fill_holes(road) & ~road
    lbl, nh = ndimage.label(holes)
    if nh:
        sizes = ndimage.sum(holes, lbl, range(1, nh + 1)) * (RES * RES)
        road |= np.isin(lbl, np.nonzero(sizes < 150)[0] + 1)
    lbl, nc = ndimage.label(road, structure=np.ones((3, 3)))
    if nc > 1:
        sizes = ndimage.sum(road, lbl, range(1, nc + 1))
        road = lbl == (int(np.argmax(sizes)) + 1)

    edt = ndimage.distance_transform_edt(road) * RES
    h, w = road.shape
    idx = np.full((h, w), -1, np.int32)
    rj, ri = np.nonzero(road)
    n = len(rj)
    idx[rj, ri] = np.arange(n, dtype=np.int32)
    pix_cost = 1.0 + 4.0 * np.exp(-edt[rj, ri] / 3.0)
    rows, cols, vals = [], [], []
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
        step = 1.4142135 if (dr and dc) else 1.0
        j2, i2 = rj + dr, ri + dc
        ok = (j2 >= 0) & (j2 < h) & (i2 >= 0) & (i2 < w)
        u, v = idx[rj[ok], ri[ok]], idx[j2[ok], i2[ok]]
        valid = v >= 0
        u, v = u[valid], v[valid]
        rows.append(u); cols.append(v); vals.append(step * 0.5 * (pix_cost[u] + pix_cost[v]))
    graph = csr_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n))

    nodes = [int(idx[_snap_road(road, edt, grid, x, z, radius)]) for x, z in waypoints]
    full_nodes = []
    for k in range(len(nodes)):
        u, v = nodes[k], nodes[(k + 1) % len(nodes)]
        _, pred = dijkstra(graph, directed=False, indices=u, return_predecessors=True)
        seg = []
        cur = v
        while cur != -9999 and cur != u:
            seg.append(cur)
            cur = int(pred[cur])
        if cur != u:
            raise RuntimeError(f'waypoint {k} -> {(k + 1) % len(nodes)} tidak terhubung di aspal')
        seg.reverse()
        full_nodes.extend(seg)
    xz = np.column_stack([grid.x0 + (ri[full_nodes] + 0.5) * RES, grid.z0 + (rj[full_nodes] + 0.5) * RES])

    # Pakai pita aspal balap (tanpa paddock luas) untuk merapikan posisi & mengukur lebar lintasan.
    ribbon, _ = race_surface(masks, surfaces)
    ribbon = ndimage.binary_closing(ribbon, structure=np.ones((3, 3)), iterations=closing)
    ribbon_holes = ndimage.binary_fill_holes(ribbon) & ~ribbon
    rlbl, rnh = ndimage.label(ribbon_holes)
    if rnh:
        rsizes = ndimage.sum(ribbon_holes, rlbl, range(1, rnh + 1)) * (RES * RES)
        ribbon |= np.isin(rlbl, np.nonzero(rsizes < 150)[0] + 1)
    # Di segmen yg ribbon-nya putus/kosong, jatuh balik ke road.
    ri_x, rj_x, rok = grid.cell(xz[:, 0], xz[:, 1])
    covered = float(ribbon[rj_x[rok], ri_x[rok]].mean()) if rok.any() else 0.0
    width_mask = ribbon if covered >= 0.85 else road
    return xz, grid, width_mask, road, masks, edt


def orient(xz, start, ahead):
    """Putar urutan agar titik 0 di dekat `start` dan arah balap menuju `ahead`."""
    start, ahead = np.asarray(start, float), np.asarray(ahead, float)
    i = int(np.argmin(np.linalg.norm(xz - start, axis=1)))
    k = int(np.argmin(np.linalg.norm(xz - ahead, axis=1)))
    n = len(xz)
    if (k - i) % n > n / 2:
        xz = xz[::-1]
        i = n - 1 - i
    return np.roll(xz, -i, axis=0)


def centre_on_road(xz, road, grid, passes=6, reach=14.0):
    """Geser tiap titik ke tengah aspal menurut arah melintang."""
    for _ in range(passes):
        tangent = np.roll(xz, -2, 0) - np.roll(xz, 2, 0)
        tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-9)
        normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
        offsets = np.arange(-reach, reach + 0.01, RES / 2)
        probe = xz[:, None, :] + normal[:, None, :] * offsets[None, :, None]
        i, j, ok = grid.cell(probe[..., 0], probe[..., 1])
        inside = np.zeros(probe.shape[:2], bool)
        inside[ok] = road[j[ok], i[ok]]
        mid = len(offsets) // 2
        shift = np.zeros(len(xz))
        for n_i in range(len(xz)):
            row = inside[n_i]
            if not row[mid]:
                continue
            left = mid
            while left > 0 and row[left - 1]:
                left -= 1
            right = mid
            while right < len(row) - 1 and row[right + 1]:
                right += 1
            shift[n_i] = (offsets[left] + offsets[right]) / 2
        shift = smooth_loop(shift[:, None], 8)[:, 0]
        xz = xz + normal * np.clip(shift, -2.5, 2.5)[:, None]
        xz = smooth_loop(xz, 3)
    return xz


def _raycast_grid(surfaces, xz, pad=40.0, cell_size=16.0):
    """Indeks spasial segitiga non-bangunan untuk raycast vertikal tepat ke mesh GLB."""
    ground_ok = ~surfaces.buildings[surfaces.m]
    a, b, c = surfaces.a[ground_ok], surfaces.b[ground_ok], surfaces.c[ground_ok]
    tri_kind = surfaces.kinds[surfaces.m[ground_ok]]
    c_bbox = (
        float(xz[:, 0].min() - pad),
        float(xz[:, 1].min() - pad),
        float(xz[:, 0].max() + pad),
        float(xz[:, 1].max() + pad),
    )
    xmin = np.minimum(np.minimum(a[:, 0], b[:, 0]), c[:, 0])
    xmax = np.maximum(np.maximum(a[:, 0], b[:, 0]), c[:, 0])
    zmin = np.minimum(np.minimum(a[:, 2], b[:, 2]), c[:, 2])
    zmax = np.maximum(np.maximum(a[:, 2], b[:, 2]), c[:, 2])
    in_box = (xmax >= c_bbox[0]) & (xmin <= c_bbox[2]) & (zmax >= c_bbox[1]) & (zmin <= c_bbox[3])
    a, b, c, tri_kind = a[in_box], b[in_box], c[in_box], tri_kind[in_box]
    xmin, xmax, zmin, zmax = xmin[in_box], xmax[in_box], zmin[in_box], zmax[in_box]

    v0x, v0z = c[:, 0] - a[:, 0], c[:, 2] - a[:, 2]
    v1x, v1z = b[:, 0] - a[:, 0], b[:, 2] - a[:, 2]
    d00 = v0x * v0x + v0z * v0z
    d01 = v0x * v1x + v0z * v1z
    d11 = v1x * v1x + v1z * v1z
    denom = d00 * d11 - d01 * d01

    buckets = {}
    ix0 = np.floor(xmin / cell_size).astype(np.int64)
    ix1 = np.floor(xmax / cell_size).astype(np.int64)
    iz0 = np.floor(zmin / cell_size).astype(np.int64)
    iz1 = np.floor(zmax / cell_size).astype(np.int64)
    # Abaikan segitiga raksasa (> 12 sel) saat pengelompokan, cek terpisah agar cepat.
    huge = ((ix1 - ix0 + 1) * (iz1 - iz0 + 1)) > 25
    for idx in np.nonzero(~huge & (np.abs(denom) > 1e-8))[0]:
        for ix in range(ix0[idx], ix1[idx] + 1):
            for iz in range(iz0[idx], iz1[idx] + 1):
                buckets.setdefault((int(ix), int(iz)), []).append(int(idx))
    buckets = {k: np.array(v, np.int64) for k, v in buckets.items()}
    huge_idx = np.nonzero(huge & (np.abs(denom) > 1e-8))[0]

    def query(px, pz):
        cand = buckets.get((int(np.floor(px / cell_size)), int(np.floor(pz / cell_size))))
        if cand is None and not len(huge_idx):
            return (), ()
        if cand is None:
            all_c = huge_idx
        elif not len(huge_idx):
            all_c = cand
        else:
            all_c = np.concatenate([cand, huge_idx])
        v2x, v2z = px - a[all_c, 0], pz - a[all_c, 2]
        d20 = v2x * v0x[all_c] + v2z * v0z[all_c]
        d21 = v2x * v1x[all_c] + v2z * v1z[all_c]
        den = denom[all_c]
        u = (d11[all_c] * d20 - d01[all_c] * d21) / den
        v = (d00[all_c] * d21 - d01[all_c] * d20) / den
        hit = (u >= -1e-3) & (v >= -1e-3) & (u + v <= 1.001)
        if not hit.any():
            return (), ()
        idx = all_c[hit]
        ys = a[idx, 1] + (c[idx, 1] - a[idx, 1]) * u[hit] + (b[idx, 1] - a[idx, 1]) * v[hit]
        return ys, tri_kind[idx]

    return query


def road_profile(surfaces, xz, road, grid, lateral):
    """Tinggi permukaan di grid (titik garis x offset melintang) dan lebar aspal."""
    tangent = np.roll(xz, -1, 0) - np.roll(xz, 1, 0)
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-9)
    normal = np.column_stack([-tangent[:, 1], tangent[:, 0]])
    probe = xz[:, None, :] + normal[:, None, :] * lateral[None, :, None]

    n, m = probe.shape[:2]
    centre = int(np.argmin(np.abs(lateral)))
    query = _raycast_grid(surfaces, xz, pad=float(lateral.max()) + 12.0)

    # 1) Tinggi garis tengah: raycast tepat ke segitiga jalan GLB, jaga kesinambungan antar-langkah.
    hits = [query(float(xz[k, 0]), float(xz[k, 1])) for k in range(n)]
    cand_y = []
    for ys, ks in hits:
        if len(ys):
            rd = ys[ks > 0]
            cand_y.append(np.sort(rd) if len(rd) else np.sort(ys))
        else:
            cand_y.append(np.array([], float))

    centre_height = np.full(n, np.nan)
    first_valid = next((k for k in range(n) if len(cand_y[k])), None)
    if first_valid is None:
        raise RuntimeError('tinggi jalan tidak ditemukan')
    # Di garis start (0), pilih permukaan aspal terendah (menghindari atap/overpass di atas lintasan).
    start_samples = [cand_y[k][0] for k in range(first_valid, min(n, first_valid + 12)) if len(cand_y[k])]
    centre_height[first_valid] = float(np.median(start_samples))
    previous = centre_height[first_valid]
    miss = 0
    for step in range(1, n):
        k = (first_valid + step) % n
        ys = cand_y[k]
        if not len(ys):
            miss += 1
            continue
        pick = float(ys[np.argmin(np.abs(ys - previous))])
        # Terima perubahan wajar (~50% gradien + toleransi celah kecil); jika jauh, cek titik berikutnya.
        limit = 1.6 + miss * 0.8
        if abs(pick - previous) <= limit:
            centre_height[k] = pick
            previous = pick
            miss = 0
        else:
            # Cek apakah titik berikutnya sepakat dengan `pick` (transisi nyata) atau outlier jembatan.
            ahead = [cand_y[(k + off) % n] for off in (1, 2, 3)]
            agree = sum(1 for ay in ahead if len(ay) and np.min(np.abs(ay - pick)) < 1.2)
            if agree >= 2 and abs(pick - previous) < 8.0:
                centre_height[k] = pick
                previous = pick
                miss = 0
            else:
                miss += 1
    valid = np.isfinite(centre_height)
    idx = np.arange(n)
    centre_height = np.interp(idx, idx[valid], centre_height[valid], period=n)
    centre_height = smooth_loop(centre_height[:, None], 3)[:, 0]

    # 2) Tinggi melintang: menyapu keluar dari garis tengah agar tidak melompat ke atap pit/dinding.
    heights = np.repeat(centre_height[:, None], m, axis=1)
    for row in range(n):
        for direction in (-1, 1):
            prev_h = centre_height[row]
            col = centre + direction
            while 0 <= col < m:
                ys, _ = query(float(probe[row, col, 0]), float(probe[row, col, 1]))
                if len(ys):
                    pick = float(ys[np.argmin(np.abs(ys - prev_h))])
                    if abs(pick - prev_h) <= 0.80:
                        prev_h = pick
                heights[row, col] = prev_h
                col += direction
    heights[:, centre] = centre_height
    heights = ndimage.uniform_filter1d(heights, 3, axis=0, mode='wrap')

    # 3) lebar aspal kiri/kanan
    i, j, ok = grid.cell(probe[..., 0], probe[..., 1])
    inside = np.zeros((n, m), bool)
    inside[ok] = road[j[ok], i[ok]]
    left = np.zeros(n); right = np.zeros(n)
    for row in range(n):
        r = inside[row]
        a = centre
        while a > 0 and r[a - 1]:
            a -= 1
        b = centre
        while b < m - 1 and r[b + 1]:
            b += 1
        left[row] = -lateral[a]
        right[row] = lateral[b]
    return heights, centre_height, left, right, normal


def wall_distances(track, xz, centre_height, normal, reach=30.0):
    """Jarak ke penghalang tegak (dinding, pagar pembatas, ban) di kiri/kanan."""
    a, b, c, m = track.triangles()
    blend = np.array([mat.get('alphaMode') == 'BLEND' for mat in track.materials] + [False])
    nrm = np.cross(b - a, c - a)
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
    vertical = (np.abs(nrm[:, 1]) < 0.45) & ~blend[m]
    a, b, c = a[vertical], b[vertical], c[vertical]
    points, owners = sample_triangles(a, b, c, 0.8)
    if not len(points):
        return np.full(len(xz), reach), np.full(len(xz), reach)
    lo_y = np.minimum.reduce([a[:, 1], b[:, 1], c[:, 1]])[owners]
    hi_y = np.maximum.reduce([a[:, 1], b[:, 1], c[:, 1]])[owners]
    tree = cKDTree(xz)
    dist, index = tree.query(points[:, [0, 2]], distance_upper_bound=reach + 2)
    ok = np.isfinite(dist)
    points, index, lo_y, hi_y = points[ok], index[ok], lo_y[ok], hi_y[ok]
    road_y = centre_height[index]
    # penghalang menyentuh rentang tinggi bodi mobil
    blocking = (lo_y < road_y + 0.9) & (hi_y > road_y + 0.35)
    points, index = points[blocking], index[blocking]
    offset = points[:, [0, 2]] - xz[index]
    lateral = (offset * normal[index]).sum(1)
    left = np.full(len(xz), reach)
    right = np.full(len(xz), reach)
    np.minimum.at(left, index[lateral < 0], -lateral[lateral < 0])
    np.minimum.at(right, index[lateral > 0], lateral[lateral > 0])
    # dinding tidak boleh tiba-tiba hilang: ambil minimum dari tetangga
    left = ndimage.minimum_filter1d(left, 3, mode='wrap')
    right = ndimage.minimum_filter1d(right, 3, mode='wrap')
    return left, right
