# Windows Server

<<<<<<< HEAD
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
=======
Open **64-bit Windows PowerShell as Administrator**, then run:

~~~powershell
irm https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1 | iex
~~~

This command becomes available after these changes are merged and a complete stable Windows release has been published. This work has not published a release. The script at main is only a bootstrapper: it selects and verifies a release. The application, runtimes, and management tools come from the same vMAJOR.MINOR.PATCH tag as Linux.

The server does not need Git, Python, Node.js, PostgreSQL, Docker, WSL, or a VM. The installer asks for the LAN IP address or DNS name, HTTPS port, and whether to use a local CA or Cloudflare domain. It generates secrets, installs services, runs migrations, checks HTTPS, the database, and workers, then asks for the first administrator account. Use a password of at least 12 characters. Existing administrator accounts are not changed.

To inspect the bootstrapper before running it, download install.ps1, read it, and run PowerShell with NoProfile and File. Do not change the machine-wide execution policy. AllSigned, AppLocker, and WDAC policies may need IT approval; the installer does not disable protections or elevate silently.

## Supported systems and preparation

Supported targets are **Windows Server 2019 (17763), 2022 (20348), and 2025 (26100)** on amd64, with Windows PowerShell 5.1, a local NTFS volume, and Administrator access for installation and maintenance. Domain controllers have not been validated; use a member server. Windows desktop editions, ARM64, 32-bit Windows, network volumes, junctions/symlinks, and multi-node clusters are not supported. Virtualization is not required.

Provide four CPU cores, 8 GB RAM, an SSD with at least 10 GB free for binaries, and enough additional capacity for school data and backups; 40 GB or more is recommended. The server needs a stable LAN IP, correct DNS, and a correct clock. The package includes a browser, so the initial download is substantial and backups need additional space. Internet access is needed for GitHub, the GitHub CLI source, Sigstore during installation/update, WhatsApp, and Cloudflare DNS.

**Validation status:** CI is configured to build and exercise real services on Windows 2022 and 2025 runners, but that does not prove the workflow has run. This change was developed on Linux. Results and required field tests are in [VALIDATION.md](VALIDATION.md). Server 2019 remains supported, but must be tested on a real machine before school use: EDB's PostgreSQL 18 test matrix lists only 2022 and 2025. This is a gap in vendor evidence, not a reason to replace the native 2019 path with a VM or downgrade PostgreSQL without a migration.

## Locations and services

| Item | Location |
| --- | --- |
| Per-version binaries and runtimes | C:\\Program Files\\Absensa\\releases\\vX.Y.Z\\ |
| Management command | C:\\Program Files\\Absensa\\absensa.ps1 |
| Private configuration and recovery key | C:\\ProgramData\\Absensa\\config\\ |
| PostgreSQL cluster | C:\\ProgramData\\Absensa\\postgres\\ |
| Photos and logo | C:\\ProgramData\\Absensa\\photos\\live\\ or a recovery tree |
| Encrypted backups | C:\\ProgramData\\Absensa\\backups\\ |
| WhatsApp session and Caddy CA | C:\\ProgramData\\Absensa\\whatsapp\\ and caddy\\ |
| Service and maintenance logs | C:\\ProgramData\\Absensa\\logs\\ |
| Installation/update journal | C:\\ProgramData\\Absensa\\state.json |

The services are AbsensaPostgreSQL, AbsensaWeb, AbsensaScheduler, AbsensaBackup, AbsensaWhatsApp, and AbsensaCaddy. PostgreSQL uses its native pg_ctl service. The other processes use the SHA-256-pinned WinSW 2.12.0 .NET Framework 4.6.1 variant, using the built-in or updated .NET Framework (4.7.2 or later on Server 2019). Each service uses its own virtual NT SERVICE account, never an administrator account. Once healthy, SCM configures automatic startup and restart on failure without a desktop login. Automatic startup is disabled during maintenance until the safe stage completes.

ACLs restrict master configuration and the recovery key to Administrators and SYSTEM. Services receive only their own configuration: Caddy and WhatsApp cannot read the PostgreSQL password, and the web service cannot read the backup key. Only PostgreSQL modifies its cluster, the web service modifies photos, and the backup service modifies backups. Do not share ProgramData\\Absensa over the network. Use BitLocker and the school's storage policy to protect removed disks.

## Networking and HTTPS

Caddy listens on TCP HTTPS 443, or the selected port. The installer adds only Absensa-Native-HTTPS: the installed Caddy executable, selected port, **Domain/Private** profiles, and **LocalSubnet** sources. It does not open TCP 80 or UDP 443, HTTP/3 is disabled, and the Windows Firewall remains enabled. Public networks and other VLANs need a narrowly scoped rule from school IT. The installer does not change DNS or routers.

PostgreSQL (127.0.0.1:55438), the web application (127.0.0.1:18088), and WhatsApp (127.0.0.1:13001) are never published to the LAN. A port conflict stops installation; the installer never stops an e-Rapor, exam, or other school application. Web proxy headers are trusted only from loopback.

For a local CA, copy only C:\\ProgramData\\Absensa\\root-ca.crt to school devices, compare its printed SHA-256 fingerprint, then install it as a trusted CA under school policy. Never copy the private key. The installer validates certificate names and chains; it has no option to disable TLS verification.

Cloudflare domains use DNS-01. The token needs only Zone:DNS:Edit and Zone:Zone:Read for the school's zone. The DNS name must resolve to the LAN IP for LAN clients. The Windows wizard does not currently configure an external reverse proxy; Linux retains its existing proxy mode.

## Management

Run these commands from an elevated PowerShell session. No PATH change is needed:

