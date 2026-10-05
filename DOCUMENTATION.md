# Mengelola situs dokumentasi

Sumber situs berada di `docs/`, navigasi di `mkdocs.yml`, dan dependensi di
`requirements-docs.txt`. Dependensi dokumentasi terpisah dari aplikasi.

Dari direktori utama repositori, gunakan lingkungan Python khusus:

```bash
python3 -m venv .venv-docs
.venv-docs/bin/python -m pip install -r requirements-docs.txt
.venv-docs/bin/python -m mkdocs serve
```

Pratinjau tersedia di `http://127.0.0.1:8000`. Periksa sebelum membuat commit:

```bash
.venv-docs/bin/python -m mkdocs build --strict
```

Hasil build berada di `site/` dan tidak disimpan di Git. Gunakan versi Python
yang sama dengan workflow dokumentasi untuk pemeriksaan yang konsisten.

Isi kerangka pada komentar `<!-- TODO: ... -->` dengan tulisan dan gambar nyata.
Simpan gambar di `docs/assets/images/` saat diperlukan; gunakan tautan relatif
dan teks alternatif berbahasa Indonesia. Daftarkan setiap halaman baru di
`nav` pada `mkdocs.yml`. Komentar TODO tidak ditampilkan di situs.

Warna berasal dari `web/app/static/tokens.css`. Font Inter dan lisensinya disalin
dari `web/app/static/fonts/`; perbarui salinan jika aset aplikasi berubah.
Aplikasi menggunakan nama Absensa sebagai identitas teks, tanpa berkas logo
merek khusus; ikon buku bawaan Material menandai situs dokumentasi.
Mode gelap menggunakan permukaan bawaan Material dan warna tautan dari palet
Absensa. Tidak ada JavaScript tambahan, plugin eksternal, atau override templat.
Antarmuka memakai bahasa Indonesia. Mesin pencarian bawaan tidak mendukung
`id`, sehingga `lang: en` menjadi fallback untuk mengindeks tulisan Indonesia.
MkDocs dan Material dipin agar pembaruan dependensi dapat diperiksa sebelum dipakai.

Panduan pemasangan dan pemulihan teknis tetap di [deploy/README.md](deploy/README.md)
dan [deploy/BACKUPS.md](deploy/BACKUPS.md). Situs ini ditujukan untuk pengguna
aplikasi, dengan jalur belajar administrator dan operator.
