"""Generator sirkuit Aventador Racing Circuit (ID 11) dengan geometri & tekstur PBR realistis."""
from pathlib import Path
import io
import json
import math
import re
import struct

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'public' / 'tracks' / '3d'
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. Spline lintasan & profil elevasi alami
# ---------------------------------------------------------------------------
CP = np.array([
    [0, 0], [120, 0], [200, 60], [200, 160], [120, 220], [20, 200],
    [-40, 140], [-120, 150], [-200, 90], [-180, -10], [-100, -60], [-50, -20],
], dtype=float)


def catmull(p0, p1, p2, p3, t):
    return 0.5 * (
        (2 * p1)
        + (-p0 + p2) * t
        + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t
        + (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t
    )


dense = []
for i in range(len(CP)):
    for j in range(100):
        dense.append(catmull(CP[(i - 1) % len(CP)], CP[i], CP[(i + 1) % len(CP)], CP[(i + 2) % len(CP)], j / 100.0))
dense = np.array(dense)
dense = np.vstack([dense, dense[0]])
delta = np.diff(dense, axis=0)
cumulative = np.r_[0.0, np.cumsum(np.linalg.norm(delta, axis=1))]
raw_length = float(cumulative[-1])
scale = 4310.0 / raw_length
N = 2155
targets = np.linspace(0.0, raw_length, N, endpoint=False)
points = np.column_stack([np.interp(targets, cumulative, dense[:, 0]), np.interp(targets, cumulative, dense[:, 1])]) * scale
x, z = points[:, 0], points[:, 1]

tang = np.roll(points, -2, axis=0) - np.roll(points, 2, axis=0)
tang /= np.maximum(np.linalg.norm(tang, axis=1)[:, None], 1e-8)
# Normal arah kanan saat menghadap tang (sesuai konvensi game: pt(k, o) = center + right * o)
right_nx = -tang[:, 1]
right_nz = tang[:, 0]

# Hitung kelengkungan lintasan untuk menentukan zona kerb, gravel trap, & papan rem.
d_tang = np.roll(tang, -4, axis=0) - np.roll(tang, 4, axis=0)
curv = (tang[:, 0] * d_tang[:, 1] - tang[:, 1] * d_tang[:, 0]) / 16.0  # +belok kanan, -belok kiri

# Profil elevasi lembut sepanjang lintasan: datar di start/finish, naik-turun alami di sektor tengah.
phase = np.linspace(0.0, math.tau, N, endpoint=False)
flat_straight = np.clip((np.abs(np.sin(phase / 2.0)) - 0.10) / 0.25, 0.0, 1.0)
flat_straight = flat_straight * flat_straight * (3.0 - 2.0 * flat_straight)
y = flat_straight * (7.2 * np.sin(phase - 0.35) + 4.4 * np.sin(2.0 * phase + 0.6) - 2.2 * np.cos(3.0 * phase))
y = y - y[0]
# Haluskan melingkar agar kemiringan sangat mulus (<4%).
for _ in range(18):
    y = 0.25 * np.roll(y, 1) + 0.5 * y + 0.25 * np.roll(y, -1)
y = np.round(y, 4)


def min_dist_sq(px: float, pz: float) -> float:
    return float(np.min((x - px) ** 2 + (z - pz) ** 2))


def rect_clear(cx: float, cz: float, sx: float, sz: float, angle_y: float = 0.0, min_clear: float = 20.5) -> bool:
    ca, sa = math.cos(angle_y), math.sin(angle_y)
    hx, hz = sx * 0.5, sz * 0.5
    samples = [(0.0, 0.0), (-hx, -hz), (hx, -hz), (hx, hz), (-hx, hz), (-hx, 0.0), (hx, 0.0), (0.0, -hz), (0.0, hz)]
    limit_sq = min_clear * min_clear
    for lx, lz in samples:
        wx = cx + lx * ca - lz * sa
        wz = cz + lx * sa + lz * ca
        if min_dist_sq(wx, wz) < limit_sq:
            return False
    return True


def track_pt(idx: int, offset: float, dy: float = 0.0):
    k = idx % N
    return (float(x[k] + right_nx[k] * offset), float(y[k] + dy), float(z[k] + right_nz[k] * offset))


# Simpan data fisika lintasan 11.json dengan profil tinggi lateral yang sesuai persis.
LATERAL = list(range(-30, 31, 5))  # 13 nilai (-30 .. +30)
heights = []
for i in range(N):
    yi = float(y[i])
    for lat in LATERAL:
        if abs(lat) <= 18.0:
            heights.append(round(yi, 3))
        else:
            extra = (abs(lat) - 18.0) * 0.025
            heights.append(round(yi - extra, 3))

course = {
    'id': 11,
    'spacing': 2.0,
    'x': np.round(x, 3).tolist(),
    'z': np.round(z, 3).tolist(),
    'y': np.round(y, 3).tolist(),
    'roadLeft': [7.5] * N,
    'roadRight': [7.5] * N,
    'wallLeft': [17.4] * N,
    'wallRight': [17.4] * N,
    'lateral': LATERAL,
    'heights': heights,
}
(OUT / '11.json').write_text(json.dumps(course, separators=(',', ':')), encoding='utf-8')

# Perbarui entri track 11 di lib/track-layouts.ts secara aman (hapus duplikat lama).
layout = {'width': 36.0, 'points': [round(float(v), 2) for row in zip(x, z, y) for v in row]}
layouts_path = ROOT / 'lib' / 'track-layouts.ts'
layouts_src = layouts_path.read_text(encoding='utf-8')
layouts_src = re.sub(r'\r?\n\s*11:\s*\{[^\r\n]*\},?', '', layouts_src)
marker_pos = layouts_src.rfind('\n};')
if marker_pos == -1:
    marker_pos = layouts_src.rfind('};')
entry = '\n  11: ' + json.dumps(layout, separators=(',', ':'), ensure_ascii=False) + ','
layouts_path.write_text(layouts_src[:marker_pos] + entry + layouts_src[marker_pos:], encoding='utf-8')


# ---------------------------------------------------------------------------
# 2. Pembantu Geometri dengan UV eksplisit (v, normal, uv)
# ---------------------------------------------------------------------------
class MatBuilder:
    def __init__(self):
        self.verts = []
        self.norms = []
        self.uvs = []
        self.inds = []

    def add_tri(self, p0, p1, p2, uv0, uv1, uv2, normal=None):
        a = np.array(p0, dtype=np.float32)
        b = np.array(p1, dtype=np.float32)
        c = np.array(p2, dtype=np.float32)
        if normal is None:
            no = np.cross(b - a, c - a)
            ln = float(np.linalg.norm(no))
            n = (no / ln) if ln > 1e-8 else np.array([0.0, 1.0, 0.0], dtype=np.float32)
        else:
            n = np.array(normal, dtype=np.float32)
        base = len(self.verts)
        self.verts.extend((p0, p1, p2))
        self.norms.extend((tuple(n), tuple(n), tuple(n)))
        self.uvs.extend((uv0, uv1, uv2))
        self.inds.extend((base, base + 1, base + 2))

    def add_quad(self, p0, p1, p2, p3, uv0=(0, 0), uv1=(1, 0), uv2=(1, 1), uv3=(0, 1), normal=None):
        self.add_tri(p0, p1, p2, uv0, uv1, uv2, normal)
        self.add_tri(p0, p2, p3, uv0, uv2, uv3, normal)


# Daftar material ber-PBR tinggi:
# 0: asphalt (peta warna + normal + roughness), 1: grass_terrain, 2: runoff_tarmac,
# 3: gravel_trap, 4: kerb_rw, 5: grid_decal (garis start/grid transparan),
# 6: armco_steel, 7: concrete_barrier, 8: tire_barrier, 9: catch_fence (alpha MASK),
# 10: building_facade, 11: glass_vip (reflektif), 12: grandstand_crowd,
# 13: gantry_banner, 14: gantry_lights (emissive merah), 15: tree_foliage (alpha MASK),
# 16: tree_trunk, 17: lamp_glow (emissive hangat), 18: sign_brake
MAT_NAMES = [
    'asphalt', 'grass_terrain', 'runoff_tarmac', 'gravel_trap', 'kerb_rw',
    'grid_decal', 'armco_steel', 'concrete_barrier', 'tire_barrier', 'catch_fence',
    'building_facade', 'glass_vip', 'grandstand_crowd', 'gantry_banner', 'gantry_lights',
    'tree_foliage', 'tree_trunk', 'lamp_glow', 'sign_brake',
]
builders = {name: MatBuilder() for name in MAT_NAMES}


def add_box(mat: str, cx: float, cy: float, cz: float, sx: float, sy: float, sz: float, angle_y: float = 0.0, uv_scale: float = 0.2):
    ca, sa = math.cos(angle_y), math.sin(angle_y)
    hx, hy, hz = sx * 0.5, sy * 0.5, sz * 0.5
    local = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz),
        (-hx, hy, -hz), (hx, hy, -hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    w = [(cx + lx * ca - lz * sa, cy + ly, cz + lx * sa + lz * ca) for lx, ly, lz in local]
    b = builders[mat]
    faces = [
        ((0, 1, 2, 3), sx * uv_scale, sz * uv_scale),
        ((4, 7, 6, 5), sx * uv_scale, sz * uv_scale),
        ((0, 4, 5, 1), sx * uv_scale, sy * uv_scale),
        ((1, 5, 6, 2), sz * uv_scale, sy * uv_scale),
        ((2, 6, 7, 3), sx * uv_scale, sy * uv_scale),
        ((3, 7, 4, 0), sz * uv_scale, sy * uv_scale),
    ]
    for (i0, i1, i2, i3), us, vs in faces:
        b.add_quad(w[i0], w[i1], w[i2], w[i3], (0, 0), (us, 0), (us, vs), (0, vs))


def oriented_pt(cx: float, cy: float, cz: float, lx: float, ly: float, lz: float, angle_y: float):
    ca, sa = math.cos(angle_y), math.sin(angle_y)
    return (cx + lx * ca - lz * sa, cy + ly, cz + lx * sa + lz * ca)


# ---------------------------------------------------------------------------
# 3. Konstruksi Geometri Dunia Sirkuit
# ---------------------------------------------------------------------------
# A. Pita aspal utama (-7.6m .. +7.6m) + UV presisi (u = 0..1 melintang, v = meter / 18m)
for i in range(N):
    j = (i + 1) % N
    v0 = (i * 2.0) / 18.0
    v1 = ((i + 1) * 2.0) / 18.0
    builders['asphalt'].add_quad(
        track_pt(i, -7.6, 0.02), track_pt(j, -7.6, 0.02),
        track_pt(j, 7.6, 0.02), track_pt(i, 7.6, 0.02),
        (0.0, v0), (0.0, v1), (1.0, v1), (1.0, v0),
    )

# B. Marka Grid Start & Garis Finish Kotak-Kotak (tepat di s = -38m .. +3m)
for i_off in range(-18, 2):
    i = (N + i_off) % N
    j = (i + 1) % N
    v0 = (i_off + 18) / 20.0
    v1 = (i_off + 19) / 20.0
    builders['grid_decal'].add_quad(
        track_pt(i, -7.2, 0.036), track_pt(j, -7.2, 0.036),
        track_pt(j, 7.2, 0.036), track_pt(i, 7.2, 0.036),
        (0.0, v0), (0.0, v1), (1.0, v1), (1.0, v0),
    )

# C. Kerb FIA 3D miring di semua tikungan + zona akselerasi keluar tikungan
for i in range(N):
    j = (i + 1) % N
    c = float(curv[i])
    c_prev = float(curv[(i - 8) % N])
    c_next = float(curv[(i + 8) % N])
    peak = max(abs(c), abs(c_prev), abs(c_next))
    for side in (-1, 1):
        is_apex = (side * c > 0.0045) or (side * c_next > 0.0065)
        is_exit = (-side * c_prev > 0.006)
        if not (is_apex or is_exit or peak > 0.011):
            continue
        in_off = side * 7.55
        out_off = side * 9.05
        p00 = track_pt(i, in_off, 0.022)
        p10 = track_pt(j, in_off, 0.022)
        p11 = track_pt(j, out_off, 0.085)
        p01 = track_pt(i, out_off, 0.085)
        v0 = (i * 2.0) / 4.0
        v1 = ((i + 1) * 2.0) / 4.0
        if side < 0:
            builders['kerb_rw'].add_quad(p01, p11, p10, p00, (0, v0), (0, v1), (1, v1), (1, v0))
        else:
            builders['kerb_rw'].add_quad(p00, p10, p11, p01, (0, v0), (0, v1), (1, v1), (1, v0))

# D. Runoff aspal berwarna + Gravel trap di tikungan tajam
for i in range(N):
    j = (i + 1) % N
    for side in (-1, 1):
        outside_turn = (-side * curv[i] > 0.0075) or (-side * curv[(i - 6) % N] > 0.0085)
        w_in = side * 7.55
        w_mid = side * 12.2
        w_out = side * 17.6
        v0 = (i * 2.0) / 8.0
        v1 = ((i + 1) * 2.0) / 8.0
        if outside_turn:
            # Pita aspal runoff (7.55..11.2) + perangkap kerikil (11.2..17.6)
            p_a0, p_a1 = track_pt(i, side * 7.55, 0.012), track_pt(j, side * 7.55, 0.012)
            p_m0, p_m1 = track_pt(i, side * 11.2, 0.006), track_pt(j, side * 11.2, 0.006)
            p_o0, p_o1 = track_pt(i, w_out, -0.02), track_pt(j, w_out, -0.02)
            if side < 0:
                builders['runoff_tarmac'].add_quad(p_m0, p_m1, p_a1, p_a0, (1, v0), (1, v1), (0, v1), (0, v0))
                builders['gravel_trap'].add_quad(p_o0, p_o1, p_m1, p_m0, (0, v0), (0, v1), (1, v1), (1, v0))
            else:
                builders['runoff_tarmac'].add_quad(p_a0, p_a1, p_m1, p_m0, (0, v0), (0, v1), (1, v1), (1, v0))
                builders['gravel_trap'].add_quad(p_m0, p_m1, p_o1, p_o0, (0, v0), (0, v1), (1, v1), (1, v0))
        else:
            # Verge bahu aspal tipis + rumput datar terpotong rapi menuju barrier
            p_a0, p_a1 = track_pt(i, w_in, 0.012), track_pt(j, w_in, 0.012)
            p_m0, p_m1 = track_pt(i, side * 10.2, 0.004), track_pt(j, side * 10.2, 0.004)
            p_o0, p_o1 = track_pt(i, w_out, -0.02), track_pt(j, w_out, -0.02)
            if side < 0:
                builders['runoff_tarmac'].add_quad(p_m0, p_m1, p_a1, p_a0, (1, v0), (1, v1), (0, v1), (0, v0))
                builders['grass_terrain'].add_quad(p_o0, p_o1, p_m1, p_m0, (0, v0), (0, v1), (1, v1), (1, v0))
            else:
                builders['runoff_tarmac'].add_quad(p_a0, p_a1, p_m1, p_m0, (0, v0), (0, v1), (1, v1), (1, v0))
                builders['grass_terrain'].add_quad(p_m0, p_m1, p_o1, p_o0, (0, v0), (0, v1), (1, v1), (1, v0))

# E. Medan bukit bergelombang menyatu mulus ke lintasan & lereng pegunungan jauh
GRID_N = 96
gx = np.linspace(-1350.0, 1350.0, GRID_N)
gz = np.linspace(-1100.0, 1450.0, GRID_N)
hill_peaks = [
    (-1120, 920, 115, 340), (1040, 1080, 138, 360),
    (1120, -680, 98, 320), (-1060, -820, 105, 340),
    (180, 1280, 125, 350), (-140, -920, 88, 300),
]

gxx, gzz = np.meshgrid(gx, gz)
flat_gx = gxx.ravel()
flat_gz = gzz.ravel()
dists_sq = (flat_gx[:, None] - x[None, :]) ** 2 + (flat_gz[:, None] - z[None, :]) ** 2
nearest_idx = np.argmin(dists_sq, axis=1)
nearest_d = np.sqrt(dists_sq[np.arange(len(flat_gx)), nearest_idx])
base_track_h = y[nearest_idx] - 0.05

hill_h = np.zeros_like(flat_gx)
for px, pz, hh, rad in hill_peaks:
    hill_h += hh * np.exp(-((flat_gx - px) ** 2 + (flat_gz - pz) ** 2) / (2.0 * rad * rad))
# Gelombang terrain halus jauh dari lintasan
blend = np.clip((nearest_d - 22.0) / 55.0, 0.0, 1.0)
blend = blend * blend * (3.0 - 2.0 * blend)
# Untuk jarak < 17m (di bawah jalan yang datar), turunkan sedikit (-0.35m) agar tidak pernah z-fighting dengan jalan
subtrack_dip = np.where(nearest_d < 17.5, -0.35, 0.0)
gy_all = base_track_h + subtrack_dip + blend * (hill_h + 1.8 * np.sin(flat_gx * 0.025) * np.cos(flat_gz * 0.025))
gy_grid = gy_all.reshape(GRID_N, GRID_N)

for r in range(GRID_N - 1):
    for c in range(GRID_N - 1):
        p00 = (float(gxx[r, c]), float(gy_grid[r, c]), float(gz[r]))
        p10 = (float(gxx[r, c + 1]), float(gy_grid[r, c + 1]), float(gz[r]))
        p11 = (float(gxx[r + 1, c + 1]), float(gy_grid[r + 1, c + 1]), float(gz[r + 1]))
        p01 = (float(gxx[r + 1, c]), float(gy_grid[r + 1, c]), float(gz[r + 1]))
        uv00 = (float(gxx[r, c]) / 26.0, float(gz[r]) / 26.0)
        uv10 = (float(gxx[r, c + 1]) / 26.0, float(gz[r]) / 26.0)
        uv11 = (float(gxx[r + 1, c + 1]) / 26.0, float(gz[r + 1]) / 26.0)
        uv01 = (float(gxx[r + 1, c]) / 26.0, float(gz[r + 1]) / 26.0)
        builders['grass_terrain'].add_quad(p00, p01, p11, p10, uv00, uv01, uv11, uv10)

# F. Pembatas Lintasan Realistis: Beton Rendah + Rel Baja ARMCO + Pagar Jaring FIA + Dinding Ban
for i in range(N):
    j = (i + 1) % N
    v0 = (i * 2.0) / 6.0
    v1 = ((i + 1) * 2.0) / 6.0
    for side in (-1, 1):
        off = side * 17.65
        outer_turn = (-side * curv[i] > 0.008)
        if outer_turn:
            # Tumpukan dinding ban merah/putih di luar tikungan keras
            off_t = side * 17.45
            builders['tire_barrier'].add_quad(
                track_pt(i, off_t, -0.02), track_pt(j, off_t, -0.02),
                track_pt(j, off_t, 1.05), track_pt(i, off_t, 1.05),
                (0, v0), (1, v0), (1, v1), (0, v1),
            )
            builders['tire_barrier'].add_quad(
                track_pt(i, off_t, 1.05), track_pt(j, off_t, 1.05),
                track_pt(j, off_t + side * 0.85, 1.05), track_pt(i, off_t + side * 0.85, 1.05),
                (0, v0), (1, v0), (1, v1), (0, v1),
            )
        else:
            # Alas beton Jersey (0..0.52m) + Rel baja ARMCO bergelombang (0.52..1.18m)
            builders['concrete_barrier'].add_quad(
                track_pt(i, off, -0.04), track_pt(j, off, -0.04),
                track_pt(j, off, 0.52), track_pt(i, off, 0.52),
                (v0, 0), (v1, 0), (v1, 0.5), (v0, 0.5),
            )
            builders['armco_steel'].add_quad(
                track_pt(i, off - side * 0.06, 0.52), track_pt(j, off - side * 0.06, 0.52),
                track_pt(j, off - side * 0.06, 1.18), track_pt(i, off - side * 0.06, 1.18),
                (v0, 0), (v1, 0), (v1, 1), (v0, 1),
            )
        # Tiang pagar & jaring catch-fence FIA ber-alpha transparan di area penonton & lintasan utama
        if i < 250 or i > N - 110 or abs(curv[i]) > 0.012:
            builders['catch_fence'].add_quad(
                track_pt(i, off + side * 0.1, 1.18), track_pt(j, off + side * 0.1, 1.18),
                track_pt(j, off + side * 0.1, 3.65), track_pt(i, off + side * 0.1, 3.65),
                (v0 * 2.0, 0), (v1 * 2.0, 0), (v1 * 2.0, 1.5), (v0 * 2.0, 1.5),
            )
            if i % 4 == 0:
                px, py, pz = track_pt(i, off + side * 0.15, 1.8)
                add_box('armco_steel', px, py, pz, 0.16, 3.8, 0.16)

# G. Gerbang Start / Finish Open-Truss + 5 Lampu LED Start
yaw0 = math.atan2(float(tang[0, 1]), float(tang[0, 0]))
g_cx, g_cy, g_cz = float(x[0]), float(y[0]), float(z[0])
for side in (-1, 1):
    px, py, pz = oriented_pt(g_cx, g_cy, g_cz, 0.0, 4.4, side * 18.4, yaw0)
    add_box('armco_steel', px, py, pz, 1.1, 8.8, 1.1, yaw0)
    px2, py2, pz2 = oriented_pt(g_cx, g_cy, g_cz, 1.5, 4.4, side * 18.4, yaw0)
    add_box('armco_steel', px2, py2, pz2, 0.7, 8.8, 0.7, yaw0)
# Balok bentang atas (tinggi 6.9m..8.5m, bebas dilewati mobil!)
b_cx, b_cy, b_cz = oriented_pt(g_cx, g_cy, g_cz, 0.6, 7.6, 0.0, yaw0)
add_box('gantry_banner', b_cx, b_cy, b_cz, 2.2, 1.75, 38.4, yaw0, uv_scale=0.12)
# Panel 5 lampu LED start merah menyala menghadap grid (-X)
lp_cx, lp_cy, lp_cz = oriented_pt(g_cx, g_cy, g_cz, -0.55, 6.25, 0.0, yaw0)
add_box('concrete_barrier', lp_cx, lp_cy, lp_cz, 0.45, 0.9, 5.4, yaw0)
for pod in range(-2, 3):
    pcx, pcy, pcz = oriented_pt(g_cx, g_cy, g_cz, -0.80, 6.25, pod * 1.05, yaw0)
    add_box('gantry_lights', pcx, pcy, pcz, 0.12, 0.48, 0.48, yaw0)

# H. Kompleks Pit Lane (Sisi Kiri / Utara lurus utama) & Tribun Penonton Terbuka (Sisi Kanan / Selatan)
# Ditempatkan sepanjang idx 15 .. 165 (lintasan lurus utama), selalu dengan jarak aman >= 32m dari lintasan lain.
paddock_anchor = np.arange(15, 165, 18)
for k, idx in enumerate(paddock_anchor):
    yaw = math.atan2(float(tang[idx, 1]), float(tang[idx, 0]))
    bx, by, bz = track_pt(idx, -39.0, 0.0)
    if not rect_clear(bx, bz, 35.5, 22.0, yaw, 21.0):
        continue
    # Garasi pit modern: dinding abu gelap, kanopi miring ringan, kaca VIP biru reflektif lantai 2
    add_box('building_facade', bx, by + 5.2, bz, 34.0, 10.4, 17.0, yaw, uv_scale=0.08)
    # Jendela kaca VIP reflektif menghadap lintasan
    gx_p, gy_p, gz_p = oriented_pt(bx, by, bz, 0.0, 7.4, 8.6, yaw)
    add_box('glass_vip', gx_p, gy_p, gz_p, 31.0, 3.6, 0.35, yaw, uv_scale=0.14)
    # Atap kanopi modern bertiang tipis
    rx_p, ry_p, rz_p = oriented_pt(bx, by, bz, 0.0, 10.9, 1.5, yaw)
    add_box('armco_steel', rx_p, ry_p, rz_p, 35.5, 0.7, 22.0, yaw, uv_scale=0.1)
    # Garis merah livery sirkuit di lis atap
    lx_p, ly_p, lz_p = oriented_pt(bx, by, bz, 0.0, 10.6, 12.6, yaw)
    add_box('gantry_lights', lx_p, ly_p, lz_p, 35.5, 0.45, 0.25, yaw)

# Menara Timing Race Control yang ikonik (di belakang pit entry)
tx, ty, tz = track_pt(175, -42.0, 0.0)
if rect_clear(tx, tz, 11.2, 11.2, yaw0, 22.0):
    add_box('building_facade', tx, ty + 15.0, tz, 9.5, 30.0, 9.5, yaw0, uv_scale=0.09)
    add_box('glass_vip', tx, ty + 23.0, tz, 11.2, 6.0, 11.2, yaw0, uv_scale=0.15)
    add_box('gantry_lights', tx, ty + 28.5, tz, 10.4, 1.2, 10.4, yaw0)

# Tribun penonton terbuka bersusun rapi (sisi berlawanan dari pit, offset +39m)
for idx in range(20, 155, 22):
    yaw = math.atan2(float(tang[idx, 1]), float(tang[idx, 0]))
    sx_p, sy_p, sz_p = track_pt(idx, 39.0, 0.0)
    if not rect_clear(sx_p, sz_p, 41.0, 19.0, yaw, 21.0):
        continue
    # Basis tribun beton + 5 tingkat kursi penonton berwarna
    add_box('building_facade', sx_p, sy_p + 2.2, sz_p, 40.0, 4.4, 18.0, yaw, uv_scale=0.08)
    for tier in range(6):
        cx_t, cy_t, cz_t = oriented_pt(sx_p, sy_p, sz_p, 0.0, 4.8 + tier * 1.15, -5.5 + tier * 2.2, yaw)
        add_box('grandstand_crowd', cx_t, cy_t, cz_t, 38.5, 1.1, 2.0, yaw, uv_scale=0.22)
    # Pilar & atap kantilever tinggi terbuka (tidak menghalangi pandangan/langit!)
    for px_off in (-16.0, 0.0, 16.0):
        px_c, py_c, pz_c = oriented_pt(sx_p, sy_p, sz_p, px_off, 10.5, 8.2, yaw)
        add_box('armco_steel', px_c, py_c, pz_c, 0.65, 16.0, 0.65, yaw)
    rf_x, rf_y, rf_z = oriented_pt(sx_p, sy_p, sz_p, 0.0, 18.4, 2.5, yaw)
    add_box('armco_steel', rf_x, rf_y, rf_z, 41.0, 0.6, 17.5, yaw, uv_scale=0.08)

# I. Lampu Sorot Stadion Ramping di Sepanjang Straight & Zona Tikungan
for idx in range(10, 210, 28):
    yaw = math.atan2(float(tang[idx, 1]), float(tang[idx, 0]))
    for side in (-1, 1):
        lx, ly, lz = track_pt(idx, side * 22.0, 0.0)
        if min_dist_sq(lx, lz) < 20.0 ** 2:
            continue
        add_box('armco_steel', lx, ly + 8.5, lz, 0.45, 17.0, 0.45, yaw)
        arm_x, arm_y, arm_z = oriented_pt(lx, ly, lz, 0.0, 16.8, -side * 1.4, yaw)
        add_box('armco_steel', arm_x, arm_y, arm_z, 0.4, 0.35, 3.2, yaw)
        hx, hy, hz = oriented_pt(lx, ly, lz, 0.0, 16.5, -side * 2.4, yaw)
        add_box('lamp_glow', hx, hy, hz, 2.2, 0.45, 0.9, yaw)

# J. Papan Jarak Pengereman (150 / 100 / 50) sebelum tikungan berat
brake_zones = [
    i for i in range(60, N - 30)
    if abs(curv[(i + 75) % N]) > 0.015 and abs(curv[i]) < 0.004 and abs(curv[(i + 35) % N]) < 0.005
]
used_zones = []
for idx in brake_zones:
    if any(abs(idx - u) < 130 for u in used_zones):
        continue
    used_zones.append(idx)
    side = -1 if curv[(idx + 75) % N] > 0 else 1
    for step, board_off in ((0, 0.0), (24, 0.34), (48, 0.67)):
        b_idx = (idx + step) % N
        yaw = math.atan2(float(tang[b_idx, 1]), float(tang[b_idx, 0]))
        bx, by, bz = track_pt(b_idx, side * 19.2, 1.55)
        if min_dist_sq(bx, bz) < 18.0 ** 2:
            continue
        add_box('armco_steel', bx, by - 0.7, bz, 0.14, 1.8, 0.14, yaw)
        p0 = oriented_pt(bx, by, bz, -0.05, -0.45, -0.85, yaw)
        p1 = oriented_pt(bx, by, bz, -0.05, -0.45, 0.85, yaw)
        p2 = oriented_pt(bx, by, bz, -0.05, 0.55, 0.85, yaw)
        p3 = oriented_pt(bx, by, bz, -0.05, 0.55, -0.85, yaw)
        u0 = board_off
        u1 = board_off + 0.33
        builders['sign_brake'].add_quad(p0, p1, p2, p3, (u0, 0), (u1, 0), (u1, 1), (u0, 1))
        builders['sign_brake'].add_quad(p1, p0, p3, p2, (u0, 0), (u1, 0), (u1, 1), (u0, 1))

# K. Pohon Organik Multi-Silang Realistis (cek jarak ketat >= 27m dari semua titik jalan!)
rng_world = np.random.default_rng(4211)
tree_coords = []
for idx in range(0, N, 16):
    for side in (-1, 1):
        for ring in range(2):
            dist_lat = 29.0 + ring * 18.0 + float(rng_world.uniform(0.0, 14.0))
            jitter_s = int(rng_world.integers(-4, 5))
            tx_p, ty_p, tz_p = track_pt((idx + jitter_s) % N, side * dist_lat, 0.0)
            if min_dist_sq(tx_p, tz_p) < 27.0 ** 2:
                continue
            # Hindari area depan pit / tribun agar pemandangan utama tetap rapi
            if 10 <= idx <= 170 and abs(dist_lat) < 58.0:
                continue
            tree_coords.append((tx_p, tz_p, float(rng_world.uniform(0.78, 1.38))))

for tx_p, tz_p, sc in tree_coords:
    # Tinggi permukaan medan di posisi pohon
    gh = float(y[int(np.argmin((x - tx_p) ** 2 + (z - tz_p) ** 2))])
    for px_h, pz_h, hh, rad in hill_peaks:
        d_tr = math.hypot(tx_p - px_h, tz_p - pz_h)
        # estimasi sama dengan blend terrain
        gh += hh * math.exp(-(d_tr * d_tr) / (2.0 * rad * rad)) * 0.28
    h_tree = 9.2 * sc
    w_tree = 6.2 * sc
    add_box('tree_trunk', tx_p, gh + 1.8 * sc, tz_p, 0.48 * sc, 3.8 * sc, 0.48 * sc, uv_scale=0.4)
    # 3 bidang silang alpha-masked membentuk kanopi daun 3D rimbun berbayangan alami
    for ang_deg in (0.0, 60.0, 120.0):
        ang = math.radians(ang_deg)
        ca, sa = math.cos(ang), math.sin(ang)
        hw = w_tree * 0.5
        p0 = (tx_p - hw * ca, gh + 1.4 * sc, tz_p - hw * sa)
        p1 = (tx_p + hw * ca, gh + 1.4 * sc, tz_p + hw * sa)
        p2 = (tx_p + hw * ca, gh + 1.4 * sc + h_tree, tz_p + hw * sa)
        p3 = (tx_p - hw * ca, gh + 1.4 * sc + h_tree, tz_p - hw * sa)
        builders['tree_foliage'].add_quad(p0, p1, p2, p3, (0, 0), (1, 0), (1, 1), (0, 1), normal=(0.0, 1.0, 0.0))


# ---------------------------------------------------------------------------
# 4. Generator Tekstur Prosedural PBR (BaseColor + NormalMap + RoughnessMap)
# ---------------------------------------------------------------------------
def value_noise(w: int, h: int, grid_size: int, rng) -> np.ndarray:
    base = rng.uniform(0.0, 1.0, (grid_size, grid_size)).astype(np.float32)
    img = Image.fromarray((base * 255).astype(np.uint8), 'L').resize((w, h), Image.Resampling.BICUBIC)
    return np.asarray(img, dtype=np.float32) / 255.0


def fbm_noise(w: int, h: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    acc = (
        0.50 * value_noise(w, h, 8, rng)
        + 0.28 * value_noise(w, h, 24, rng)
        + 0.14 * value_noise(w, h, 64, rng)
        + 0.08 * rng.uniform(0.0, 1.0, (h, w)).astype(np.float32)
    )
    return np.clip(acc, 0.0, 1.0)


def make_normal_map(height_map: np.ndarray, strength: float = 2.4) -> bytes:
    gx = (np.roll(height_map, -1, axis=1) - np.roll(height_map, 1, axis=1)) * strength
    gy = (np.roll(height_map, -1, axis=0) - np.roll(height_map, 1, axis=0)) * strength
    nx, ny = -gx, -gy
    nz = np.ones_like(height_map)
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    rgb = np.stack([
        np.clip((nx / ln * 0.5 + 0.5) * 255.0, 0, 255),
        np.clip((ny / ln * 0.5 + 0.5) * 255.0, 0, 255),
        np.clip((nz / ln * 0.5 + 0.5) * 255.0, 0, 255),
    ], axis=-1).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(rgb, 'RGB').save(buf, format='WEBP', quality=86, method=4)
    return buf.getvalue()


def encode_webp(img: Image.Image, quality: int = 86) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='WEBP', quality=quality, method=5)
    return buf.getvalue()


def encode_mr(roughness: np.ndarray, metallic: float = 0.0) -> bytes:
    # glTF 2.0 metallicRoughnessTexture: G = roughness, B = metalness
    h, w = roughness.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[:, :, 1] = np.clip(roughness * 255.0, 10, 255).astype(np.uint8)
    rgb[:, :, 2] = int(np.clip(metallic * 255.0, 0, 255))
    return encode_webp(Image.fromarray(rgb, 'RGB'), quality=84)


def gen_asphalt():
    w, h = 512, 512
    n = fbm_noise(w, h, 101)
    fine = fbm_noise(w, h, 102)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = xx / w
    # Aspal gelap alami dengan butiran agregat + jejak ban balap
    base = 44.0 + (n - 0.5) * 18.0 + (fine - 0.5) * 14.0
    rubber = 0.85 * np.exp(-((u - 0.34) / 0.12) ** 2) + 0.85 * np.exp(-((u - 0.66) / 0.12) ** 2)
    base -= rubber * 12.0
    rgb = np.stack([base * 0.98, base * 1.0, base * 1.04], axis=-1)
    # Garis batas putih bersih di tepi kiri/kanan aspal
    edge_mask = ((u > 0.018) & (u < 0.036)) | ((u > 0.964) & (u < 0.982))
    rgb[edge_mask] = np.array([232.0, 232.0, 226.0]) - fine[edge_mask, None] * 18.0
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    rough = np.clip(0.84 - rubber * 0.24 + (fine - 0.5) * 0.12, 0.35, 0.94)
    rough[edge_mask] = 0.62
    return {
        'base': encode_webp(Image.fromarray(rgb, 'RGB'), 90),
        'mr': encode_mr(rough, 0.0),
        'norm': make_normal_map(fine * 0.7 + n * 0.3, strength=3.0),
        'rough_f': 1.0, 'metal_f': 0.0,
    }


def gen_grass():
    w, h = 512, 512
    n1 = fbm_noise(w, h, 201)
    n2 = fbm_noise(w, h, 202)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    stripe = 0.05 * np.sin((xx / w) * math.tau * 4.0)
    shade = 0.82 + (n1 - 0.5) * 0.36 + (n2 - 0.5) * 0.24 + stripe
    rgb = np.stack([68.0 * shade, 108.0 * shade, 42.0 * shade], axis=-1)
    # Sedikit semburat tanah kering alami
    dry = np.clip((n1 - 0.64) * 2.5, 0.0, 0.65)
    rgb[:, :, 0] += dry * 48.0
    rgb[:, :, 1] += dry * 22.0
    rgb = np.clip(rgb, 0, 255).astype(np.uint8)
    return {
        'base': encode_webp(Image.fromarray(rgb, 'RGB')),
        'mr': encode_mr(np.clip(0.88 + (n2 - 0.5) * 0.12, 0.7, 0.98), 0.0),
        'norm': make_normal_map(n2, strength=2.6),
        'rough_f': 1.0, 'metal_f': 0.0,
    }


def gen_runoff():
    w, h = 256, 256
    n = fbm_noise(w, h, 301)
    rgb = np.stack([72 + n * 24, 80 + n * 24, 92 + n * 26], axis=-1)
    return {
        'base': encode_webp(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')),
        'mr': encode_mr(np.full((h, w), 0.85), 0.0),
        'norm': make_normal_map(n, strength=1.8),
        'rough_f': 1.0, 'metal_f': 0.0,
    }


def gen_gravel():
    w, h = 256, 256
    n = fbm_noise(w, h, 351)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rake = 0.5 + 0.5 * np.sin(xx / w * math.tau * 6.0)
    pebble = 0.65 * n + 0.35 * rake
    rgb = np.stack([168 * (0.72 + 0.34 * pebble), 152 * (0.72 + 0.34 * pebble), 128 * (0.72 + 0.34 * pebble)], axis=-1)
    return {
        'base': encode_webp(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')),
        'norm': make_normal_map(pebble, strength=4.2),
        'rough_f': 0.96, 'metal_f': 0.0,
    }


def gen_kerb():
    w, h = 256, 512
    n = fbm_noise(w, h, 401)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    red_band = ((yy // (h // 2)) % 2) == 0
    rgb = np.empty((h, w, 3), dtype=np.float32)
    rgb[red_band] = np.array([208.0, 26.0, 36.0])
    rgb[~red_band] = np.array([238.0, 236.0, 228.0])
    scuff = np.clip((n - 0.52) * 1.4, 0.0, 0.45) * np.exp(-((xx / w - 0.35) / 0.3) ** 2)
    rgb = rgb * (1.0 - scuff[:, :, None]) + np.array([25.0, 25.0, 27.0]) * scuff[:, :, None]
    sawtooth = np.abs((yy % 64) - 32.0) / 32.0
    return {
        'base': encode_webp(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')),
        'norm': make_normal_map(sawtooth * 0.7 + n * 0.3, strength=3.0),
        'rough_f': 0.74, 'metal_f': 0.0,
    }


def gen_grid_decal():
    w, h = 512, 1024
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, 'RGBA')
    # Garis finish kotak-kotak di bagian atas gambar (v ~ 0.90)
    y_fin = int(h * 0.88)
    sq = 16
    for row in range(3):
        for col in range(0, w // sq):
            white = (row + col) % 2 == 0
            col_rgba = (242, 242, 238, 225) if white else (18, 20, 24, 210)
            d.rectangle((col * sq, y_fin + row * sq, (col + 1) * sq, y_fin + (row + 1) * sq), fill=col_rgba)
    # 4 kotak posisi start staggered
    for slot in range(4):
        cx = int(w * (0.31 if slot % 2 else 0.69))
        cy = int(h * (0.72 - slot * 0.17))
        d.line((cx - 46, cy + 28, cx - 46, cy, cx + 46, cy, cx + 46, cy + 28), fill=(242, 242, 236, 215), width=6)
    return {
        'base': encode_webp(img, 90),
        'alphaMode': 'BLEND', 'rough_f': 0.65, 'metal_f': 0.0,
    }


def gen_armco():
    w, h = 256, 256
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    n = fbm_noise(w, h, 501)
    rib = 0.5 + 0.5 * np.sin((yy / h) * math.tau * 3.0)
    val = 158.0 + rib * 44.0 + (n - 0.5) * 22.0
    rgb = np.stack([val * 0.96, val * 0.98, val * 1.02], axis=-1)
    return {
        'base': encode_webp(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')),
        'mr': encode_mr(np.clip(0.32 + 0.16 * (1 - rib), 0.2, 0.55), metallic=0.45),
        'norm': make_normal_map(rib * 0.85 + n * 0.15, strength=4.5),
        'rough_f': 1.0, 'metal_f': 1.0,
    }


def gen_concrete():
    w, h = 256, 256
    n = fbm_noise(w, h, 551)
    val = 175.0 + (n - 0.5) * 38.0
    rgb = np.stack([val, val * 0.99, val * 0.96], axis=-1)
    rgb[18:36, :] = [210, 26, 36]
    return {
        'base': encode_webp(Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), 'RGB')),
        'norm': make_normal_map(n, strength=2.4),
        'rough_f': 0.88, 'metal_f': 0.0,
    }


def gen_tires():
    w, h = 256, 256
    img = Image.new('RGB', (w, h), (22, 23, 26))
    d = ImageDraw.Draw(img)
    for row in range(4):
        col = (196, 26, 34) if row % 2 == 0 else (232, 232, 226)
        y0 = row * 64
        for cx in range(32, w, 64):
            d.ellipse((cx - 28, y0 + 4, cx + 28, y0 + 60), fill=col, outline=(14, 14, 16), width=3)
            d.ellipse((cx - 12, y0 + 20, cx + 12, y0 + 44), fill=(16, 17, 20))
    return {'base': encode_webp(img), 'rough_f': 0.82, 'metal_f': 0.0}


def gen_fence():
    w, h = 128, 128
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, 'RGBA')
    for off in range(-w, w * 2, 16):
        d.line((off, 0, off + h, h), fill=(165, 174, 182, 220), width=2)
        d.line((off, h, off + h, 0), fill=(140, 150, 160, 220), width=2)
    return {'base': encode_webp(img), 'alphaMode': 'MASK', 'alphaCutoff': 0.45, 'rough_f': 0.5, 'metal_f': 0.35}


def gen_facade():
    w, h = 512, 256
    img = Image.new('RGB', (w, h), (228, 232, 236))
    d = ImageDraw.Draw(img)
    # Lantai atas: panel alucobond cerah + pita sponsor motorsport
    d.rectangle((0, 0, w, 96), fill=(40, 44, 52))
    d.rectangle((0, 88, w, 102), fill=(210, 24, 36))
    # Garasi pit lantai bawah berderet rapi + lampu dalam garasi
    for gx_p in range(12, w - 40, 72):
        d.rectangle((gx_p, 118, gx_p + 56, 250), fill=(28, 32, 38), outline=(212, 214, 210), width=3)
        d.rectangle((gx_p + 6, 126, gx_p + 50, 152), fill=(248, 244, 220))
        d.rectangle((gx_p + 6, 156, gx_p + 50, 248), fill=(52, 58, 66))
    return {'base': encode_webp(img), 'rough_f': 0.55, 'metal_f': 0.15}


def gen_glass():
    w, h = 256, 256
    img = Image.new('RGB', (w, h), (38, 66, 92))
    d = ImageDraw.Draw(img)
    for y0 in range(0, h, 32):
        grad = 42 + (y0 // 4)
        d.rectangle((0, y0, w, y0 + 32), fill=(grad, grad + 36, grad + 68))
    for x0 in range(0, w, 48):
        d.line((x0, 0, x0, h), fill=(18, 24, 32), width=4)
    return {'base': encode_webp(img), 'rough_f': 0.14, 'metal_f': 0.35}


def gen_crowd():
    w, h = 256, 256
    img = Image.new('RGB', (w, h), (58, 62, 68))
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(777)
    palette = [(210, 24, 36), (235, 235, 228), (28, 72, 145), (230, 172, 28), (48, 52, 58), (242, 242, 242)]
    for py in range(10, h, 22):
        d.line((0, py + 12, w, py + 12), fill=(36, 40, 44), width=4)
        for px in range(6, w, 12):
            c = palette[int(rng.integers(0, len(palette)))]
            d.ellipse((px, py, px + 8, py + 11), fill=c)
    return {'base': encode_webp(img), 'rough_f': 0.85, 'metal_f': 0.0}


def gen_gantry():
    w, h = 1024, 128
    img = Image.new('RGB', (w, h), (18, 20, 24))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 16), fill=(214, 24, 38))
    d.rectangle((0, h - 16, w, h), fill=(214, 24, 38))
    for sq in range(0, 140, 16):
        for r in range(3):
            if (sq // 16 + r) % 2 == 0:
                d.rectangle((sq + 16, 36 + r * 18, sq + 30, 52 + r * 18), fill=(242, 242, 236))
                d.rectangle((w - sq - 30, 36 + r * 18, w - sq - 16, 52 + r * 18), fill=(242, 242, 236))
    try:
        font = ImageFont.truetype('arialbd.ttf', 46)
    except Exception:
        font = ImageFont.load_default()
    d.text((240, 36), 'AVENTADOR GRAND PRIX', fill=(248, 248, 244), font=font)
    return {'base': encode_webp(img, 90), 'rough_f': 0.45, 'metal_f': 0.25}


def gen_foliage():
    w, h = 256, 256
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img, 'RGBA')
    rng = np.random.default_rng(888)
    for _ in range(170):
        ry = float(rng.uniform(0.08, 0.94))
        spread = (1.0 - ry * 0.45) * 0.44
        cx = int(w * (0.5 + rng.uniform(-spread, spread)))
        cy = int(h * (1.0 - ry))
        rad = int(rng.uniform(12, 26))
        g_col = (
            int(34 + ry * 32 + rng.integers(-10, 12)),
            int(68 + ry * 56 + rng.integers(-12, 16)),
            int(26 + ry * 18 + rng.integers(-6, 8)),
            255,
        )
        d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=g_col)
    return {'base': encode_webp(img), 'alphaMode': 'MASK', 'alphaCutoff': 0.5, 'rough_f': 0.92, 'metal_f': 0.0}


def gen_brake_atlas():
    w, h = 768, 256
    img = Image.new('RGB', (w, h), (242, 242, 238))
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype('arialbd.ttf', 112)
    except Exception:
        font = ImageFont.load_default()
    for idx_b, label in enumerate(('150', '100', '50')):
        x0 = idx_b * 256
        d.rectangle((x0 + 8, 8, x0 + 248, 248), outline=(24, 26, 30), width=10)
        d.text((x0 + (28 if len(label) == 3 else 58), 64), label, fill=(20, 22, 26), font=font)
    return {'base': encode_webp(img, 90), 'rough_f': 0.65, 'metal_f': 0.0}


def gen_solid(rgb_col, rough=0.8, metal=0.0, emissive=None):
    img = Image.new('RGB', (64, 64), rgb_col)
    res = {'base': encode_webp(img), 'rough_f': rough, 'metal_f': metal}
    if emissive:
        res['emissive'] = emissive
    return res


MAT_SPEC = {
    'asphalt': gen_asphalt(),
    'grass_terrain': gen_grass(),
    'runoff_tarmac': gen_runoff(),
    'gravel_trap': gen_gravel(),
    'kerb_rw': gen_kerb(),
    'grid_decal': gen_grid_decal(),
    'armco_steel': gen_armco(),
    'concrete_barrier': gen_concrete(),
    'tire_barrier': gen_tires(),
    'catch_fence': gen_fence(),
    'building_facade': gen_facade(),
    'glass_vip': gen_glass(),
    'grandstand_crowd': gen_crowd(),
    'gantry_banner': gen_gantry(),
    'gantry_lights': gen_solid((235, 30, 38), rough=0.25, metal=0.1, emissive=[1.2, 0.12, 0.12]),
    'tree_foliage': gen_foliage(),
    'tree_trunk': gen_solid((68, 46, 28), rough=0.95),
    'lamp_glow': gen_solid((255, 245, 215), rough=0.2, emissive=[1.1, 1.0, 0.8]),
    'sign_brake': gen_brake_atlas(),
}


# ---------------------------------------------------------------------------
# 5. Paket GLB 2.0
# ---------------------------------------------------------------------------
binbuf = bytearray()
views = []
accessors = []
prims = []
images = []
textures = []
mats = []


def add_view(data: bytes, target: int | None):
    while len(binbuf) % 4:
        binbuf.append(0)
    off = len(binbuf)
    binbuf.extend(data)
    v = {'buffer': 0, 'byteOffset': off, 'byteLength': len(data)}
    if target is not None:
        v['target'] = target
    views.append(v)
    return len(views) - 1


def add_texture(raw_bytes: bytes, label: str) -> int:
    bv = add_view(raw_bytes, None)
    idx = len(images)
    images.append({'name': label, 'bufferView': bv, 'mimeType': 'image/webp'})
    textures.append({'sampler': 0, 'source': idx})
    return idx


for mi, name in enumerate(MAT_NAMES):
    spec = MAT_SPEC[name]
    base_tex = add_texture(spec['base'], f'{name}_base')
    pbr = {
        'baseColorFactor': [1, 1, 1, 1],
        'baseColorTexture': {'index': base_tex},
        'metallicFactor': spec.get('metal_f', 0.0),
        'roughnessFactor': spec.get('rough_f', 0.8),
    }
    if 'mr' in spec:
        pbr['metallicRoughnessTexture'] = {'index': add_texture(spec['mr'], f'{name}_mr')}
    mat_def = {'name': name, 'pbrMetallicRoughness': pbr, 'doubleSided': True}
    if 'norm' in spec:
        mat_def['normalTexture'] = {'index': add_texture(spec['norm'], f'{name}_norm')}
    if 'alphaMode' in spec:
        mat_def['alphaMode'] = spec['alphaMode']
    if 'alphaCutoff' in spec:
        mat_def['alphaCutoff'] = spec['alphaCutoff']
    if 'emissive' in spec:
        mat_def['emissiveFactor'] = spec['emissive']
    mats.append(mat_def)

    b = builders[name]
    if not b.inds:
        continue
    v_arr = np.asarray(b.verts, dtype=np.float32).reshape(-1, 3)
    n_arr = np.asarray(b.norms, dtype=np.float32).reshape(-1, 3)
    uv_arr = np.asarray(b.uvs, dtype=np.float32).reshape(-1, 2)
    i_arr = np.asarray(b.inds, dtype=np.uint32)
    po = add_view(v_arr.tobytes(), 34962)
    no = add_view(n_arr.tobytes(), 34962)
    uo = add_view(uv_arr.tobytes(), 34962)
    io_view = add_view(i_arr.tobytes(), 34963)
    pa = len(accessors)
    accessors.append({
        'bufferView': po, 'componentType': 5126, 'count': len(v_arr), 'type': 'VEC3',
        'min': v_arr.min(axis=0).tolist(), 'max': v_arr.max(axis=0).tolist(),
    })
    na = len(accessors)
    accessors.append({'bufferView': no, 'componentType': 5126, 'count': len(n_arr), 'type': 'VEC3'})
    ua = len(accessors)
    accessors.append({'bufferView': uo, 'componentType': 5126, 'count': len(uv_arr), 'type': 'VEC2'})
    ia = len(accessors)
    accessors.append({'bufferView': io_view, 'componentType': 5125, 'count': len(i_arr), 'type': 'SCALAR'})
    prims.append({'attributes': {'POSITION': pa, 'NORMAL': na, 'TEXCOORD_0': ua}, 'indices': ia, 'material': mi})

gltf = {
    'asset': {'version': '2.0', 'generator': 'Aventador Realistic PBR Circuit Builder'},
    'scene': 0,
    'scenes': [{'nodes': [0]}],
    'nodes': [{'mesh': 0, 'name': 'Aventador Racing Circuit'}],
    'meshes': [{'primitives': prims}],
    'materials': mats,
    'textures': textures,
    'images': images,
    'samplers': [{'magFilter': 9729, 'minFilter': 9987, 'wrapS': 10497, 'wrapT': 10497}],
    'buffers': [{'byteLength': len(binbuf)}],
    'bufferViews': views,
    'accessors': accessors,
}
js = json.dumps(gltf, separators=(',', ':')).encode()
js += b' ' * ((-len(js)) % 4)
binbuf += b'\0' * ((-len(binbuf)) % 4)
total = 12 + 8 + len(js) + 8 + len(binbuf)
glb = b'glTF' + struct.pack('<II', 2, total) + struct.pack('<I4s', len(js), b'JSON') + js + struct.pack('<I4s', len(binbuf), b'BIN\0') + binbuf
(OUT / '11.glb').write_bytes(glb)
print(f'Built Track 11: {N} samples, y=[{y.min():.2f}, {y.max():.2f}]m, trees={len(tree_coords)}, GLB={len(glb)//1024} KB')
