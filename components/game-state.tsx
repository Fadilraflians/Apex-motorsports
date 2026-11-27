'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { cars, paintColors, tracks } from '@/lib/game-data';

export type UpgradeStat = 'speed' | 'acceleration' | 'handling';
export type UpgradeLevels = Record<UpgradeStat, number>;

type Selection = {
  car: string;
  color: string | null;
  track: number;
  sound: boolean;
  upgrades: Record<string, UpgradeLevels>;
};

const STORAGE_KEY = 'apex-selection-v1';
const MAX_UPGRADE_POINTS = 6;
const MAX_UPGRADE_LEVEL = 3;
const UPGRADE_AMOUNT = 4;
const STAT_KEYS: UpgradeStat[] = ['speed', 'acceleration', 'handling'];
const emptyUpgrades = (): UpgradeLevels => ({ speed: 0, acceleration: 0, handling: 0 });
const defaults: Selection = { car: cars[14].slug, color: null, track: tracks[0].id, sound: true, upgrades: {} };

function readUpgrades(value: unknown): Record<string, UpgradeLevels> {
  if (!value || typeof value !== 'object') return {};
  const result: Record<string, UpgradeLevels> = {};
  for (const car of cars) {
    const saved = (value as Record<string, unknown>)[car.slug];
    if (!saved || typeof saved !== 'object') continue;
    const levels = emptyUpgrades();
    let points = 0;
    for (const key of STAT_KEYS) {
      const raw = (saved as Record<string, unknown>)[key];
      const wanted = typeof raw === 'number' && Number.isFinite(raw) ? Math.max(0, Math.min(MAX_UPGRADE_LEVEL, Math.floor(raw))) : 0;
      const useful = Math.min(wanted, Math.floor((100 - car.stats[key]) / UPGRADE_AMOUNT));
      levels[key] = Math.min(useful, MAX_UPGRADE_POINTS - points);
      points += levels[key];
    }
    if (points) result[car.slug] = levels;
  }
  return result;
}

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
          upgrades: readUpgrades(saved.upgrades),
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
  const upgrade = useCallback((stat: UpgradeStat) => setSelection(previous => {
    const baseCar = cars.find(item => item.slug === previous.car)!;
    const levels = previous.upgrades[previous.car] ?? emptyUpgrades();
    const pointsUsed = STAT_KEYS.reduce((sum, key) => sum + levels[key], 0);
    if (pointsUsed >= MAX_UPGRADE_POINTS || levels[stat] >= MAX_UPGRADE_LEVEL || baseCar.stats[stat] + (levels[stat] + 1) * UPGRADE_AMOUNT > 100) return previous;
    return { ...previous, upgrades: { ...previous.upgrades, [previous.car]: { ...levels, [stat]: levels[stat] + 1 } } };
  }), []);
  const resetUpgrades = useCallback(() => setSelection(previous => {
    if (!previous.upgrades[previous.car]) return previous;
    const upgrades = { ...previous.upgrades };
    delete upgrades[previous.car];
    return { ...previous, upgrades };
  }), []);

  const baseCar = cars.find(c => c.slug === selection.car)!;
  const upgradeLevels = selection.upgrades[selection.car] ?? emptyUpgrades();
  const car = {
    ...baseCar,
    stats: Object.fromEntries(STAT_KEYS.map(key => [key, Math.min(100, baseCar.stats[key] + upgradeLevels[key] * UPGRADE_AMOUNT)])) as typeof baseCar.stats,
  };
  const upgradePoints = MAX_UPGRADE_POINTS - STAT_KEYS.reduce((sum, key) => sum + upgradeLevels[key], 0);

  return useMemo(
    () => ({
      ready,
      car,
      color: selection.color,
      track: tracks.find(t => t.id === selection.track)!,
      sound: selection.sound,
      upgradeLevels,
      upgradePoints,
      upgrade,
      resetUpgrades,
      update,
    }),
    [ready, selection, car, upgradeLevels, upgradePoints, upgrade, resetUpgrades, update],
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
