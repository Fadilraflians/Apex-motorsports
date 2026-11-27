'use client';

import { useEffect, useRef, useState } from 'react';
import { carUrl } from '@/lib/car-loader';
import { createCarStage, type CarStage } from '@/lib/car-stage';

type Load = { state: 'loading' | 'ready' | 'error'; progress: number };

type Props = {
  file: string;
  color: string | null;
  zoom?: boolean;
  onPaintable?: (paintable: boolean) => void;
};

export default function CarViewer({ file, color, zoom = true, onPaintable }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const [stage, setStage] = useState<CarStage | null>(null);
  const [load, setLoad] = useState<Load>({ state: 'loading', progress: 0 });

  useEffect(() => {
    let dead = false;
    let created: CarStage | undefined;
    createCarStage(host.current!, { zoom })
      .then(next => {
        if (dead) return next.dispose();
        created = next;
        setStage(next);
      })
      .catch(() => !dead && setLoad({ state: 'error', progress: 0 }));
    return () => {
      dead = true;
      created?.dispose();
      setStage(null);
    };
  }, [zoom]);

  useEffect(() => {
    stage?.setColor(color);
  }, [stage, color]);

  useEffect(() => {
    if (!stage) return;
    let stale = false;
    setLoad({ state: 'loading', progress: 0 });
    stage
      .setCar(carUrl(file), progress => !stale && setLoad({ state: 'loading', progress }))
      .then(info => {
        if (stale || !info) return;
        setLoad({ state: 'ready', progress: 100 });
        onPaintable?.(info.paintable);
      })
      .catch(() => !stale && setLoad({ state: 'error', progress: 0 }));
    return () => {
      stale = true;
    };
  }, [stage, file, onPaintable]);

  return (
    <div className="car-viewer">
      <div className="car-viewer-canvas" ref={host} />
      {load.state !== 'ready' && (
        <div className="viewer-status" role="status">
          {load.state === 'loading' ? (
            <>
              <span>Memuat model 3D {load.progress > 0 && `${load.progress}%`}</span>
              <div className="viewer-progress"><i style={{ width: `${load.progress}%` }} /></div>
            </>
          ) : (
            <span>Model gagal dimuat</span>
          )}
        </div>
      )}
    </div>
  );
}