~~~powershell
& 'C:\\Program Files\\Absensa\\absensa.ps1' status
& 'C:\\Program Files\\Absensa\\absensa.ps1' start
& 'C:\\Program Files\\Absensa\\absensa.ps1' stop
& 'C:\\Program Files\\Absensa\\absensa.ps1' restart
& 'C:\\Program Files\\Absensa\\absensa.ps1' logs web
& 'C:\\Program Files\\Absensa\\absensa.ps1' logs postgres
& 'C:\\Program Files\\Absensa\\absensa.ps1' admin
& 'C:\\Program Files\\Absensa\\absensa.ps1' backup
& 'C:\\Program Files\\Absensa\\absensa.ps1' update
& 'C:\\Program Files\\Absensa\\absensa.ps1' repair
~~~

status shows the installed version, maintenance stage, and all six service states. start and restart run health checks before enabling automatic startup. stop disables automatic startup until the next start. logs shows the latest 80 lines; use scheduler, backup, whatsapp, or caddy as needed. Console logs rotate at 10 MB × 5; PostgreSQL uses seven daily log files. admin creates only the first administrator and never resets an existing account.

## Backups and recovery

AbsensaBackup makes scheduled database and photo backups using the same application code as Linux. The initial schedule is 10:00 and 17:00 Asia/Jakarta; schedule and retention can be changed in the Backups interface. The absbackup format uses pg_dump -Fc, photos/logo, a manifest, and AES-256-GCM on both platforms.

The backup command temporarily stops the application, creates a new database and photo backup, then packages it with private configuration, the WhatsApp session, and the Caddy CA into an authenticated encrypted absfull archive. Store config\\recovery.key **separately** from the archive. Copy backups to a separate disk, USB device, or NAS. Manual full backups are not automatically rotated. There is no Windows equivalent to Linux cron full-snapshot scheduling yet; the database/photo schedule remains automatic.

Recovery creates a new database and photo tree while keeping the previous data. It requires a healthy native installation; on a replacement server, install the version used by the archive first. You need the archive and its original key:

~~~powershell
& 'C:\\Program Files\\Absensa\\absensa.ps1' restore 'D:\\Backups\\school.absfull' 'E:\\Keys\\recovery.key'
& 'C:\\Program Files\\Absensa\\absensa.ps1' activate
~~~

Confirm PULIHKAN, then stop the source installation before AKTIFKAN to avoid duplicate WhatsApp messages. Restore first backs up the target installation. Windows full archives require the same application version. The restored system stays stopped until activation; a migration or health failure does not restart an old application version.

Linux absbackup archives are accepted: the database and photos are imported, Windows configuration remains in place, and WhatsApp must be linked again. Linux absfull archives can provide the database and photos, but their Compose configuration and Linux session are not converted. A Windows absbackup can be restored with the existing Linux PostgreSQL/photo procedure. Real cross-platform restore tests remain required.

Do not open a dump from an untrusted source. Restore uses the non-superuser application database role. The recovery directory contains decrypted private staging data for diagnosis; remove it only after verification and under the school's storage policy. Do not remove old databases or photos before checking the restored system.

## Updates and interrupted installation

update downloads one stable tag, verifies its SHA-256 checksum and GitHub workflow/tag attestation, then creates a mandatory full backup. New binaries are stored beside the old version. PostgreSQL remains major version 18 and Alembic migrations use the same application code. Undeclared application or PostgreSQL major upgrades are rejected. The release also supplies runtime and browser updates.

If migration or health checks fail, application services remain stopped and the journal records the target version and backup location. Run status, inspect the logs, then run repair to continue the target version. **Do not change state back to the old version** or start services manually. Database rollback is not automatic; recovery into a clean installation running the previous version is the safe return path.

Running the installer again repairs the recorded version; it does not rotate secrets or update without a backup. If initdb stops before creating PG_VERSION, the installer preserves the partial directory and asks for investigation. For a new installation that was never healthy, IT may quarantine the partial PostgreSQL directory after confirming it contains no school data, then run repair. Never use this procedure for an installation that has already been used.

If state or configuration is missing or corrupted, restore both files from secure storage; the installer will not guess passwords or create an empty replacement database. For an interrupted restore, inspect state.json and recovery\\restore_*\\previous-config.json. Leave services stopped and recover into a clean installation with IT support; do not remove the journal to force startup.

## Uninstalling the application

~~~powershell
& 'C:\\Program Files\\Absensa\\absensa.ps1' uninstall
~~~

Type HAPUS APLIKASI. Services are stopped and removed, the Absensa firewall rule is removed, and the launcher removes the binary directory after Python exits. **All ProgramData files, database files, photos, configuration, keys, and backups are retained.** There is no automatic data-deletion option. Save backups and the recovery key before uninstalling. Running the bootstrap afterwards reinstalls the recorded version and reuses retained data and secrets.

## Troubleshooting

1. Run status, then logs with the stopped service name.
2. Check free disk space and the server clock. The installer reports a bootstrap log under ProgramData\\Absensa\\bootstrap; operations use logs\\operations.log. Do not include configuration or keys in support reports.
3. If the server can connect but LAN devices cannot, check DNS/IP, the Domain/Private network profile, LocalSubnet scope, port, and each device's CA.
4. If only WhatsApp fails, link it in the WhatsApp interface. Liveness is not proof of QR pairing, session health, or message delivery. Chromium runs headlessly with its sandbox.
5. If download or attestation verification fails, check GitHub/Sigstore access and the server clock. Do not bypass checksums or disable TLS. A release without a complete Windows package cannot be installed through this bootstrap script.
>>>>>>> f03c74e (feat: add native Windows Server deployment and unified releases)
