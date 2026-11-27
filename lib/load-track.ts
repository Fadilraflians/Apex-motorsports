/** Model sirkuit ringan hasil scripts/build_track_models.py dari folder Track. */
export const trackModelUrl = (trackId: number) => `/tracks/3d/${trackId}.glb`;

/** Unduh model arena secara bertahap, agar indikator tampil dan unduhan bisa dihentikan saat batal. */
export async function loadTrackScene(
  trackId: number,
  onProgress?: (percent: number) => void,
  signal?: AbortSignal,
) {
  const response = await fetch(trackModelUrl(trackId), { signal });
  if (!response.ok) throw new Error(`Model sirkuit tidak ditemukan (${response.status})`);

  const total = Number(response.headers.get('Content-Length')) || 0;
  const reader = response.body?.getReader();
  let bytes = 0;
  let buffer = total ? new Uint8Array(total) : null;
  const chunks: Uint8Array[] = [];
  if (reader) {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (buffer && bytes + value.byteLength > buffer.byteLength) {
        const expanded = new Uint8Array(Math.max(buffer.byteLength * 2, bytes + value.byteLength));
        expanded.set(buffer.subarray(0, bytes));
        buffer = expanded;
      }
      if (buffer) buffer.set(value, bytes);
      else chunks.push(value);
      bytes += value.byteLength;
      if (total) onProgress?.(Math.min(100, Math.round(bytes / total * 100)));
    }
  } else {
    const value = new Uint8Array(await response.arrayBuffer());
    buffer = value;
    bytes = value.byteLength;
    onProgress?.(100);
  }
  if (!buffer) {
    const joined = new Uint8Array(bytes);
    let offset = 0;
    chunks.forEach(chunk => { joined.set(chunk, offset); offset += chunk.byteLength; });
    buffer = joined;
  } else buffer = buffer.subarray(0, bytes);

  const { GLTFLoader } = await import('three/addons/loaders/GLTFLoader.js');
  const exactBuffer = buffer.byteOffset === 0 && buffer.byteLength === buffer.buffer.byteLength
    ? buffer.buffer as ArrayBuffer
    : buffer.slice().buffer as ArrayBuffer;
  return new GLTFLoader().parseAsync(exactBuffer, '');
}
