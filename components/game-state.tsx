'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { cars, paintColors, tracks } from '@/lib/game-data';

type Selection = { car: string; color: string | null; track: number; sound: boolean };

const STORAGE_KEY = 'apex-selection-v1';
const defaults: Selection = { car: cars[14].slug, color: null, track: tracks[0].id, sound: true };

type GameState = ReturnType<typeof useSelection>;

function useSelection() {
  const [selection, setSelection] = useState<Selection>(defaults);
  // false sampai pilihan tersimpan terbaca, supaya model default tidak ikut dimuat percuma.
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? 'null');
      if (saved) {
        setSelection({
          car: cars.some(c => c.slug === saved.car) ? saved.car : defaults.car,
          color: paintColors.some(c => c.value === saved.color) ? saved.color : null,
          track: tracks.some(t => t.id === saved.track) ? saved.track : defaults.track,
          sound: saved.sound !== false,
        });
      }
    } catch {
      // Penyimpanan diblokir atau datanya rusak: pakai pilihan default.
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(selection));
    } catch {
      // Pilihan tetap berlaku selama halaman terbuka.
    }
  }, [ready, selection]);

  const update = useCallback((patch: Partial<Selection>) => setSelection(previous => ({ ...previous, ...patch })), []);

  return useMemo(
    () => ({
      ready,
      car: cars.find(c => c.slug === selection.car)!,
      color: selection.color,
      track: tracks.find(t => t.id === selection.track)!,
      sound: selection.sound,
      update,
    }),
    [ready, selection, update],
  );
}

const Context = createContext<GameState | null>(null);

export function GameProvider({ children }: { children: React.ReactNode }) {
  return <Context.Provider value={useSelection()}>{children}</Context.Provider>;
}

export function useGame() {
  const state = useContext(Context);
  if (!state) throw new Error('useGame harus dipakai di dalam GameProvider');
  return state;
}
