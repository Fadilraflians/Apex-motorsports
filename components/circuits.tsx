'use client';

import Link from 'next/link';
import { useEffect } from 'react';
import { difficultyLevel, tracks, weatherIcon } from '@/lib/game-data';
import { useGame } from './game-state';
import { TrackMap, TrackPhoto, trackPhotoUrl } from './track-art';

export default function Circuits() {
  const { track, update } = useGame();
  const index = tracks.findIndex(item => item.id === track.id);
  const level = difficultyLevel[track.difficulty];

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      const direction = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
      if (direction) update({ track: tracks[(index + direction + tracks.length) % tracks.length].id });
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, [index, update]);

  return (
    <main className="page circuits">
      <section className="circuit-stage" aria-label="Pratinjau sirkuit">
        <TrackPhoto track={track} />
        <span className="circuit-tag">{track.tag}</span>
        <div className="circuit-map">
          <span className="circuit-map-label">Rute balap</span>
          <TrackMap trackId={track.id} animate />
        </div>
        <div className="circuit-title">
          <small>{track.country} <span>—</span> {track.region}</small>
          <h1>{track.name}</h1>
        </div>
      </section>

      <aside className="panel circuit-info" aria-label="Detail sirkuit">
        <p className="eyebrow">Sirkuit {String(index + 1).padStart(2, '0')} <span>/</span> {tracks.length}</p>
        <p className="circuit-description">{track.description}</p>
        <dl className="facts">
          <div><dt>Panjang</dt><dd>{track.length}</dd></div>
          <div><dt>Tikungan</dt><dd>{track.turns}</dd></div>
          <div><dt>Putaran</dt><dd>{track.laps} lap</dd></div>
        </dl>
        <div className="info-row">
          <span>Kesulitan</span>
          <b>{track.difficulty}</b>
          <span className="meter" aria-label={`${level} dari 5`}>
            {[1, 2, 3, 4, 5].map(n => <i key={n} className={n <= level ? 'on' : ''} />)}
          </span>
        </div>
        <div className="info-row">
          <span>Cuaca</span>
          <b>{track.weather}</b>
          <span className="weather-icon" aria-hidden="true">{weatherIcon(track.weather)}</span>
        </div>
        <div className="actions">
          <Link className="button primary" href="/balapan">Lanjut ke balapan <span aria-hidden="true">→</span></Link>
          <Link className="button ghost" href="/mobil">Kembali pilih mobil</Link>
        </div>
      </aside>

      <section className="circuit-list" aria-label="Semua sirkuit">
        {tracks.map(item => (
          <button key={item.id} className="circuit-card" aria-pressed={item.id === track.id} onClick={() => update({ track: item.id })}>
            <span className="circuit-card-art" style={{ backgroundImage: `url(${trackPhotoUrl(item.id)})` }}>
              <span>{item.tag}</span>
              <i>{String(item.id).padStart(2, '0')}</i>
            </span>
            <span className="circuit-card-text">
              <small>{item.country}</small>
              <b>{item.name}</b>
              <small>{item.length} · {item.turns} tikungan</small>
            </span>
          </button>
        ))}
      </section>
    </main>
  );
}
