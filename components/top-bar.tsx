'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useGame } from './game-state';

const pages = [
  { href: '/', label: 'Menu' },
  { href: '/mobil', label: 'Mobil' },
  { href: '/sirkuit', label: 'Sirkuit' },
  { href: '/balapan', label: 'Balapan' },
];

export default function TopBar() {
  const path = usePathname();
  const { sound, update } = useGame();

  return (
    <header className="topbar">
      <Link className="brand" href="/" aria-label="APEX Motorsport, menu utama">
        <span className="brand-mark">A<i>/</i></span>
        <span className="brand-name">APEX<small>MOTORSPORT</small></span>
      </Link>
      <nav className="top-nav" aria-label="Halaman">
        {pages.map((page, i) => (
          <Link key={page.href} href={page.href} aria-current={path === page.href ? 'page' : undefined}>
            <small>0{i}</small>
            {page.label}
          </Link>
        ))}
      </nav>
      <div className="top-tools">
        <button className="sound-toggle" onClick={() => update({ sound: !sound })} aria-pressed={sound}>
          <span aria-hidden="true">{sound ? '♪' : '✕'}</span> Audio {sound ? 'on' : 'off'}
        </button>
        <div className="profile">
          <span className="profile-text">Pembalap<b>GUEST_01</b></span>
          <span className="profile-avatar">G</span>
        </div>
      </div>
    </header>
  );
}
