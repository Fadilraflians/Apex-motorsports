'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { prefetchCar } from '@/lib/car-loader';
import { brands, cars, categories, paintColors } from '@/lib/game-data';
import CarThumbnail from './car-thumbnail';
import CarViewer from './car-viewer';
import { useGame, type UpgradeStat } from './game-state';

export default function Garage() {
  const { ready, car, color, update, upgradeLevels, upgradePoints, upgrade, resetUpgrades } = useGame();
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('SEMUA');
  const [brand, setBrand] = useState('SEMUA');
  const [paintable, setPaintable] = useState(true);
  const [fullscreen, setFullscreen] = useState(false);
  const list = useRef<HTMLDivElement>(null);
  const showroom = useRef<HTMLElement>(null);

  useEffect(() => {
    const syncFullscreen = () => setFullscreen(document.fullscreenElement === showroom.current);
    document.addEventListener('fullscreenchange', syncFullscreen);
    return () => document.removeEventListener('fullscreenchange', syncFullscreen);
  }, []);

  const toggleFullscreen = async () => {
    const element = showroom.current;
    if (!element) return;
    try {
      if (document.fullscreenElement === element) await document.exitFullscreen();
      else await element.requestFullscreen();
    } catch {
      // Fullscreen tidak tersedia di browser ini.
    }
  };

  const visible = cars.filter(
    item =>
      (category === 'SEMUA' || item.category === category) &&
      (brand === 'SEMUA' || item.brand === brand) &&
      item.name.toLowerCase().includes(search.trim().toLowerCase()),
  );

  const onPaintable = useCallback((value: boolean) => setPaintable(value), []);

  // Unduh mobil sebelum dan sesudah pilihan lebih awal.
  useEffect(() => {
    if (!ready) return;
    const index = cars.findIndex(item => item.slug === car.slug);
    const timer = window.setTimeout(() => {
      [1, cars.length - 1].forEach(offset => prefetchCar(cars[(index + offset) % cars.length].file));
    }, 1200);
    return () => window.clearTimeout(timer);
  }, [car.slug, ready]);
  useEffect(() => setPaintable(true), [car.slug]);

  // Panah kiri/kanan berpindah mobil di dalam hasil filter.
  const step = (direction: 1 | -1) => {
    if (!visible.length) return;
    const index = visible.findIndex(item => item.slug === car.slug);
    const next = index < 0 ? 0 : (index + direction + visible.length) % visible.length;
    update({ car: visible[next].slug });
  };

  useEffect(() => {
    const keydown = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement) return;
      if (event.altKey || event.ctrlKey || event.metaKey) return;
      if (event.key === 'ArrowRight') step(1);
      if (event.key === 'ArrowLeft') step(-1);
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  });

  // Gulirkan daftar (bukan halaman) agar mobil terpilih terlihat.
  useEffect(() => {
    const box = list.current;
    const active = box?.querySelector<HTMLElement>('[aria-pressed="true"]');
    if (!box || !active) return;
    const outer = box.getBoundingClientRect();
    const inner = active.getBoundingClientRect();
    if (inner.top < outer.top || inner.bottom > outer.bottom) box.scrollTop += inner.top - outer.top - (outer.height - inner.height) / 2;
    if (inner.left < outer.left || inner.right > outer.right) box.scrollLeft += inner.left - outer.left - (outer.width - inner.width) / 2;
  }, [car.slug, ready]);

  const overall = Math.round((car.stats.speed + car.stats.acceleration + car.stats.handling) / 3);
  const position = cars.findIndex(item => item.slug === car.slug) + 1;
  const stats = [
    ['Kecepatan', car.stats.speed],
    ['Akselerasi', car.stats.acceleration],
    ['Handling', car.stats.handling],
  ] as const;
  const upgradeRows: { key: UpgradeStat; label: string; part: string }[] = [
    { key: 'speed', label: 'Kecepatan', part: 'Mesin' },
    { key: 'acceleration', label: 'Akselerasi', part: 'Turbo' },
    { key: 'handling', label: 'Handling', part: 'Suspensi' },
  ];

  return (
    <main className="page garage">
      <aside className="panel car-browser" aria-label="Daftar mobil">
        <div className="panel-head">
          <h1>Garasi</h1>
          <span>{visible.length} / {cars.length} mobil</span>
        </div>
        <div className="filters">
          <input type="search" value={search} onChange={e => setSearch(e.target.value)} placeholder="Cari mobil..." aria-label="Cari mobil" />
          <select value={brand} onChange={e => setBrand(e.target.value)} aria-label="Filter merek">
            {brands.map(name => <option key={name} value={name}>{name === 'SEMUA' ? 'Semua merek' : name}</option>)}
          </select>
          <div className="tabs" role="group" aria-label="Filter kelas">
            {categories.map(name => (
              <button key={name} aria-pressed={category === name} onClick={() => setCategory(name)}>{name}</button>
            ))}
          </div>
        </div>
        <div className="car-list" ref={list}>
          {visible.map(item => (
            <button key={item.slug} className="car-card" aria-pressed={item.slug === car.slug} onPointerEnter={() => prefetchCar(item.file)} onFocus={() => prefetchCar(item.file)} onClick={() => update({ car: item.slug })}>
              {item.livePreview ? <CarThumbnail file={item.file} /> : (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={item.thumb} alt="" aria-hidden="true" loading="lazy" width="480" height="270" />
              )}
              <span className="car-card-text">
                <small>{item.brand} · {item.year}</small>
                <b>{item.name}</b>
              </span>
              <span className="car-card-tag">{item.category}</span>
            </button>
          ))}
          {!visible.length && (
            <div className="empty">
              Tidak ada mobil yang cocok.
              <button onClick={() => { setSearch(''); setCategory('SEMUA'); setBrand('SEMUA'); }}>Hapus filter</button>
            </div>
          )}
        </div>
      </aside>

      <section className="showroom" aria-label="Tampilan 3D" ref={showroom} data-model-number={String(position).padStart(2, '0')}>
        <div className="showroom-title">
          <small>{car.brand} <span>///</span> {car.category}</small>
          <h2>{car.name}</h2>
        </div>
        <button className="showroom-fullscreen" onClick={toggleFullscreen} aria-label={fullscreen ? 'Tutup tampilan penuh' : 'Lihat mobil layar penuh'} title={fullscreen ? 'Tutup tampilan penuh (Esc)' : 'Lihat mobil layar penuh'}>
          <span aria-hidden="true">{fullscreen ? '×' : '⛶'}</span>
          {fullscreen ? 'Tutup' : 'Lihat detail'}
        </button>
        {ready && <CarViewer file={car.file} color={color} onPaintable={onPaintable} />}
        <p className="showroom-hint">Seret untuk memutar · gulir untuk zoom</p>
        <div className="showroom-bar">
          <button className="arrow-button" onClick={() => step(-1)} aria-label="Mobil sebelumnya">←</button>
          <div className="paint">
            {paintable ? (
              <fieldset className="paint-mod" aria-label="Modifikasi cat mobil">
                <legend>Modifikasi cat</legend>
                <div className="swatches" role="group" aria-label="Warna mobil">
                  <button className="swatch-original" aria-pressed={color === null} onClick={() => update({ color: null })}>Asli</button>
                  {paintColors.map(paint => (
                    <button
                      key={paint.value}
                      className="swatch"
                      aria-label={paint.name}
                      title={paint.name}
                      aria-pressed={color === paint.value}
                      style={{ '--swatch': paint.value } as React.CSSProperties}
                      onClick={() => update({ color: paint.value })}
                    />
                  ))}
                </div>
              </fieldset>
            ) : (
              <span className="paint-note">Model ini hanya tersedia dalam warna asli</span>
            )}
          </div>
          <button className="arrow-button" onClick={() => step(1)} aria-label="Mobil berikutnya">→</button>
        </div>
      </section>

      <aside className="panel spec-panel" aria-label="Spesifikasi">
        <div className="rating">
          <b>{overall}</b>
          <span>Rating<small>Mobil {position} dari {cars.length}</small></span>
        </div>
        <div className="stats">
          {stats.map(([label, value]) => (
            <div className="stat" key={label}>
              <span>{label}</span><b>{value}</b>
              <div className="stat-bar"><i style={{ width: `${value}%` }} /></div>
            </div>
          ))}
        </div>
        <dl className="facts">
          <div><dt>Merek</dt><dd>{car.brand}</dd></div>
          <div><dt>Tahun</dt><dd>{car.year}</dd></div>
          <div><dt>Kelas</dt><dd>{car.category}</dd></div>
        </dl>
        <section className="upgrade-panel" aria-label="Upgrade dan modifikasi performa">
          <div className="upgrade-head">
            <span>Upgrade performa</span>
            <b>{upgradePoints} POIN</b>
          </div>
          <p className="upgrade-note">Setiap level menambah 4 poin atribut. Upgrade disimpan untuk mobil ini.</p>
          <div className="upgrade-list">
            {upgradeRows.map(row => {
              const level = upgradeLevels[row.key];
              const canUpgrade = upgradePoints > 0 && level < 3 && car.stats[row.key] + 4 <= 100;
              return (
                <div className="upgrade-row" key={row.key}>
                  <div className="upgrade-copy">
                    <span>{row.part}<small>{row.label} · Lv {level}/3</small></span>
                    <div className="upgrade-levels" aria-label={`Level ${level} dari 3`}>
                      {[0, 1, 2].map(index => <i key={index} className={index < level ? 'active' : ''} />)}
                    </div>
                  </div>
                  <button className="upgrade-button" disabled={!canUpgrade} onClick={() => upgrade(row.key)} aria-label={`Upgrade ${row.part}`}>+</button>
                </div>
              );
            })}
          </div>
          <button className="upgrade-reset" disabled={upgradePoints === 6} onClick={resetUpgrades}>Reset upgrade</button>
        </section>
        <div className="actions">
          <Link className="button primary" href="/sirkuit">Lanjut pilih sirkuit <span aria-hidden="true">→</span></Link>
          <Link className="button ghost" href="/">Kembali ke menu</Link>
        </div>
      </aside>
    </main>
  );
}
