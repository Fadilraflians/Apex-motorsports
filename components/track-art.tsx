'use client';

import { type Track } from '@/lib/game-data';
import { layouts } from '@/lib/track-layouts';

const cache = new Map<number, { path: string; x: number; y: number }>();

/** Denah lintasan asli, diskalakan ke kotak 100 x 100 (utara di atas). */
function outline(trackId: number) {
  let result = cache.get(trackId);
  if (result) return result;
  const { points } = layouts[trackId];
  const xs = points.filter((_, i) => i % 3 === 0);
  const zs = points.filter((_, i) => i % 3 === 1);
  const [minX, maxX, minZ, maxZ] = [Math.min(...xs), Math.max(...xs), Math.min(...zs), Math.max(...zs)];
  const scale = 92 / Math.max(maxX - minX, maxZ - minZ);
  const map = (i: number) => [50 + (xs[i] - (minX + maxX) / 2) * scale, 50 + (zs[i] - (minZ + maxZ) / 2) * scale];
  let path = '';
  for (let i = 0; i < xs.length; i += 2) {
    const [x, y] = map(i);
    path += `${i ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
  }
  const [x, y] = map(0);
  result = { path: `${path}Z`, x, y };
  cache.set(trackId, result);
  return result;
}

export function TrackMap({ trackId, animate = false }: { trackId: number; animate?: boolean }) {
  const { path, x, y } = outline(trackId);
  return (
    <svg className="track-map" viewBox="0 0 100 100" aria-hidden="true">
      <path className="map-glow" d={path} />
      <path className="map-line" d={path} />
      <circle className="map-start" cx={x} cy={y} r="2.4" />
      {animate && (
        // key memaksa animasi diulang dari awal saat sirkuit berganti
        <circle key={trackId} className="map-runner" r="2">
          <animateMotion dur="9s" repeatCount="indefinite" path={path} />
        </circle>
      )}
    </svg>
  );
}

/** Foto sirkuit, dipotret dari model GLB asli (public/tracks/{id}.webp). */
export function TrackPhoto({ track }: { track: Track }) {
  // eslint-disable-next-line @next/next/no-img-element
  return <img className="track-photo" src={trackPhotoUrl(track.id)} alt="" decoding="async" />;
}

export const trackPhotoUrl = (trackId: number) => `/tracks/${trackId}.webp`;
