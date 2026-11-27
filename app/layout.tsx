import type { Metadata } from 'next';
import { GameProvider } from '@/components/game-state';
import TopBar from '@/components/top-bar';
import './globals.css';

export const metadata: Metadata = {
  title: { default: 'APEX — Motorsport', template: '%s · APEX Motorsport' },
  description: 'Pilih mobil impianmu dan bersiaplah untuk balapan.',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body>
        <GameProvider>
          <TopBar />
          {children}
        </GameProvider>
      </body>
    </html>
  );
}
