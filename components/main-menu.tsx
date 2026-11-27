'use client';

import Link from 'next/link';
import { cars, tracks } from '@/lib/game-data';
import CarViewer from './car-viewer';
import { useGame } from './game-state';
import { TrackMap, TrackPhoto } from './track-art';

export default function MainMenu() {
  const { ready, car, color, track } = useGame();

  const menu = [
    { href: '/mobil', title: 'Pilih Mobil', detail: ready ? car.name : `${cars.length} mobil` },
    { href: '/sirkuit', title: 'Pilih Sirkuit', detail: ready ? track.name : `${tracks.length} sirkuit` },
    { href: '/balapan', title: 'Mulai Balapan', detail: 'Cek grid dan hitung mundur' },
  ];

  return (
    <main className="page home">
      <div className="home-backdrop"><TrackPhoto track={track} /></div>

      <section className="home-menu">
        <p className="eyebrow">Season 01 <span>/</span> 2025</p>
        <h1>The grid<br /><em>is yours.</em></h1>
        <p className="lead">Pilih mesin. Kuasai lintasan. Tulis namamu di garis finis.</p>
        <nav className="menu-list" aria-label="Menu utama">
          {menu.map((item, i) => (
            <Link key={item.href} href={item.href} className="menu-item">
              <span className="menu-number">0{i + 1}</span>
              <span className="menu-text"><b>{item.title}</b><small>{item.detail}</small></span>
              <span className="menu-arrow" aria-hidden="true">→</span>
            </Link>
          ))}
        </nav>
        <p className="home-count"><b>{cars.length}</b> mobil <span>·</span> <b>{tracks.length}</b> sirkuit</p>
      </section>

      <section className="home-stage" aria-label="Pilihan saat ini">
        {ready && <CarViewer file={car.file} color={color} zoom={false} />}
        <div className="home-car">
          <small>{car.brand} · {car.year}</small>
          <b>{car.name}</b>
        </div>
        <Link href="/sirkuit" className="home-track">
          <TrackMap trackId={track.id} animate />
          <span><small>{track.country}</small><b>{track.name}</b></span>
        </Link>
      </section>
    </main>
  );
}
