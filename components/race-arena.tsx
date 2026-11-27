'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cars } from '@/lib/game-data';
import type { Control, Hud, Race } from '@/lib/race/game';
import { useGame } from './game-state';

const RIVAL_CARS = [
  '2014_ferrari_laferrari', '2019_mclaren_600lt', '2014_mclaren_p1_gtr_concept', '2012_koenigsegg_agera_r',
  '2020_ferrari_sf90_stradale', '2015_mclaren_650s_gt3', '2016_mclaren_mp4-x', '2019_ferrari_488_pista', '2025_bugatti_bolide',
];
const DRIVERS = ['M. Rivera', 'K. Tanaka', 'L. Novak'];

const clock = (seconds: number) =>
  `${Math.floor(seconds / 60)}:${(seconds % 60).toFixed(3).padStart(6, '0')}`;

export default function RaceArena({ onExit }: { onExit: () => void }) {
  const { car, color, track, sound, update } = useGame();
  const frame = useRef<HTMLDivElement>(null);
  const host = useRef<HTMLDivElement>(null);
  const map = useRef<HTMLCanvasElement>(null);
  const race = useRef<Race | null>(null);
  const [hud, setHud] = useState<Hud | null>(null);
  const [loading, setLoading] = useState({ message: 'Menyiapkan sirkuit', percent: 0 });
  const [failed, setFailed] = useState('');
  const [portalTarget, setPortalTarget] = useState<HTMLElement | null>(null);
  // Pengaturan saat balapan dimulai; perubahan suara di tengah balapan tidak memuat ulang arena.
  const [setup] = useState(() => ({ car, color, track, muted: !sound }));

  useEffect(() => setPortalTarget(document.body), []);

  useEffect(() => {
    if (!portalTarget) return;
    let dead = false;
    const controller = new AbortController();
    const rivals = RIVAL_CARS.filter(slug => slug !== setup.car.slug)
      .sort(() => Math.random() - 0.5)
      .slice(0, DRIVERS.length)
      .map((slug, i) => {
        const rival = cars.find(item => item.slug === slug)!;
        return { file: rival.file, car: rival.name, driver: DRIVERS[i], color: null };
      });
    document.body.style.overflow = 'hidden';
    frame.current?.focus();
    let wasFullscreen = Boolean(document.fullscreenElement);
    const onFullscreenChange = () => {
      if (document.fullscreenElement) wasFullscreen = true;
      else if (wasFullscreen) race.current?.setPaused(true);
    };
    document.addEventListener('fullscreenchange', onFullscreenChange);

    import('@/lib/race/game')
      .then(({ createRace }) =>
        createRace(
          host.current!,
          map.current!,
          {
            trackId: setup.track.id,
            title: setup.track.name,
            laps: setup.track.laps,
            weather: setup.track.weather,
            muted: setup.muted,
            signal: controller.signal,
            player: { file: setup.car.file, car: setup.car.name, driver: 'Kamu', color: setup.color, stats: setup.car.stats },
            rivals,
            onProgress: (message, percent) => !dead && setLoading({ message, percent }),
            onHud: next => !dead && setHud(next),
          },
          () => dead,
        ),
      )
      .then(created => {
        if (!created) return;
        if (dead) created.dispose();
        else race.current = created;
      })
      .catch(error => {
        // Dibatalkan (keluar arena / efek dijalankan ulang): bukan kesalahan.
        if (dead || error?.name === 'AbortError') return;
        console.error(error);
        setFailed('Arena gagal dimuat. Pastikan browser mendukung WebGL, lalu coba lagi.');
      });

    return () => {
      dead = true;
      controller.abort();
      race.current?.dispose();
      race.current = null;
      document.body.style.overflow = '';
      document.removeEventListener('fullscreenchange', onFullscreenChange);
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    };
  }, [setup, portalTarget]);

  /** Tombol layar melepas fokus agar spasi/enter tidak menekannya lagi. */
  const press = (action: () => void) => (event: React.MouseEvent<HTMLButtonElement>) => {
    event.currentTarget.blur();
    action();
  };
  const hold = (control: Control) => ({
    onPointerDown: (event: React.PointerEvent<HTMLButtonElement>) => {
      event.currentTarget.setPointerCapture(event.pointerId);
      race.current?.setControl(control, true);
    },
    onPointerUp: () => race.current?.setControl(control, false),
    onPointerCancel: () => race.current?.setControl(control, false),
    onContextMenu: (event: React.MouseEvent) => event.preventDefault(),
  });
  const fullscreen = () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else frame.current?.requestFullscreen().catch(() => {});
  };

  const playing = hud && !failed;

  if (!portalTarget) return null;

  return createPortal((
    <div className="arena" ref={frame} tabIndex={-1} role="application" aria-label={`Balapan di ${setup.track.name}`}>
      <div className="arena-view" ref={host} />

      <div className={`hud ${playing ? '' : 'hud-hidden'}`}>
        <div className="hud-box hud-place">
          <div><b>{hud?.position ?? '-'}<small>/{hud?.total ?? '-'}</small></b><span>Posisi</span></div>
          <div><b>{hud?.lap ?? '-'}<small>/{setup.track.laps}</small></b><span>Lap</span></div>
        </div>

        <div className="hud-right">
          <dl className="hud-box hud-times">
            <div className="current"><dt>Lap ini</dt><dd>{clock(hud?.lapTime ?? 0)}</dd></div>
            <div><dt>Terbaik</dt><dd>{hud?.bestLap ? clock(hud.bestLap) : '–'}</dd></div>
            <div><dt>Total</dt><dd>{clock(hud?.raceTime ?? 0)}</dd></div>
          </dl>
          <canvas className="hud-map" ref={map} aria-label="Peta sirkuit" />
        </div>

        <div className="hud-center" aria-live="polite">
          {hud?.phase === 'countdown' && (
            <>
              <div className="start-lights" aria-label={`${hud.lights} lampu menyala`}>
                {[1, 2, 3, 4, 5].map(n => <i key={n} className={n <= hud.lights ? 'on' : ''} />)}
              </div>
              <p className="hud-hint">Mulai saat semua lampu padam</p>
              <p className="hud-keys"><kbd>W</kbd><kbd>↑</kbd> gas <kbd>S</kbd><kbd>↓</kbd> rem <kbd>A</kbd><kbd>D</kbd> belok <kbd>C</kbd> kamera <kbd>R</kbd> kembali <kbd>Esc</kbd> jeda</p>
            </>
          )}
          {hud?.go && <strong className="hud-go">GO!</strong>}
          {hud?.wrongWay && <strong className="hud-warning">Arah terbalik</strong>}
          {hud?.brakeNow && !hud.wrongWay && <strong className="hud-brake">Rem!</strong>}
        </div>

        <div className="hud-speed">
          <div className="hud-gear">{hud?.gear ?? 'N'}</div>
          <div className="hud-kmh"><b>{hud?.speed ?? 0}</b><span>km/jam</span></div>
          <div className="hud-rpm">
            {Array.from({ length: 15 }, (_, i) => (
              <i key={i} className={(hud?.rpm ?? 0) * 15 > i ? (i > 11 ? 'on high' : i > 7 ? 'on mid' : 'on') : ''} />
            ))}
          </div>
        </div>

        <div className="hud-tools">
          <button onClick={press(() => race.current?.setPaused(true))}>❚❚ Jeda</button>
          <button onClick={press(() => race.current?.cycleCamera())}>Kamera: {hud?.camera}</button>
          <button aria-pressed={hud?.assist} onClick={press(() => race.current?.toggleAssist())}>Bantuan kemudi {hud?.assist ? 'on' : 'off'}</button>
          <button onClick={press(() => { const muted = race.current?.toggleMuted(); if (muted !== undefined) update({ sound: !muted }); })}>Suara {hud?.muted ? 'off' : 'on'}</button>
          <button onClick={press(fullscreen)}>Layar penuh</button>
        </div>

        <div className="hud-touch">
          <div><button aria-label="Belok kiri" {...hold('left')}>◀</button><button aria-label="Belok kanan" {...hold('right')}>▶</button></div>
          <div><button className="brake" {...hold('brake')}>Rem</button><button className="gas" {...hold('gas')}>Gas</button></div>
        </div>
      </div>

      {(!playing || failed) && (
        <div className="arena-loading">
          <div>
            <p className="eyebrow">{setup.track.country} <span>/</span> {setup.track.length} <span>/</span> {setup.track.laps} lap</p>
            <h2>{setup.track.name}</h2>
            {failed ? (
              <p role="alert">{failed}</p>
            ) : (
              <>
                <div className="arena-progress"><i style={{ width: `${loading.percent}%` }} /></div>
                <p role="status">{loading.message}…</p>
              </>
            )}
            <button className="button ghost" onClick={onExit}>Batal</button>
          </div>
        </div>
      )}

      {hud?.paused && (
        <div className="arena-panel" role="dialog" aria-label="Jeda">
          <div>
            <p className="eyebrow">{setup.track.name}</p>
            <h2>Jeda</h2>
            <button className="button primary" autoFocus onClick={press(() => race.current?.setPaused(false))}>Lanjutkan</button>
            <button className="button ghost" onClick={press(() => race.current?.restart())}>Ulangi balapan</button>
            <button className="button ghost" onClick={onExit}>Keluar dari arena</button>
          </div>
        </div>
      )}

      {hud?.results && (
        <div className="arena-panel results" role="dialog" aria-label="Hasil balapan">
          <div>
            <p className="eyebrow">Finis <span>/</span> {setup.track.name}</p>
            <h2>{hud.position === 1 ? 'Juara 1!' : `Posisi ${hud.position}`}</h2>
            <ol>
              {hud.results.map((result, i) => (
                <li key={result.driver} className={result.you ? 'you' : ''}>
                  <b>{i + 1}</b>
                  <span>{result.driver}<small>{result.car}</small></span>
                  <time>{clock(result.time)}</time>
                </li>
              ))}
            </ol>
            {hud.bestLap && <p>Lap terbaikmu {clock(hud.bestLap)}</p>}
            <button className="button primary" onClick={press(() => race.current?.restart())}>Balapan lagi</button>
            <button className="button ghost" onClick={onExit}>Kembali ke grid</button>
          </div>
        </div>
      )}
    </div>
  ), portalTarget);
}
