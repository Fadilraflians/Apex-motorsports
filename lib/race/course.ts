/* Geometri lintasan dalam meter, diukur langsung dari model GLB sirkuit
 * (lihat scripts/build_track_models.py): garis tengah aspal, lebar aspal,
 * jarak ke dinding, dan tinggi permukaan di kiri-kanan garis. */

export type CourseData = {
  id: number;
  spacing: number;
  x: number[];
  z: number[];
  y: number[];
  roadLeft: number[];
  roadRight: number[];
  wallLeft: number[];
  wallRight: number[];
  /** Offset melintang (meter, positif = kanan) untuk kolom `heights`. */
  lateral: number[];
  /** Tinggi relatif garis tengah dalam cm, n x lateral.length. */
  heights: number[];
};

export type Course = ReturnType<typeof buildCourse>;

export const wrapAngle = (a: number) => Math.atan2(Math.sin(a), Math.cos(a));
export const clamp = (v: number, low: number, high: number) => Math.max(low, Math.min(high, v));

export const courseUrl = (trackId: number) => `/tracks/3d/${trackId}.json`;

export async function loadCourse(trackId: number, signal?: AbortSignal): Promise<CourseData> {
  const response = await fetch(courseUrl(trackId), { signal });
  if (!response.ok) throw new Error(`Data lintasan tidak ditemukan (${response.status})`);
  return response.json();
}

export function buildCourse(data: CourseData) {
  const n = data.x.length;
  const x = Float64Array.from(data.x);
  const z = Float64Array.from(data.z);
  const y = Float64Array.from(data.y);
  const roadLeft = Float64Array.from(data.roadLeft);
  const roadRight = Float64Array.from(data.roadRight);
  const wallLeft = Float64Array.from(data.wallLeft);
  const wallRight = Float64Array.from(data.wallRight);
  const lateral = data.lateral;
  const columns = lateral.length;
  const heights = Float32Array.from(data.heights, v => v / 100);
  const lateralStep = lateral[1] - lateral[0];

  const wrap = (i: number) => ((i % n) + n) % n;
  const s = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) s[i + 1] = s[i] + Math.hypot(x[wrap(i + 1)] - x[i], z[wrap(i + 1)] - z[i]);
  const length = s[n];
  const step = length / n;

  const tx = new Float64Array(n);
  const tz = new Float64Array(n);
  const heading = new Float64Array(n);
  const slope = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const dx = x[wrap(i + 2)] - x[wrap(i - 2)];
    const dz = z[wrap(i + 2)] - z[wrap(i - 2)];
    const d = Math.hypot(dx, dz) || 1;
    tx[i] = dx / d;
    tz[i] = dz / d;
    heading[i] = Math.atan2(dx, dz);
    slope[i] = (y[wrap(i + 2)] - y[wrap(i - 2)]) / d;
  }

  // Kelengkungan (1/radius). Negatif = belok kanan, positif = belok kiri.
  const raw = new Float64Array(n);
  for (let i = 0; i < n; i++) raw[i] = wrapAngle(heading[wrap(i + 4)] - heading[wrap(i - 4)]) / (8 * step);
  const curve = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    let sum = 0;
    for (let k = -4; k <= 4; k++) sum += raw[wrap(i + k)];
    curve[i] = sum / 9;
  }

  // Kisi pencarian cepat: titik lintasan mana yang dekat posisi tertentu.
  const CELL = 24;
  const cells = new Map<number, number[]>();
  const key = (cx: number, cz: number) => cx * 100003 + cz;
  for (let i = 0; i < n; i++) {
    const k = key(Math.floor(x[i] / CELL), Math.floor(z[i] / CELL));
    if (!cells.has(k)) cells.set(k, []);
    cells.get(k)!.push(i);
  }
  const near = (px: number, pz: number, radius: number, visit: (i: number, distance: number) => void) => {
    for (let cx = Math.floor((px - radius) / CELL); cx <= Math.floor((px + radius) / CELL); cx++) {
      for (let cz = Math.floor((pz - radius) / CELL); cz <= Math.floor((pz + radius) / CELL); cz++) {
        cells.get(key(cx, cz))?.forEach(i => {
          const d = Math.hypot(x[i] - px, z[i] - pz);
          if (d <= radius) visit(i, d);
        });
      }
    }
  };

  const indexAt = (distance: number) => {
    const d = ((distance % length) + length) % length;
    let i = Math.min(n - 1, Math.floor(d / step));
    while (i > 0 && s[i] > d) i--;
    while (i < n - 1 && s[i + 1] <= d) i++;
    return { i, u: (d - s[i]) / Math.max(1e-6, s[i + 1] - s[i]) };
  };

  /** Tinggi permukaan relatif garis tengah pada titik i, offset melintang `lane`. */
  const rowHeight = (i: number, lane: number) => {
    const f = clamp((lane - lateral[0]) / lateralStep, 0, columns - 1);
    const c = Math.min(columns - 2, Math.floor(f));
    const u = f - c;
    const base = i * columns;
    return heights[base + c] * (1 - u) + heights[base + c + 1] * u;
  };

  /** Posisi pada jarak tempuh tertentu; lane positif = ke kanan dari garis tengah. */
  const at = (distance: number, lane = 0) => {
    const { i, u } = indexAt(distance);
    const j = wrap(i + 1);
    const mix = (a: Float64Array) => a[i] + (a[j] - a[i]) * u;
    const dx = mix(tx);
    const dz = mix(tz);
    const d = Math.hypot(dx, dz) || 1;
    const centre = mix(y);
    const surface = rowHeight(i, lane) * (1 - u) + rowHeight(j, lane) * u;
    // kemiringan melintang untuk guling mobil
    const bank = (rowHeight(i, lane + 1) - rowHeight(i, lane - 1)) / 2;
    return {
      x: mix(x) - (dz / d) * lane,
      y: centre + surface,
      z: mix(z) + (dx / d) * lane,
      heading: heading[i] + wrapAngle(heading[j] - heading[i]) * u,
      slope: mix(slope),
      curve: mix(curve),
      bank,
      i,
    };
  };

  /** Titik lintasan terdekat, dicari di sekitar indeks sebelumnya. */
  const locate = (px: number, pz: number, hint: number) => {
    let best = Infinity;
    let index = hint;
    for (let k = -40; k <= 40; k++) {
      const i = wrap(hint + k);
      const d = (x[i] - px) ** 2 + (z[i] - pz) ** 2;
      if (d < best) {
        best = d;
        index = i;
      }
    }
    const dx = px - x[index];
    const dz = pz - z[index];
    const along = clamp(dx * tx[index] + dz * tz[index], -step, step);
    return {
      i: index,
      s: (s[index] + along + length) % length,
      lateral: -dx * tz[index] + dz * tx[index],
    };
  };

  return {
    trackId: data.id, n, length, step, x, y, z, s, tx, tz, heading, slope, curve,
    roadLeft, roadRight, wallLeft, wallRight, wrap, near, at, locate, indexAt,
  };
}

/** Kecepatan aman di setiap titik, sudah memperhitungkan jarak pengereman. */
export function speedProfile(course: Course, top: number, grip: number, brake: number) {
  const { n, curve, step } = course;
  const profile = new Float64Array(n);
  for (let i = 0; i < n; i++) profile[i] = Math.min(top, Math.sqrt(grip / Math.max(Math.abs(curve[i]), 1e-5)));
  for (let k = 2 * n; k >= 0; k--) {
    const i = k % n;
    profile[i] = Math.min(profile[i], Math.sqrt(profile[(i + 1) % n] ** 2 + 2 * brake * step));
  }
  return profile;
}
