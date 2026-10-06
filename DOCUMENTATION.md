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

Panduan pemasangan dan pemulihan teknis tetap di [deploy/README.md](deploy/README.md),
[Windows Server native](deploy/windows/README.md),
dan [deploy/BACKUPS.md](deploy/BACKUPS.md). Situs ini ditujukan untuk pengguna
aplikasi, dengan jalur belajar administrator dan operator.

Kerangka mengikuti halaman aplikasi yang sudah terhubung ke navigasi. Log
Presensi sudah tersedia meskipun bagian lama README menyebutnya placeholder.
Riwayat operator yang terlihat adalah Riwayat Scan Hari Ini; endpoint lama tidak
menjadi panduan tombol yang tidak tersedia. Pencatatan terbatas pada siswa aktif,
satu kali per hari menurut zona waktu sekolah. Pengelolaan admin dan pemulihan
cadangan tidak dibuat sebagai menu web. Pengaturan dikelompokkan pada fitur
masing-masing, tanpa mengasumsikan menu Pengaturan umum.

## Validasi dan publikasi

[Workflow dokumentasi](.github/workflows/docs.yml) memakai Python 3.12 dan
menjalankan build strict untuk PR menuju `main` serta perubahan dokumentasi
di `main`. Path yang dipantau: `docs/**`, `mkdocs.yml`, `requirements-docs.txt`,
`DOCUMENTATION.md`, dan workflow itu sendiri. Pemeriksaan PR dapat berjalan
sebelum Pages diaktifkan. Workflow rilis aplikasi membangun Linux dan Windows dari tag versi yang sama;
lihat [panduan rilis](deploy/RELEASING.md).

Setelah perubahan digabungkan ke `main`, job build mengunggah artefak `site/`
dan job deploy menerbitkannya melalui Actions resmi GitHub Pages. Job deploy
saja memiliki izin `pages: write` dan `id-token: write`. Tidak ada branch
`gh-pages`. Dependabot yang sudah ada memantau pin GitHub Actions.

Workflow juga dapat dijalankan dari **Actions → Documentation → Run workflow**.
Pilih `main` untuk publikasi; branch lain hanya menjalankan validasi.

## Pengaturan GitHub yang perlu disiapkan

1. Buka [Settings → Pages](https://github.com/u70i1/absensa/settings/pages).
   Pada **Build and deployment → Source**, pilih **GitHub Actions**.
   Biarkan **Custom domain** kosong; situs direncanakan memakai
   `https://u70i1.github.io/absensa/`.
2. Pastikan GitHub Actions diizinkan di pengaturan repositori. Jika kebijakan
   membatasi Actions, izinkan `actions/checkout`, `actions/setup-python`,
   `actions/configure-pages`, `actions/upload-pages-artifact`, dan
   `actions/deploy-pages`. Tidak diperlukan token atau rahasia tambahan.
3. Setelah environment `github-pages` tersedia, periksa aturan deployment-nya
   di **Settings → Environments**. Izinkan `main`; sesuaikan persetujuan
   environment jika publikasi otomatis diinginkan.
4. Tinjau dan gabungkan PR dokumentasi. Pastikan job build dan deploy berhasil.
   Jika Pages baru diaktifkan setelah merge, jalankan workflow secara manual
   dari `main`. URL situs belum dianggap aktif sampai deployment berhasil.

Jika memakai branch protection, jadikan **Validate documentation** wajib hanya
dengan kebijakan yang sesuai path filter: PR tanpa perubahan dokumentasi tidak
menjalankan workflow ini.
