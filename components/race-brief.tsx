'use client';

import Link from 'next/link';
import { useState } from 'react';
import { weatherIcon } from '@/lib/game-data';
import CarViewer from './car-viewer';
import { useGame } from './game-state';
import RaceArena from './race-arena';
import { TrackMap, TrackPhoto } from './track-art';

export default function RaceBrief() {
  const { ready, car, color, track } = useGame();
  const [race, setRace] = useState(false);
  const distance = (parseFloat(track.length) * track.laps).toFixed(2);
  const startRace = () => {
    // Dipanggil langsung dari klik agar browser mengizinkan Fullscreen API.
    if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
      document.documentElement.requestFullscreen({ navigationUI: 'hide' }).catch(() => {});
    }
    setRace(true);
  };

  return (
    <main className="page race">
      <header className="race-head">
        <p className="eyebrow">Race brief</p>
        <h1>Grid sudah <em>siap.</em></h1>
      </header>

      <div className="race-cards">
        <article className="race-card">
          <div className="race-card-art car">{ready && !race && <CarViewer file={car.file} color={color} zoom={false} />}</div>
          <div className="race-card-text">
            <span><small>Mobil kamu</small><b>{car.name}</b></span>
            <Link className="button ghost" href="/mobil">Ganti mobil</Link>
          </div>
        </article>
        <article className="race-card">
          <div className="race-card-art">
            <TrackPhoto track={track} />
            <div className="race-card-map"><TrackMap trackId={track.id} animate /></div>
          </div>
          <div className="race-card-text">
            <span><small>{track.country} · {weatherIcon(track.weather)} {track.weather}</small><b>{track.name}</b></span>
            <Link className="button ghost" href="/sirkuit">Ganti sirkuit</Link>
          </div>
        </article>
      </div>

      <div className="race-bar">
        <dl className="facts">
          <div><dt>Grid start</dt><dd>4 pembalap</dd></div>
          <div><dt>Format</dt><dd>{track.laps} lap</dd></div>
          <div><dt>Jarak total</dt><dd>{distance} km</dd></div>
          <div><dt>Kesulitan</dt><dd>{track.difficulty}</dd></div>
        </dl>
        <button className="button primary launch" onClick={startRace} disabled={!ready}>Mulai balapan <span aria-hidden="true">→</span></button>
      </div>

      {race && <RaceArena onExit={() => setRace(false)} />}
    </main>
  );
}
