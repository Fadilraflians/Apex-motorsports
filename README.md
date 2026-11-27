# APEX Motorsport

Proyek antarmuka game balap berbasis Next.js, React, TypeScript, dan Three.js. Aset 3D lokal diletakkan di `public/cars`.

## Menjalankan aplikasi

```bash
npm install
npm run dev
```

Buka `http://localhost:3000`. Tampilan dibagi menjadi empat halaman:

| Alamat | Isi |
| --- | --- |
| `/` | Menu utama beserta pilihan mobil dan sirkuit saat ini |
| `/mobil` | Garasi: 29 mobil, pencarian, filter merek dan kelas, warna, model 3D |
| `/sirkuit` | 10 sirkuit dari folder `Track`: foto, peta, dan detail sirkuit |
| `/balapan` | Ringkasan pilihan dan arena balap 3D |

Pilihan mobil, warna, sirkuit, dan audio tersimpan di browser.

### Sirkuit

Lintasan dan seluruh pemandangan balapan berasal dari model GLB di folder `Track` (tidak ada lagi lintasan buatan). Berkas aslinya 44–200 MB, jadi `scripts/build_track_models.py` membuat versi siap pakai di `public/tracks/3d`:

* `{id}.glb`: model yang dipotong per petak 320 m (hanya bagian yang terlihat kamera yang digambar) dengan tekstur WebP dan geometri yang dipadatkan.
* `{id}.json`: garis balap yang diukur dari permukaan aspal model, lebar aspal, jarak ke dinding, dan ketinggian jalan. Fisika mobil memakai data ini sehingga mobil selalu berada di atas aspal yang terlihat.
* `lib/track-layouts.ts`: denah untuk peta di menu dan HUD.

Jalankan ulang setelah mengganti berkas di folder `Track` (butuh Python dengan numpy, scipy, pillow, dan opencv):

```bash
python scripts/build_track_models.py        # semua sirkuit
python scripts/build_track_models.py 5      # satu sirkuit
```

Foto sirkuit di menu ada di `public/tracks/{id}.webp`, dan layar memuat sebelum balapan memakai `public/loading/sirkuit.webp`. Arena balap berjalan dalam layar penuh dengan lawan AI, beberapa sudut kamera, bantuan kemudi, audio mesin, peta, hasil balapan, serta kendali sentuh. WASD/panah untuk gas, rem, dan kemudi; C mengganti kamera, R kembali ke lintasan, M mematikan suara, dan Esc menjeda.

Gambar daftar mobil ada di `public/thumbs` (nama file sama dengan model di `public/cars`). Saat menambah mobil baru, tambahkan juga gambarnya. Nilai kecepatan, akselerasi, dan handling adalah angka permainan, bukan data pabrikan.

HTML lama tetap tersedia di `Lamborghini Aventador Racing.html` sebagai sumber gameplay Three.js yang perlu dipakai saat porting tahap berikutnya. Tampilan sebelumnya dicadangkan di `_backup-tampilan-lama`.
