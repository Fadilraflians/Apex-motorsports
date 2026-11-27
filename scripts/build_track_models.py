"""Menyiapkan 10 sirkuit dari folder Track untuk game.

Sumber : Track/*.glb (tidak diubah)
Hasil  : public/tracks/3d/{id}.glb   model ringan (dipotong per petak, tekstur WebP)
         public/tracks/3d/{id}.json  garis balap, lebar aspal, dinding, ketinggian permukaan
         lib/track-layouts.ts        denah untuk peta di menu dan HUD
Pakai  : python scripts/build_track_models.py [id ...]       (butuh numpy, scipy, pillow, opencv)
         --tanpa-model  hanya hitung ulang data lintasan

Garis balap diambil dari permukaan aspal model itu sendiri (lihat track_course.py), sehingga
mobil selalu melaju tepat di atas jalan yang terlihat.
"""
import json
import sys
import time
from pathlib import Path

import numpy as np

from track_cache import CACHE, draw_map
from track_course import (RES, Surfaces, centre_on_road, orient, resample, road_profile,
                          smooth_loop, trace_waypoints, wall_distances)
from track_files import FILES
from track_glb import ROOT, Track
from track_model import build_model

TARGET = ROOT / 'public' / 'tracks' / '3d'
SPACING = 2.0
LATERAL = np.arange(-30, 30.01, 2.5)

# Waypoint berurutan searah balap (wp[0] -> wp[1] = garis start lurus menuju tikungan 1).
TRACK_SPECS = {
    1: {
        'closing': 3, 'radius': 24.0,
        'not_road': ('cota_pits_40', 'cota_pits_86', 'cota_pits_73', 'cota_pits_95', 'cota_pits_84', 'cota_pits_82', 'cota_pits_18'),
        'wps': [
            (-476, 762), (-375, 900), (-125, 1065), (-160, 700), (130, 290), (460, 300),
            (945, 25), (190, 155), (-215, 200), (-290, 285), (-115, 415),
            (-260, 610), (-605, 465), (-825, 560), (-670, 575), (-575, 635),
        ],
    },
    2: {
        'closing': 3, 'radius': 24.0,
        'wps': [
            (-178, 187), (-158, -270), (-115, -810), (95, -1125), (955, -1290),
            (1005, -985), (635, -610), (330, -400), (185, -240), (120, -150),
            (85, 340), (45, 720), (-55, 875), (-150, 740), (-192, 340),
        ],
    },
    3: {
        'closing': 3, 'radius': 22.0,
        'wps': [
            (225, 75), (345, -135), (435, -400), (405, -475), (255, -605),
            (115, -545), (95, -455), (205, -420), (315, -420), (270, -330),
            (-20, -250), (-115, -150), (-150, -10), (-115, 110), (-15, 190),
            (-75, 365), (-225, 465), (-425, 485), (-220, 525), (-115, 515),
            (45, 325),
        ],
    },
    4: {
        'closing': 6, 'radius': 26.0,
        'wps': [
            (-14, 150), (-10, -150), (0, -565), (230, -700), (1070, -1120),
            (585, -690), (250, -180), (15, 200), (-15, 340),
        ],
    },
    5: {
        'closing': 3, 'radius': 24.0,
        'wps': [
            (-364, -812), (-505, -1010), (-320, -875), (105, -585), (235, -330),
            (455, 195), (585, 835), (260, 1070), (145, 315), (-105, 745),
            (-380, 955), (-520, 995), (-645, 810), (-100, 100), (-215, -565), (-285, -695),
        ],
    },
    6: {
        'closing': 3, 'radius': 24.0,
        'wps': [
            (-364, -812), (-505, -1010), (-320, -875), (105, -585), (235, -330),
            (455, 195), (585, 835), (260, 1070), (145, 315), (-105, 745),
            (-380, 955), (-520, 995), (-645, 810), (-100, 100), (-215, -565), (-285, -695),
        ],
    },
    7: {
        'closing': 3, 'radius': 24.0,
        'wps': [
            (-240, 355), (-590, 25), (-360, 125), (-155, 205), (-205, 40),
            (-205, -55), (10, -355), (75, -605), (360, -220), (390, 210),
            (165, 425), (25, 325), (-5, 385), (55, 460), (105, 540), (10, 555),
        ],
    },
    8: {
        'closing': 3, 'radius': 18.0,
        'wps': [
            (-10, -450), (-15, -240), (-80, -220), (-195, -195), (-105, -145),
            (40, 125), (195, 115), (175, 490), (160, 565), (130, 350),
            (-35, 45), (-135, -60), (-275, -50), (-285, -380), (-150, -685),
            (-180, -700), (-45, -860),
        ],
    },
    9: {
        'closing': 3, 'radius': 24.0,
        'wps': [
            (-952, 2655), (-1190, 2860), (-1335, 2810), (-1375, 2930), (-1255, 3040),
            (-1305, 3155), (-1230, 3500), (-1450, 3620), (-1725, 3880), (-1415, 3250),
            (-1510, 2845), (-1010, 2495), (-835, 2405), (-700, 2380),
        ],
    },
    10: {
        'closing': 3, 'radius': 24.0,
        'wps': [
            (-368, 212), (-268, 65), (-155, -10), (185, -155), (265, -205), (-220, -595),
            (-270, -550), (-200, -830), (325, -870), (415, -210), (380, -25),
            (0, 810), (-505, 430), (-412, 280),
        ],
    },
}


