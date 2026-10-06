# Windows Server

Buka **Windows PowerShell 64-bit → Run as administrator**, lalu jalankan:

```powershell
irm https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1 | iex
```

Perintah ini berlaku **setelah perubahan digabungkan dan rilis stabil Windows
lengkap diterbitkan**. Belum ada rilis yang diterbitkan oleh pekerjaan ini.
Bootstrap dari `main` hanya memilih rilis dan memverifikasinya. Aplikasi, runtime,
dan pengelola berasal dari satu tag stabil `vMAJOR.MINOR.PATCH`, sama dengan Linux.
Tidak perlu Git, Python, Node, PostgreSQL, Docker, WSL, atau VM di server sekolah.

Installer menanyakan IP LAN/nama DNS, port HTTPS dan pilihan CA lokal atau domain
Cloudflare, membuat rahasia acak, memasang layanan, menjalankan migrasi,
memeriksa HTTPS/database/worker, lalu meminta akun admin pertama. Gunakan sandi
minimal 12 karakter. Akun admin yang sudah ada tidak diubah.

Untuk meninjau bootstrap sebelum menjalankan, unduh `install.ps1`, baca berkasnya,
lalu jalankan `powershell -NoProfile -File .\install.ps1`. Jangan mengubah execution
policy seluruh komputer. Kebijakan AllSigned/AppLocker/WDAC sekolah mungkin perlu
persetujuan petugas IT; installer tidak menonaktifkannya. Tidak ada elevasi diam-diam.

## Dukungan dan persiapan

Target: **Windows Server 2019 (17763), 2022 (20348), 2025 (26100), amd64**, Windows
PowerShell 5.1, NTFS lokal, hak Administrator saat instalasi/pemeliharaan. Domain
controller bukan target tervalidasi; gunakan member server. Desktop Windows,
ARM64/32-bit, volume jaringan, junction/symlink, dan cluster multi-node tidak
didukung backend ini. Virtualisasi tidak diperlukan.

Sediakan 4 core, RAM 8 GB, disk SSD dengan sedikitnya 10 GB kosong untuk binary
serta kapasitas data/cadangan (40 GB atau lebih disarankan), IP LAN tetap, DNS dan
jam server yang benar. Paket membawa browser sehingga unduhan besar; cadangan
membutuhkan ruang tambahan. Internet diperlukan untuk GitHub, sumber GitHub CLI,
Sigstore saat instalasi/update, WhatsApp, dan DNS Cloudflare jika digunakan.

**Status validasi:** CI disiapkan untuk build dan layanan nyata pada runner
Windows 2022/2025; menambahkan workflow bukan bukti bahwa workflow sudah lulus.
Lingkungan pengembangan perubahan ini Linux. Hasil aktual dan pemeriksaan mesin
2019/2022/2025 tercatat di `VALIDATION.md` pada direktori dokumentasi Windows di
repositori. Server 2019 tetap diterima, tetapi wajib menjalani uji mesin nyata
sebelum dipakai sekolah: paket PostgreSQL 18 EDB hanya mencantumkan sertifikasi
2022/2025. Ini batas bukti pengujian vendor, bukan alasan mengganti jalur 2019
menjadi VM atau menurunkan versi database tanpa migrasi.

## Lokasi dan layanan

