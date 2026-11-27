import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  poweredByHeader: false,
  // Model dan gambar jarang berubah: biarkan browser menyimpannya sehari.
  async headers() {
    return ['/cars/:path*', '/thumbs/:path*', '/tracks/:path*'].map(source => ({
      source,
      headers: [{ key: 'Cache-Control', value: 'public, max-age=86400, stale-while-revalidate=604800' }],
    }));
  },
};

export default nextConfig;
