# Absensa v1.0.0

Rilis stabil pertama Absensa untuk pencatatan kehadiran sekolah.

## Fitur

- Pemindaian kehadiran, riwayat, dan ringkasan harian untuk operator.
- Pengelolaan siswa, kelas, akun operator, serta perangkat tepercaya melalui dasbor admin.
- Impor dan ekspor spreadsheet, operasi massal, foto siswa, serta kartu siswa yang dapat dicetak.
- Pengiriman pemberitahuan ketidakhadiran melalui WhatsApp yang dihubungkan oleh admin.
- Pemasangan HTTPS melalui installer Linux amd64, dengan image yang dipatok berdasarkan digest dan artefak yang diverifikasi asalnya.
- Cadangan terenkripsi, pemulihan terisolasi, pembaruan dengan cadangan wajib, dan perintah perbaikan.

## Pemasangan dan kompatibilitas

Ikuti [panduan pemasangan](https://github.com/u70i1/absensa/blob/v1.0.0/deploy/README.md). Windows memerlukan WSL2 yang kompatibel atau VM Linux. DNS-01 otomatis tersedia untuk Cloudflare; jaringan lain dapat memakai proxy yang sudah tersedia atau CA lokal.

Instalasi lama berbasis kode sumber tidak dipindahkan otomatis ke installer rilis. Cadangkan data dan ikuti [panduan pemulihan](https://github.com/u70i1/absensa/blob/v1.0.0/deploy/BACKUPS.md) sebelum migrasi. Deployment ini memakai PostgreSQL 18; peningkatan versi mayor PostgreSQL memerlukan prosedur migrasi tersendiri.

Artefak rilis: `absensa-linux-amd64.tar.gz`, `SHA256SUMS`, dan `provenance.jsonl`. Publikasi rilis dilakukan setelah pemeriksaan image publik, artefak, dan instalasi pada lingkungan bersih.
