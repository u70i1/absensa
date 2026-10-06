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

Ikuti [panduan pemasangan](https://github.com/u70i1/absensa/blob/v1.0.0/deploy/README.md). Windows Server 2019/2022/2025 memakai backend native; baca batas validasi pada panduan Windows. DNS-01 otomatis tersedia untuk Cloudflare; jaringan lain dapat memakai proxy yang sudah tersedia atau CA lokal.

Instalasi lama berbasis kode sumber tidak dipindahkan otomatis ke installer rilis. Cadangkan data dan ikuti [panduan pemulihan](https://github.com/u70i1/absensa/blob/v1.0.0/deploy/BACKUPS.md) sebelum migrasi. Deployment ini memakai PostgreSQL 18; peningkatan versi mayor PostgreSQL memerlukan prosedur migrasi tersendiri.

Artefak rilis: `absensa-linux-amd64.tar.gz`, `absensa-windows-amd64.zip`, `install.ps1`, `SHA256SUMS`, `SHA256SUMS.windows`, `provenance.jsonl`, dan `provenance-windows.jsonl`. Publikasi rilis dilakukan setelah pemeriksaan image publik, artefak, dan instalasi pada lingkungan bersih.


## Native Windows Server deployment

The same application tag now builds Linux amd64 and Windows amd64 packages.
Windows Server 2019/2022/2025 are targeted through PowerShell 5.1, bundled
runtimes, six native Windows services, private ProgramData storage and verified
release updates. No WSL/VM/Docker Desktop is required. Linux deployment remains
available with the existing artifact/checksum/provenance contract.

Maintainers must attach actual Windows CI and field-test evidence before
publishing, especially Server 2019, reboot without login, Chrome under the service
identity, and cross-platform restores. See deploy/windows/VALIDATION.md.
