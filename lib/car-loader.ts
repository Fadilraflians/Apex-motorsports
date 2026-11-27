/* Memuat model mobil sekali saja, lalu memakainya ulang di semua halaman. */

const PAINT = /paint|body|carroceria|exterior|_ext\d*$|^coloured$/i;
const NOT_PAINT = /caliper|window|glass|light|badge|misc|chassis|black|carbon|rough|trim|nero|interior|wheel|rim/i;
const LIMIT = 8;

type Entry = { scene: Promise<any>; listeners: Set<(percent: number) => void>; percent: number };

const cache = new Map<string, Entry>();
const prefetching = new Set<string>();

export const carUrl = (file: string) => `/cars/${encodeURIComponent(file)}`;

function disposeModel(root: any) {
  root.traverse((object: any) => {
    if (!object.isMesh) return;
    object.geometry.dispose();
    [object.material].flat().forEach((material: any) => {
      Object.values(material).forEach((value: any) => value?.isTexture && value.dispose());
      material.dispose();
    });
  });
}

function load(url: string): Entry {
  const existing = cache.get(url);
  if (existing) {
    // Pindahkan ke urutan terbaru.
    cache.delete(url);
    cache.set(url, existing);
    return existing;
  }
  const entry: Entry = { listeners: new Set(), percent: 0, scene: Promise.resolve() };
  entry.scene = import('three/addons/loaders/GLTFLoader.js').then(
    ({ GLTFLoader }) =>
      new Promise((resolve, reject) => {
        new GLTFLoader().load(
          url,
          (gltf: any) => resolve(gltf.scene),
          (event: ProgressEvent) => {
            if (!event.total) return;
            entry.percent = Math.min(99, Math.round((event.loaded / event.total) * 100));
            entry.listeners.forEach(listener => listener(entry.percent));
          },
          reject,
        );
      }),
  );
  entry.scene.catch(() => cache.delete(url));
  cache.set(url, entry);
  if (cache.size > LIMIT) {
    const [oldUrl, old] = cache.entries().next().value!;
    cache.delete(oldUrl);
    old.scene.then(disposeModel).catch(() => {});
  }
  return entry;
}

/**
 * Salinan mobil siap pakai. Geometri dan tekstur dipakai bersama;
 * material cat disalin supaya tiap salinan bisa berwarna sendiri.
 */
export async function createCar(url: string, onProgress?: (percent: number) => void) {
  const entry = load(url);
  if (onProgress) {
    entry.listeners.add(onProgress);
    onProgress(entry.percent);
  }
  try {
    const object = (await entry.scene).clone(true);
    const copies = new Map<any, any>();
    const paints: { material: any; original: any }[] = [];
    object.traverse((mesh: any) => {
      if (!mesh.isMesh) return;
      const swap = (material: any) => {
        if (!material.color || !PAINT.test(material.name) || NOT_PAINT.test(material.name)) return material;
        if (!copies.has(material)) {
          const copy = material.clone();
          copies.set(material, copy);
          paints.push({ material: copy, original: material.color.clone() });
        }
        return copies.get(material);
      };
      mesh.material = Array.isArray(mesh.material) ? mesh.material.map(swap) : swap(mesh.material);
    });
    return {
      object,
      paintable: paints.length > 0,
      dispose() {
        copies.forEach(material => material.dispose());
      },
      /** null = warna asli model. */
      setColor(color: string | null) {
        paints.forEach(({ material, original }) => (color ? material.color.set(color) : material.color.copy(original)));
      },
    };
  } finally {
    if (onProgress) entry.listeners.delete(onProgress);
  }
}

/** Unduh lebih awal ke cache browser (tanpa mengolah), agar pindah mobil terasa instan. */
export function prefetchCar(file: string) {
  const url = carUrl(file);
  if (cache.has(url) || prefetching.has(url)) return;
  prefetching.add(url);
  fetch(url, { priority: 'low' } as RequestInit)
    .catch(() => {})
    .finally(() => prefetching.delete(url));
}
