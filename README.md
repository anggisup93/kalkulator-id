# KalkulatorID

Situs statis kumpulan kalkulator berbahasa Indonesia, dirancang untuk SEO dan
monetisasi Google AdSense. Tanpa framework, tanpa dependency — hanya Python 3
untuk membangun HTML final.

## Struktur

```
site.json           Konfigurasi situs + daftar halaman (judul, deskripsi, menu)
layout.html         Kerangka HTML (header, footer, slot iklan) — placeholder {{...}}
build.py            Generator: gabungkan layout + pages/ -> dist/
assets/
  style.css         Tampilan (mobile-first)
  calc.js           Helper JS bersama (format rupiah, ambil input, tampilkan hasil)
pages/
  kpr.html          Isi 1 halaman kalkulator (form + artikel + <script>)
  bunga-majemuk.html
  bmi.html
  tentang.html      Halaman wajib untuk AdSense
  kontak.html       Halaman wajib untuk AdSense
  privasi.html      Halaman wajib untuk AdSense (kebijakan privasi + AdSense)
dist/               Hasil build (jangan di-commit, sudah di .gitignore)
```

## Build & pratinjau lokal

```bash
python build.py
python -m http.server -d dist 8000
# buka http://localhost:8000
```

## Menambahkan kalkulator baru

1. Buat `pages/<slug>.html` berisi **isi halaman saja** (tanpa `<html>`/`<head>`):
   `<h1>`, `<form class="calc">`, `<div id="...-hasil" class="result" hidden>`,
   `<section class="article">` (tulis 200–400 kata: rumus, contoh, FAQ),
   lalu `<script>` dengan fungsi perhitungannya.
   Pakai helper dari `calc.js`: `num("id")`, `rp(angka)`, `show("id", html)`.
2. Tambahkan entri di `site.json` -> `pages` (`slug`, `nav`, `in_index`,
   `title` yang mengandung kata kunci, `description` 1 kalimat).
3. `python build.py` ulang.

Target realistis: 20–50 kalkulator sebelum berharap traffic berarti.

## Mengaktifkan Google AdSense

1. Beli domain sendiri, deploy situs (lihat di bawah), biarkan 2–4 minggu.
2. Daftar di https://adsense.google.com dengan domain tersebut.
3. Setelah dapat kode publisher (`ca-pub-xxxxxxxxxxxxxxxx`), isi di
   `site.json` -> `"adsense_client"`, lalu build ulang. Skrip AdSense dan satu
   unit iklan responsif otomatis muncul di semua halaman.
4. Kalau AdSense memberi cuplikan verifikasi khusus, tempel di `layout.html`
   bagian `<head>`.

## Deploy ke Cloudflare Pages (gratis)

1. `git init && git add -A && git commit -m "init"` lalu push ke GitHub.
2. Cloudflare Dashboard -> Workers & Pages -> Create -> Pages -> connect repo.
3. Build command: `python build.py`  •  Output directory: `dist`
4. Tambahkan custom domain di tab **Custom domains**.

Netlify serupa: build command `python build.py`, publish directory `dist`.

## Setelah online

- Daftarkan situs di Google Search Console, submit `sitemap.xml`.
- Pantau query yang mulai muncul, perkuat halaman yang mendekati halaman 1.
- Tambah kalkulator baru secara rutin; siapkan yang musiman (THR, pajak)
  jauh sebelum musimnya.
- Ganti alamat email di `pages/kontak.html` dan tanggal di `pages/privasi.html`.
