# Absensa v1.1.0

Rilis ini memperkenalkan deployment native Windows Server bersama jalur
Linux amd64 berbasis container yang sudah tersedia pada v1.0.0.
Tag dan artefak v1.0.0 tetap dipertahankan.

## Perubahan utama

- Paket `absensa-windows-amd64.zip` siap pakai dengan CPython, Node.js,
  PostgreSQL 18, Chrome for Testing, Caddy/Cloudflare, WinSW, Cairo dan libarchive.
  Server tidak memerlukan Python, Node.js atau PostgreSQL terpisah, WSL,
  Docker Desktop, VM, maupun compiler.
- Bootstrap PowerShell 5.1 memverifikasi SHA-256 dan provenance GitHub untuk tag
  rilis yang sama dengan Linux. Paket menjalankan enam layanan native dengan
  akun virtual terpisah, binary di `C:\Program Files\Absensa` dan data privat
  di `C:\ProgramData\Absensa`.
- Pengelolaan Windows mencakup HTTPS CA lokal atau Cloudflare DNS-01, migrasi,
  cadangan terenkripsi, pemulihan database/foto ke penyimpanan baru, pembaruan
  dengan cadangan wajib, perbaikan, dan uninstall yang mempertahankan data.
- Workflow rilis membangun dan menguji kedua platform, memverifikasi checksum
  dan provenance, lalu membuat satu **draft** untuk ditinjau pengelola.
  Kontrak checksum/provenance Linux tetap kompatibel dengan installer lama.

## Pemasangan dan batas validasi

Ikuti [panduan pemasangan](https://github.com/u70i1/absensa/blob/v1.1.0/deploy/README.md)
atau [panduan Windows](https://github.com/u70i1/absensa/blob/v1.1.0/deploy/windows/README.md).
Paket Windows baru dapat dipasang setelah v1.1.0 diterbitkan sebagai rilis stabil;
bootstrap tidak menggunakan draft atau kode aplikasi dari `main`.

Build paket dan drill layanan native telah lulus di GitHub Actions Windows
Server 2022 dan 2025. Server 2019 diterima oleh bootstrap tetapi **belum
tervalidasi saat runtime**; tidak ada job Server 2019 pada matriks CI.
Reboot tanpa login, pairing/reconnect WhatsApp, Cloudflare issuance/renewal,
dan pemulihan lintas platform tetap memerlukan bukti lapangan. Lihat
[catatan validasi dan syarat publikasi](https://github.com/u70i1/absensa/blob/v1.1.0/deploy/windows/VALIDATION.md).

Pembaruan Windows diuji menggunakan paket kandidat lokal di runner. Karena
v1.0.0 tidak memiliki paket Windows, belum ada bukti upgrade Windows dari
rilis stabil sebelumnya. Unduhan publik dan attestation paket v1.1.0 diperiksa
pada workflow tag dan setelah publikasi; keduanya tidak disimulasikan sebagai
bukti instalasi publik yang sudah selesai.

Jalur Linux tetap memakai Docker Engine/Compose dan image digest terverifikasi.
Instalasi source/Compose lama tidak diadopsi otomatis. Cadangkan data dan ikuti
[panduan pemulihan](https://github.com/u70i1/absensa/blob/v1.1.0/deploy/BACKUPS.md)
sebelum migrasi. Peningkatan mayor PostgreSQL memerlukan prosedur tersendiri.
Konfigurasi deployment dan sesi WhatsApp tidak otomatis dikonversi lintas OS.

Artefak: `absensa-linux-amd64.tar.gz`, `absensa-windows-amd64.zip`, `install.ps1`,
`SHA256SUMS`, `SHA256SUMS.windows`, `provenance.jsonl`, dan
`provenance-windows.jsonl`. `SHA256SUMS` hanya memuat arsip Linux;
`SHA256SUMS.windows` memuat ZIP Windows dan bootstrap.