def build_course(track_id, track):
    spec = TRACK_SPECS[track_id]
    surfaces = Surfaces(track, not_road=spec.get('not_road', ()))
    wps = spec['wps']
    xz, grid, width_mask, road, masks, depth = trace_waypoints(
        surfaces, wps, closing=spec['closing'], radius=spec['radius']
    )
    xz = resample(xz, SPACING)
    xz = smooth_loop(xz, 4)
    xz = orient(xz, wps[0], wps[1])
    xz = centre_on_road(xz, width_mask, grid)
    xz = resample(xz, SPACING)
    xz = orient(xz, wps[0], wps[1])
    CACHE.mkdir(exist_ok=True)
    draw_map(track_id, grid, masks, path=xz, points=wps, out=CACHE / f'final{track_id}.png')
    heights, centre, left, right, normal = road_profile(surfaces, xz, width_mask, grid, LATERAL)
    wall_left, wall_right = wall_distances(track, xz, centre, normal)
    left = np.clip(smooth_loop(left[:, None], 3)[:, 0], 4.5, 22)
    right = np.clip(smooth_loop(right[:, None], 3)[:, 0], 4.5, 22)
    wall_left = np.maximum(wall_left, left + 1.5)
    wall_right = np.maximum(wall_right, right + 1.5)
    relative = np.round((heights - centre[:, None]) * 100).astype(int)
    data = {
        'id': track_id,
        'spacing': SPACING,
        'x': np.round(xz[:, 0], 2).tolist(),
        'z': np.round(xz[:, 1], 2).tolist(),
        'y': np.round(centre, 2).tolist(),
        'roadLeft': np.round(left, 1).tolist(),
        'roadRight': np.round(right, 1).tolist(),
        'wallLeft': np.round(wall_left, 1).tolist(),
        'wallRight': np.round(wall_right, 1).tolist(),
        'lateral': LATERAL.tolist(),
        'heights': relative.reshape(-1).tolist(),
    }
    length = float(np.sum(np.linalg.norm(np.diff(np.vstack([xz, xz[:1]]), axis=0), axis=1)))
    return data, length


def write_layouts():
    """lib/track-layouts.ts dari data lintasan yang sudah dibuat."""
    lines = [
        '// Dibuat oleh scripts/build_track_models.py dari model GLB di folder Track. Jangan diedit manual.',
        '',
        'export type TrackLayout = {',
        '  width: number;',
        '  /** Titik tengah lintasan berurutan sesuai arah balap: x, z, tinggi (meter). */',
        '  points: number[];',
        '};',
        '',
        'export const layouts: Record<number, TrackLayout> = {',
    ]
    for track_id in sorted(FILES):
        path = TARGET / f'{track_id}.json'
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        step = 4
        values = []
        for i in range(0, len(data['x']), step):
            values += [round(data['x'][i], 1), round(data['z'][i], 1), round(data['y'][i], 1)]
        width = round(float(np.median(np.array(data['roadLeft']) + np.array(data['roadRight']))), 1)
        lines.append(f'  {track_id}: {{ width: {width}, points: [{",".join(str(v) for v in values)}] }},')
    lines.append('};')
    (ROOT / 'lib' / 'track-layouts.ts').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    args = sys.argv[1:]
    skip_model = '--tanpa-model' in args
    skip_course = '--hanya-model' in args
    wanted = [int(a) for a in args if a.isdigit()] or sorted(FILES)
    TARGET.mkdir(parents=True, exist_ok=True)
    for track_id in wanted:
        t = time.time()
        source = ROOT / 'Track' / FILES[track_id]
        track = Track(source)
        length = 0.0
        if not skip_course:
            data, length = build_course(track_id, track)
            (TARGET / f'{track_id}.json').write_text(json.dumps(data, separators=(',', ':')), encoding='utf-8')
        info = ''
        if not skip_model:
            stats = build_model(track, TARGET / f'{track_id}.glb')
            size = (TARGET / f'{track_id}.glb').stat().st_size / 1e6
            info = f'model {source.stat().st_size / 1e6:.0f} -> {size:.0f} MB, {stats["meshes"]} potongan, {stats["triangles"]} segitiga'
        print(f'{track_id:2} {FILES[track_id][:38]:38} lintasan {length:6.0f} m  {info}  ({time.time() - t:.0f} dtk)', flush=True)
    if not skip_course:
        write_layouts()


if __name__ == '__main__':
    main()
