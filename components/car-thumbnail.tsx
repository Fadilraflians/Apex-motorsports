'use client';

import { useEffect, useRef, useState } from 'react';
import { carUrl } from '@/lib/car-loader';
import { createCarStage } from '@/lib/car-stage';

let renderQueue = Promise.resolve();

export default function CarThumbnail({ file }: { file: string }) {
  const host = useRef<HTMLDivElement>(null);
  const [image, setImage] = useState<string | null>(null);

  useEffect(() => {
    const element = host.current;
    if (!element) return;
    let cancelled = false;
    let dispose: (() => void) | undefined;
    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      observer.disconnect();
      renderQueue = renderQueue.then(async () => {
        if (cancelled) return;
        let stage: Awaited<ReturnType<typeof createCarStage>> | undefined;
        let disposed = false;
        const disposeStage = () => {
          if (!stage || disposed) return;
          disposed = true;
          stage.dispose();
        };
        try {
          stage = await createCarStage(element, { zoom: false, thumbnail: true });
          dispose = disposeStage;
          if (cancelled) return;
          await stage.setCar(carUrl(file));
          if (!cancelled) setImage(stage.snapshot());
        } catch {
          // Tetap tampilkan latar kartu jika WebGL atau model tidak tersedia.
        } finally {
          disposeStage();
          dispose = undefined;
        }
      });
    }, { rootMargin: '100px' });
    observer.observe(element);

    return () => {
      cancelled = true;
      observer.disconnect();
      dispose?.();
    };
  }, [file]);

  return (
    <span className="car-card-preview" aria-hidden="true" ref={host}>
      {image && <img src={image} alt="" width="184" height="116" />}
    </span>
  );
}