| Isi | Lokasi |
| --- | --- |
| Binary/runtimes setiap versi | `C:\Program Files\Absensa\releases\vX.Y.Z\` |
| Perintah pengelolaan | `C:\Program Files\Absensa\absensa.ps1` |
| Konfigurasi privat dan kunci pemulihan | `C:\ProgramData\Absensa\config\` |
| PostgreSQL | `C:\ProgramData\Absensa\postgres\` |
| Foto/logo | `C:\ProgramData\Absensa\photos\live\` (atau pohon pemulihan) |
| Cadangan terenkripsi | `C:\ProgramData\Absensa\backups\` |
| Sesi WhatsApp dan CA Caddy | `C:\ProgramData\Absensa\whatsapp\`, `caddy\` |
| Log layanan dan pemeliharaan | `C:\ProgramData\Absensa\logs\` |
| Jurnal instalasi/update | `C:\ProgramData\Absensa\state.json` |

Layanan: `AbsensaPostgreSQL`, `AbsensaWeb`, `AbsensaScheduler`, `AbsensaBackup`,
`AbsensaWhatsApp`, `AbsensaCaddy`. PostgreSQL memakai layanan native `pg_ctl`;
proses lain memakai WinSW 2.12.0 varian .NET Framework 4.6.1 yang dikunci SHA-256
dan memakai .NET Framework bawaan/terbarui OS (4.7.2+ pada Server 2019). Setiap layanan memakai akun
virtual `NT SERVICE\<nama layanan>`, bukan akun administrator. Setelah instalasi
sehat, SCM mengatur startup otomatis dan restart saat gagal, tanpa login desktop.
Saat pemeliharaan, startup otomatis dinonaktifkan sampai fase aman selesai.

ACL membatasi konfigurasi utama/kunci pemulihan kepada Administrators dan SYSTEM.
Layanan menerima konfigurasi masing-masing; Caddy/WhatsApp tidak membaca sandi
PostgreSQL, web tidak membaca kunci enkripsi backup. Hanya PostgreSQL mengubah
cluster, web mengubah foto, backup membaca foto dan mengubah cadangan. Jangan
membagikan `ProgramData\Absensa` sebagai folder jaringan. Gunakan BitLocker/kebijakan
penyimpanan sekolah untuk melindungi data saat disk dilepas.

## Jaringan dan HTTPS

Caddy menerima TCP HTTPS 443 (atau port yang dipilih). Installer hanya menambah
aturan `Absensa-Native-HTTPS`: executable Caddy yang dipasang, port terpilih,
profil **Domain/Private**, sumber **LocalSubnet**. TCP 80 dan UDP 443 tidak dibuka;
HTTP/3 dinonaktifkan. Firewall tidak dimatikan. Jaringan Public atau VLAN lain
memerlukan aturan terarah dari petugas IT. Installer tidak mengubah DNS/router.

PostgreSQL `127.0.0.1:55438`, web `127.0.0.1:18088`, WhatsApp
`127.0.0.1:13001` tidak dipublikasikan ke LAN. Konflik port menghentikan instalasi;
installer tidak mematikan aplikasi e-Rapor/ujian lain. Proses lokal dengan akses
ke server dipercaya; proxy headers web hanya dipercaya dari loopback.

CA lokal disimpan privat oleh Caddy. Salin hanya `C:\ProgramData\Absensa\root-ca.crt`
ke perangkat sekolah, cocokkan SHA-256 yang dicetak, lalu pasang sebagai CA
tepercaya sesuai kebijakan IT. Jangan menyalin private key. Pemeriksaan installer
memvalidasi nama dan rantai sertifikat; tidak ada opsi mematikan verifikasi TLS.

Domain Cloudflare menggunakan DNS-01; token hanya memerlukan Zone:DNS:Edit dan
Zone:Zone:Read untuk zona sekolah. Nama DNS harus menuju IP LAN sekolah untuk
klien LAN. Konfigurasi reverse proxy luar belum menjadi pilihan wizard Windows;
backend Linux tetap mempertahankan mode proxy yang sudah ada.

## Pengelolaan

Jalankan dari PowerShell Administrator. Tidak perlu mengubah PATH:

```powershell
& 'C:\Program Files\Absensa\absensa.ps1' status
& 'C:\Program Files\Absensa\absensa.ps1' start
& 'C:\Program Files\Absensa\absensa.ps1' stop
& 'C:\Program Files\Absensa\absensa.ps1' restart
& 'C:\Program Files\Absensa\absensa.ps1' logs web
& 'C:\Program Files\Absensa\absensa.ps1' logs postgres
& 'C:\Program Files\Absensa\absensa.ps1' admin
& 'C:\Program Files\Absensa\absensa.ps1' backup
& 'C:\Program Files\Absensa\absensa.ps1' update
& 'C:\Program Files\Absensa\absensa.ps1' repair
```

`status` menampilkan versi terpasang, tahap pemeliharaan, dan keadaan enam layanan.
`start`/`restart` memeriksa kesehatan sebelum mengaktifkan startup otomatis.
`stop` juga menonaktifkan startup otomatis sampai `start` berikutnya. `logs`
menampilkan 80 baris terakhir; pilihan lain: `scheduler`, `backup`, `whatsapp`,
`caddy`. Log console diputar 10 MB × 5; PostgreSQL memakai rotasi harian tujuh
nama. Log operasi/bootstrap perlu diarsipkan oleh IT bila membesar.
`admin` membuat admin pertama; tidak mereset akun yang ada.

## Cadangan dan pemulihan

Pekerja `AbsensaBackup` menjalankan cadangan database/foto terjadwal dengan kode
aplikasi yang sama seperti Linux. Waktu awal 10:00 dan 17:00 Asia/Jakarta;
jadwal/retensi dapat diubah di menu Cadangan. Arsip `.absbackup` memakai
`pg_dump -Fc`, foto/logo, manifest, dan AES-256-GCM yang sama pada dua platform.
Menu Cadangan dapat membuat dan mengunduh arsip ini.

Perintah `backup` menghentikan aplikasi sementara, membuat cadangan database/foto
baru, lalu membungkusnya bersama konfigurasi privat, sesi WhatsApp dan CA menjadi
`.absfull` terenkripsi dan terautentikasi. Rahasia hanya berada di dalam enkripsi.
Simpan `config\recovery.key` **secara terpisah** dari arsip. Salin cadangan ke disk
lain/USB/NAS dengan prosedur sekolah. Cadangan lengkap manual tidak dirotasi
otomatis; pantau kapasitas dan arsipkan/hapus arsip lama hanya setelah memverifikasi
salinan eksternal. Penjadwalan full snapshot setara cron Linux belum disediakan;
jadwal database/foto tetap otomatis.

Pemulihan dilakukan ke database baru dan pohon foto baru; database/foto sebelumnya
tetap disimpan. Diperlukan instalasi native yang sudah sehat (untuk bencana pada
server baru, pasang versi arsip terlebih dahulu), arsip dan kunci asli:

```powershell
& 'C:\Program Files\Absensa\absensa.ps1' restore 'D:\Cadangan\sekolah.absfull' 'E:\Kunci\recovery.key'
& 'C:\Program Files\Absensa\absensa.ps1' activate
```

Konfirmasi `PULIHKAN`, lalu hentikan instalasi sumber sebelum `AKTIFKAN` agar tidak
mengirim WhatsApp ganda. Restore membuat cadangan instalasi tujuan lebih dahulu.
Arsip lengkap Windows memerlukan versi aplikasi yang sama. Hasil restore tetap
berhenti sampai aktivasi; migrasi/health gagal tidak menyalakan versi lama.
Pemulihan `.absbackup` Linux juga diterima: database dan foto dipindahkan,
konfigurasi Windows tujuan dipertahankan, WhatsApp harus ditautkan ulang. Arsip
`.absfull` Linux dapat diambil database/fotonya; konfigurasi Compose/session Linux
tidak otomatis dikonversi. Arsip Windows `.absbackup` dapat dipulihkan dengan
prosedur PostgreSQL/foto Linux yang sudah ada. Uji lintas OS nyata masih wajib.

Jangan membuka dump dari sumber yang tidak dipercaya; autentikasi hanya membuktikan
penguasaan kunci cadangan. Restore berjalan dengan role database aplikasi yang
bukan superuser. Direktori `recovery` memuat hasil dekripsi privat untuk diagnosis;
setelah hasil diverifikasi, petugas IT dapat menghapus staging plaintext tersebut
sesuai kebijakan penyimpanan. Jangan hapus database/foto lama sebelum pemeriksaan.

## Update dan instalasi terhenti

`update` mengunduh satu tag stabil, memeriksa SHA-256 dan attestation workflow/tag
GitHub yang tepat, lalu membuat backup lengkap wajib. Binary versi baru disimpan
berdampingan dengan versi lama. PostgreSQL tetap mayor 18, migrasi Alembic tetap
kode aplikasi yang sama; upgrade mayor PostgreSQL/aplikasi yang tidak dinyatakan
kompatibel ditolak. Runtimes/browser ikut diperbarui lewat rilis Absensa.

Jika migrasi atau health gagal, layanan aplikasi tetap berhenti dan jurnal
menyimpan versi tujuan serta lokasi backup. Jalankan `status`, baca log, lalu
`repair` untuk melanjutkan versi tujuan. **Jangan mengganti state ke versi lama**
atau menyalakan layanan manual. Tidak ada downgrade database otomatis; pemulihan
ke instalasi bersih dengan versi sebelum update adalah jalur kembali yang aman.

Mengulangi installer memperbaiki versi tersimpan; tidak merotasi rahasia atau
menjalankan update tanpa backup. Jika `initdb` terhenti sebelum menghasilkan
`PG_VERSION`, installer mempertahankan direktori parsial dan meminta pemeriksaan.
Untuk instalasi baru yang belum pernah siap, IT dapat memindahkan direktori
PostgreSQL parsial ke lokasi karantina setelah memastikan tidak ada data sekolah,
lalu menjalankan `repair`. Jangan menerapkan langkah ini pada database yang hilang
atau rusak dari instalasi yang pernah dipakai.

Jika state/config hilang atau rusak, pulihkan kedua berkas dari penyimpanan aman;
installer tidak menebak sandi/database atau membuat database kosong pengganti.
Untuk restore terhenti, lihat `state.json` dan `recovery\restore_*\previous-config.json`.
Biarkan layanan berhenti dan pulihkan backup ke instalasi bersih dengan bantuan IT;
jangan menghapus jurnal untuk memaksa startup.

## Menghapus aplikasi

```powershell
& 'C:\Program Files\Absensa\absensa.ps1' uninstall
```

Ketik `HAPUS APLIKASI`. Layanan dihentikan/dihapus, aturan firewall Absensa dihapus,
lalu launcher menghapus direktori binary setelah Python keluar. **Seluruh
ProgramData, database, foto, konfigurasi, kunci dan cadangan dipertahankan.** Tidak
ada opsi menghapus data otomatis. Simpan cadangan dan kunci sebelum uninstall. Mengulangi bootstrap setelah uninstall
memasang ulang versi yang tercatat dan menggunakan data/rahasia yang dipertahankan.

## Jika belum dapat dibuka

1. Jalankan `status`, lalu `logs` untuk layanan yang berhenti.
2. Periksa disk kosong dan waktu server. Installer menampilkan lokasi
   `ProgramData\Absensa\bootstrap\<id>\bootstrap.log`; operasi memakai
   `logs\operations.log`. Jangan membagikan config/kunci bersama laporan masalah.
3. Jika server bisa membuka namun perangkat LAN tidak bisa, periksa DNS/IP,
   profil jaringan Domain/Private, cakupan LocalSubnet, port dan CA perangkat.
4. Jika hanya WhatsApp gagal, hubungkan melalui menu WhatsApp. Liveness bukan
   bukti QR/session/pengiriman berhasil. Chromium berjalan headless dengan sandbox.
5. Bila unduhan/attestation ditolak, periksa akses GitHub/Sigstore dan jam server.
   Jangan melewati checksum atau mematikan TLS. Rilis tanpa paket Windows lengkap
   tidak dapat dipasang melalui bootstrap baru.
