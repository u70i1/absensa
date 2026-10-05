# Memasang dan mengelola Absensa di sekolah

Panduan ini untuk installer rilis `install.sh`/`install.ps1`. Pengembangan aplikasi
menggunakan [RUNNING.md](../RUNNING.md). Jangan mencampur Compose pengembangan
dengan instalasi sekolah. Installer tidak memerlukan Git, Node.js, Python paket
aplikasi, PostgreSQL, atau Chromium di komputer sekolah; semuanya ada dalam image.
Python standar di Linux hanya dipakai untuk pengelolaan instalasi.

**Status distribusi:** kode installer dan workflow disiapkan dalam branch
`feat/installer`. URL `main` di bawah baru tersedia setelah perubahan digabungkan.
Instalasi memerlukan sedikitnya satu rilis stabil lengkap yang telah diterbitkan
pengelola. Installer berhenti jika rilis belum tersedia; tidak beralih ke kode
pengembangan. Lihat [panduan pengelola rilis](RELEASING.md).

## 1. Pilih komputer yang sesuai

| Lingkungan | Dukungan installer |
| --- | --- |
| Ubuntu Server 22.04/24.04 LTS amd64 | Jalur Linux, pemasangan dependensi melalui APT bila disetujui |
| Debian 12/13 amd64 | Jalur Linux, Python 3.10+ dan Docker Linux |
| Windows 11 23H2, build 22631 atau lebih baru yang masih didukung | PowerShell → Ubuntu/Debian di WSL2 2.1.5+, Docker Linux yang sudah disiapkan |
| Windows 10 22H2, build 19045, 64-bit | Bersyarat: harus tetap menerima pembaruan keamanan dan didukung versi Docker; minta konfirmasi petugas IT |
| Windows Server | VM Linux yang didukung, dengan IP LAN sendiri; bukan Docker Desktop |
| Windows 8/8.1, WSL1, container Windows, macOS, ARM/32-bit | Tidak didukung paket ini; gunakan server/VM Linux amd64 |

Untuk server yang harus kembali menyala tanpa login pengguna setelah listrik
padam, gunakan Linux atau VM Linux dengan startup otomatis. Docker Desktop/WSL
bergantung pada konfigurasi startup dan akun Windows; jangan menganggapnya sebagai
layanan server tanpa pengawasan. ARM belum didukung karena image cadangan memakai
pustaka PostgreSQL amd64.

Sediakan minimal 2 vCPU, RAM 4 GB untuk Docker (8 GB disarankan), RAM tersedia
minimal 2 GB saat pemasangan, dan ruang kosong minimal 10 GB. Sediakan disk 40 GB
atau lebih, disesuaikan jumlah foto dan retensi cadangan. Batas ini adalah syarat
awal, bukan hasil uji kapasitas sekolah besar. Windows/Docker Desktop membutuhkan
RAM host sesuai persyaratan vendornya, sedikitnya 8 GB. Gunakan SSD dan UPS bila ada.

Docker Engine minimal 24 dan Compose plugin minimal 2.24 diperlukan. Gunakan
versi yang masih menerima pembaruan keamanan. Instalasi baru membutuhkan internet
ke GitHub, GHCR, Docker Hub, repositori APT, dan Sigstore. Absensi dengan HTTPS
lokal dapat berjalan tanpa internet; WhatsApp dan perpanjangan sertifikat publik
membutuhkan internet. Sinkronkan tanggal/jam server.

## 2. Instalasi Linux — cara yang disarankan

Buka terminal akun yang akan mengelola Absensa. Akun itu harus mempunyai akses
Docker lokal; akses Docker setara dengan hak administrator mesin. Jangan memberikan
akses tersebut kepada semua guru/operator. Unduh dan baca installer lebih dahulu:

```bash
curl --proto '=https' --proto-redir '=https' -fsSL \
  https://raw.githubusercontent.com/u70i1/absensa/main/install.sh -o install.sh
less install.sh
bash install.sh
```

Jika `curl` belum ada, petugas IT dapat memasangnya melalui pengelola paket OS.
Cara cepat tersedia, tetapi menjalankan kode dari internet sebelum ditinjau:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh | bash
```

Pertanyaan dibaca dari terminal `/dev/tty`, bukan dari aliran unduhan. Jangan
jalankan dalam terminal otomatis tanpa interaksi. Jangan memakai `curl -k`.

Installer memeriksa OS dan arsitektur. Bila dependensi hilang, installer meminta
izin sebelum memakai `sudo`, menambah repositori APT resmi bertanda tangan, dan
memasang paket. Kunci GitHub CLI diperiksa dengan SHA-256 yang tertanam dalam
installer; kunci Docker diperiksa sidik jarinya. Paket yang sudah terpasang tidak
di-upgrade otomatis. Konflik dengan Docker/containerd yang sudah ada menghentikan
pemasangan untuk diperiksa petugas IT. Tidak ada skrip `get.docker.com` yang dijalankan.

Docker baru dapat memerlukan hak administrator atau login ulang untuk mengakses
soketnya. Installer tidak otomatis menambahkan pengguna ke grup Docker. Minta
petugas IT menetapkan akun pengelola atau jalankan dari terminal root yang telah
disetujui. Selalu gunakan akun dan direktori instalasi yang sama sesudahnya.
Jika Compose hilang dari Docker yang sudah terpasang, petugas IT harus memasang
plugin yang cocok tanpa mengganti instalasi Docker itu.

Lokasi awal adalah `$HOME/absensa`; direktori lain dapat diberikan sebagai argumen:

```bash
bash install.sh /lokasi/absensa
```

Gunakan direktori kosong yang bisa ditulis akun tersebut, tanpa spasi/karakter
khusus/tautan simbolis. Installer menanyakan alamat LAN/domain, mode HTTPS, port,
zona waktu, lokasi dan waktu cadangan. Rahasia database, penghubung WhatsApp, dan
kunci cadangan dibuat acak. Akun admin memakai mekanisme Argon2 aplikasi. Sandi
admin dikirim melalui stdin ke container, tidak disimpan dalam berkas atau argumen.

Sebelum menerapkan konfigurasi dan mengunduh image, installer menampilkan ringkasan
dan meminta persetujuan. Setelah image tersedia, pilih apakah ingin menyalakan
Absensa sekarang. **Jika memilih tidak, database, migrasi, web, dan WhatsApp belum
dinyalakan.** Jalankan `./absensa mulai` kemudian; admin pertama ditanyakan saat itu.
Menunda pembuatan admin juga diperbolehkan; buat dengan `./absensa admin` sebelum
sekolah mulai menggunakan aplikasi. Perintah ini tidak mengganti sandi admin yang ada.

## 3. Windows 10/11

Petugas IT menyiapkan WSL2 2.1.5+ dengan Ubuntu/Debian yang didukung dan Docker Linux.
Untuk Docker Desktop, aktifkan integrasi distribusi WSL tersebut. Persyaratan
Windows dan ketentuan lisensi Docker harus diperiksa oleh pengelola sekolah.
Installer tidak mengaktifkan virtualisasi, mengubah boot, atau memulai reboot.

Unduh dan periksa PowerShell bootstrap:

```powershell
Invoke-WebRequest 'https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1' -OutFile install.ps1
Get-Content .\install.ps1
powershell -NoProfile -File .\install.ps1
```

Ikuti kebijakan eksekusi skrip sekolah; jangan menonaktifkan kebijakan komputer
secara menyeluruh. Cara singkat mengunduh berkas lalu menjalankannya:

```powershell
Invoke-WebRequest 'https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1' -OutFile "$env:TEMP\absensa-install.ps1"; & "$env:TEMP\absensa-install.ps1"
```

Bootstrap memeriksa edisi/build, arsitektur dan versi WSL, lalu meminta nama
distribusi WSL2. Ia mengunduh installer Linux ke berkas sementara, menampilkan
lokasinya untuk ditinjau, dan meminta persetujuan sebelum menjalankan berkas itu.
Inti installer sama dengan Linux. Simpan instalasi di filesystem Linux WSL,
bukan `/mnt/c`, OneDrive, atau folder Windows yang izin Unix-nya berbeda.

Jalankan perintah pemeliharaan dari terminal distribusi WSL yang sama. Pada
Windows 10, dukungan teknis Docker dan status pembaruan keamanan/ESU perlu
konfirmasi petugas IT; nomor build saja tidak membuktikan status dukungan.

Alamat NAT WSL dapat berubah dan belum tentu dapat diakses Wi-Fi sekolah.
Petugas IT harus memilih jaringan WSL yang sesuai atau menggunakan VM dengan IP
LAN sendiri, mengatur aturan firewall terbatas ke LAN, lalu mencoba dari komputer
lain. Bootstrap tidak membuat port forwarding Windows/router. Untuk layanan
sekolah permanen, jalur VM Linux lebih mudah dipastikan startup dan akses LAN-nya.

## 4. Windows Server dan server bersama

Pada Windows Server, gunakan VM Ubuntu Server 24.04 LTS amd64 dalam Hyper-V atau
hypervisor yang memang dikelola sekolah. Administrator harus menyetujui pembuatan
VM, alokasi RAM/disk, jaringan virtual, startup otomatis, dan shutdown yang baik.
Jalankan installer Linux di dalam VM. Tidak diperlukan Docker Desktop di host
Windows Server, dan installer menolak menganggapnya lingkungan yang didukung.

Pada server e-Rapor/ujian/aplikasi lain, jangan mengganti Docker, mematikan web
server, atau mengosongkan disk aplikasi lain. Absensa memakai nama proyek acak
tersimpan seperti `absensa-a12b34c56d78`, jaringan dan volume terpisah, tanpa
`container_name` global. PostgreSQL dan WhatsApp tidak mempunyai port host.
Installer memeriksa RAM, disk dan port TCP termasuk port container Docker.
Port 80 tidak digunakan; bila 443 sudah dipakai, pilih 8443 atau mode proxy.
Tidak ada perintah prune, `down -v`, atau pembersihan volume dalam pengelola.

Mode biasa mempublikasikan port HTTPS pada semua antarmuka IPv4. Pada mesin yang
juga memiliki antarmuka publik, minta IT membatasi `BIND_IP` dalam
`production.env` ke IP LAN yang tepat sebelum startup. Docker dapat melewati
sebagian aturan UFW; gunakan aturan firewall yang sesuai Docker. Jangan membuat
port forwarding pada router internet. Installer tidak mengubah firewall/router.

## 5. HTTPS dan Wi-Fi sekolah

### Tanpa domain: CA lokal

Pilih mode **CA lokal**, lalu gunakan IP LAN tetap server, misalnya
`192.168.1.10`, atau nama DNS lokal seperti `absensa.sekolah.home.arpa`.
Jika port 8443 dipilih, alamatnya menjadi `https://192.168.1.10:8443`.
Tetapkan reservasi DHCP/IP bersama petugas IT agar alamat tidak berubah.

Caddy membuat dan memperpanjang sertifikat lokal. Kunci CA disimpan hanya dalam
volume Caddy dan cadangan lengkap terenkripsi. Installer menyalin **sertifikat
publik** menjadi `root-ca.crt` dan menampilkan sidik jari SHA-256. Pemeriksaan
HTTPS menggunakan CA itu dan tetap memvalidasi nama/alamat; tidak memakai `-k`.

Setiap perangkat sekolah harus mempercayai CA ini secara terpisah. Pindahkan
`root-ca.crt` melalui USB atau jalur sekolah yang terpercaya dan cocokkan sidik
jarinya dengan yang ditampilkan server. Jangan memindahkan `root.key`, `production.env`,
atau `recovery.key` ke perangkat siswa.

- **Windows:** buka sertifikat, pilih pemasangan pada penyimpanan *Trusted Root
  Certification Authorities* milik pengguna/perangkat sesuai kebijakan IT.
- **Android:** Pengaturan → Keamanan → Enkripsi/kredensial → Pasang sertifikat CA.
  Nama menu berbeda antarmerek. Perangkat terkelola mungkin memerlukan IT/MDM.
- **iPhone/iPad:** impor profil sertifikat, kemudian aktifkan kepercayaan root pada
  Pengaturan → Umum → Mengenai → Pengaturan Kepercayaan Sertifikat.
- **Firefox/Linux:** browser dapat memakai penyimpanan sertifikat berbeda. Impor
  CA ke Authorities atau gunakan kebijakan sertifikat organisasi.

Jika kebijakan perangkat tidak mengizinkan CA lokal, gunakan domain dengan
sertifikat publik. Jangan menekan “lanjutkan meskipun tidak aman” sebagai solusi.
Instalasi CA di server saja tidak memberikan kepercayaan kepada semua ponsel.

### Dengan domain: DNS-01 Cloudflare

Pilih **Domain di Cloudflare** untuk domain yang DNS otoritatifnya dikelola
Cloudflare, misalnya `absensa.sekolah.sch.id`. Masukkan token API yang hanya memiliki
izin `Zone:DNS:Edit` dan `Zone:Zone:Read` pada zona sekolah. Token dibaca tersembunyi,
disimpan dalam `production.env` berizin 0600, dan tersedia hanya bagi Caddy.
Pemilik akses Docker tetap dapat membaca environment container; batasi akun tersebut.

Caddy membuat record TXT ACME DNS-01 dan memperpanjang sertifikat otomatis.
Server hanya perlu koneksi **keluar** menuju DNS/ACME; tidak perlu membuka port
80/443 dari internet. Jangan mencabut token selama masih dipakai untuk pembaruan.

IT harus membuat DNS lokal agar domain mengarah ke IP privat server untuk perangkat
Wi-Fi/LAN. Pada DNS publik, DNS-01 tidak memerlukan record A publik menuju server.
Jangan menyalakan proxy CDN Cloudflare menuju alamat LAN. Split DNS, router yang
memblokir jawaban IP privat, DNS terenkripsi di ponsel, dan jaringan tamu dapat
memerlukan pengaturan khusus; installer tidak punya akses untuk mengubahnya.

Paket saat ini menyertakan **provider Cloudflare saja**. Untuk provider lain,
gunakan reverse proxy yang sudah mengelola DNS-01 provider tersebut, atau CA lokal.
Menambah provider memerlukan modul Caddy dalam rilis baru yang ditinjau pengelola;
installer tidak mengunduh plugin secara dinamis.

### Reverse proxy yang sudah ada

Pilih mode **reverse proxy** dengan domain publik yang dipakai pengguna. Absensa
menjalankan Caddy lokal pada `127.0.0.1:8443` (atau port kosong lain), dengan TLS CA
lokal. Administrator proxy membuat upstream HTTPS dan mempercayai `root-ca.crt`
Absensa. Proxy luar harus mempertahankan Host pengguna, mengirim SNI domain yang
sama, dan memverifikasi sertifikat upstream. Contoh Nginx, untuk ditinjau IT:

```nginx
location / {
    proxy_pass https://127.0.0.1:8443;
    proxy_set_header Host $http_host;
    proxy_ssl_server_name on;
    proxy_ssl_name absensa.sekolah.sch.id;
    proxy_ssl_trusted_certificate /lokasi-aman/absensa-root-ca.crt;
    proxy_ssl_verify on;
    client_max_body_size 100m;
}
```

Proxy luar harus menyediakan HTTPS dengan sertifikat yang sudah dipercaya klien
(dan trust store sistem server untuk pemeriksaan otomatis). Untuk proxy dalam
container lain, `127.0.0.1` menunjuk ke container itu sendiri; IT perlu merancang
jalur ke loopback host yang sesuai. Installer tidak menggabungkan jaringan Docker
aplikasi lain secara otomatis. Cara paling sederhana adalah memakai port HTTPS
Absensa tersendiri.

Pemeriksaan membuktikan HTTPS internal dan, dalam mode proxy, URL HTTPS luar.
Sebelum proxy luar dikonfigurasi, installer tidak menyatakan aplikasi siap.
Jalankan `./absensa periksa` setelah konfigurasi IT selesai.

FastAPI mendengarkan socket Unix yang hanya dipasang pada web dan Caddy, sehingga
header proxy dipercaya melalui jalur privat tersebut. Cookie admin dan operator
selalu `Secure`, `HttpOnly`, dan `SameSite`; pemeriksaan CSRF memakai origin HTTPS.
Port HTTP web tidak dipublikasikan. HSTS diberikan oleh Caddy.

## 6. Perintah sehari-hari

Dari direktori instalasi (contoh `cd ~/absensa`):

```bash
./absensa mulai
./absensa henti
./absensa ulang
./absensa status
./absensa periksa
./absensa log web
./absensa log whatsapp
./absensa log backup
./absensa admin
./absensa perbarui
./absensa perbaiki
```

`henti` mempertahankan container dan volume. `mulai` menjalankan migrasi versi yang
tersimpan lalu memeriksa kesehatan layanan dan HTTPS. Jangan mengganti nama proyek,
password database, atau kunci cadangan sembarangan. Jangan menjalankan Compose
pengembangan di direktori ini. Layanan memakai kebijakan `unless-stopped`: akan
kembali berjalan ketika Docker aktif setelah reboot, kecuali sebelumnya memang
dihentikan. Uji restart terencana dan akses LAN pada mesin sekolah sendiri.

WhatsApp dapat belum terhubung walaupun layanan sehat. Buka menu **WhatsApp** pada
halaman admin, hubungkan akun, lalu pindai QR dari ponsel sekolah. Internet dan
otorisasi manual WhatsApp masih diperlukan. Data pairing bertahan dalam volume.
Chromium memakai sandbox dengan kemampuan `SYS_ADMIN` hanya pada container
WhatsApp; ini hak yang cukup luas, sehingga jangan mempublikasikan API bridge.
Tidak ada container aplikasi yang mendapat Docker socket atau mode privileged.

Container tidak dianggap siap hanya karena proses hidup: database memakai
`pg_isready`, web memeriksa database melalui `/health`, bridge mempunyai probe HTTP,
dan pekerja memiliki heartbeat. Probe bridge tidak membuktikan sesi WhatsApp aktif.
Status backup sukses tetap perlu diperiksa di halaman **Cadangan**. Docker tidak
otomatis memperbaiki semua proses yang berstatus unhealthy; gunakan log/perbaiki.

## 7. Cadangan

Dua jenis cadangan saling melengkapi:

| Jenis | Isi dan waktu |
| --- | --- |
| Cadangan aplikasi `.absbackup` | Database + foto siswa/logo, AES-256-GCM. Default 10:00 dan 17:00 zona waktu sekolah. Jadwal dan retensi bisa diubah pada halaman Cadangan. Tidak menghentikan absensi. |
| Cadangan lengkap `.absfull` | Satu cadangan aplikasi terverifikasi + konfigurasi/versi + sesi WhatsApp + data/kunci CA Caddy. AES-256-GCM. Dibuat sebelum update, dapat dijalankan manual atau lewat cron harian. Menghentikan layanan sebentar untuk konsistensi. |

Cadangan aplikasi memakai snapshot PostgreSQL dan penguncian data foto yang sudah
ada di aplikasi. Retensi default: 14 hari, 8 minggu, 3 bulan, sebagai gabungan
titik pemulihan; jumlah hari dapat dipilih saat instalasi. Setelah database terisi,
pengaturan halaman Cadangan menjadi sumber utama, bukan nilai awal env.
Cadangan lengkap default menyimpan 7 arsip terbaru yang lolos autentikasi.
Arsip rusak tidak dijadikan pengganti arsip sehat. Kegagalan backup tidak mengizinkan
update. Riwayat file cadangan lama tidak disalin ke dalam setiap cadangan lengkap.

```bash
./absensa cadangkan
./absensa jadwal
./absensa ekspor /media/disk-sekolah/absensa-2026-10-02
```

`jadwal` meminta persetujuan sebelum menambah/mengganti satu baris milik proyek ini
pada crontab akun pengelola. Jadwal lengkap default 02:00 **waktu OS server**, dapat
diubah; retensinya juga ditanyakan. Baris pekerjaan lain dipertahankan. Bila cron
belum terpasang, petugas IT perlu memasang/mengaktifkannya; cadangan database/foto
melalui container tetap otomatis tanpa cron. Mesin harus menyala saat jadwal cron;
cron tidak mengejar semua jadwal yang terlewat. Periksa `schedule.log` sesudahnya.

`ekspor` menyalin cadangan lengkap terbaru ke **direktori baru**, memverifikasi
sumber dan hasil salinan, serta membuatnya berizin 0600 milik akun pemanggil.
Arsip dapat berada pada disk kedua, USB, atau filesystem server cadangan yang
sudah dipasang oleh IT. Installer tidak menyimpan sandi SMB/SSH atau memasang share.
Media tujuan harus menyediakan izin Unix dan cukup ruang; untuk drive Windows,
gunakan pengaturan mount/ACL IT yang sesuai. Putuskan media setelah penyalinan aman.

**Simpan `recovery.key` secara terpisah** dari disk cadangan, dalam media/penyimpanan
rahasia yang dikelola sekolah. Kehilangan kunci membuat arsip tidak bisa dipulihkan.
`production.env` juga mengandung kunci dan rahasia; hanya administrator sistem boleh
membacanya. Enkripsi arsip tidak mengenkripsi data aktif PostgreSQL atau env di
server; pertimbangkan enkripsi disk OS bersama IT.

Backup pada disk yang sama tidak melindungi dari kerusakan disk. Tetapkan petugas
untuk menyalin dan memeriksa backup setiap hari. Dengan jadwal aplikasi default,
perubahan sampai 17 jam terakhir dapat hilang ketika server gagal; kehilangan
sesudah salinan eksternal terakhir bergantung pada disiplin salinan sekolah.
Tidak ada jaminan waktu pemulihan sebelum diuji pada perangkat sekolah.

## 8. Pemulihan dan latihan pemulihan

Pemulihan selalu menuju **direktori dan proyek Docker baru**, bukan menimpa layanan
aktif. Siapkan ruang untuk database/foto baru dan data sementara yang didekripsi.
Internet dibutuhkan untuk mengambil kembali rilis asal dan memverifikasi provenance.
Simpan juga salinan artefak rilis di arsip sekolah; pemulihan offline otomatis belum
disediakan. Pengelola jangan menghapus artefak/image rilis lama.

```bash
./absensa pulihkan /media/disk/arsip.absfull /media/kunci/recovery.key /lokasi/absensa-pulih
```

Jika server lama rusak total, pasang installer di server Linux pengganti dan pilih
**tidak menyalakan sekarang**, lalu jalankan perintah di atas dari instalasi kosong
tersebut dengan kunci lama. Installer saat ini menyediakan alat dekripsi; versi
aplikasi tujuan diambil dari cadangan lalu diverifikasi kembali.

Alat mengautentikasi arsip, menolak path traversal/link/perangkat khusus, memulihkan
PostgreSQL dengan transaksi tunggal, memulihkan foto, WhatsApp dan CA, lalu menguji
web/database/HTTPS pada loopback dengan port lain. Tidak ada penjadwal atau WhatsApp
yang dinyalakan pada hasil latihan. Setelah pemeriksaan, layanan hasil pemulihan
dihentikan. Jumlah siswa/pemindaian dan revisi migrasi ditampilkan. Periksa pula
foto dan sampel data sesuai catatan sekolah sebelum dipakai sungguhan.

Untuk menggantikan server lama: hentikan instalasi lama termasuk WhatsApp dan
penjadwal, arahkan DNS/IP sesuai keputusan IT, lalu jalankan pada hasil pemulihan:

```bash
cd /lokasi/absensa-pulih
./absensa aktifkan
```

Perintah menanyakan konfirmasi layanan lama sudah berhenti, alamat, mode HTTPS,
port, dan token Cloudflare bila diperlukan, lalu melakukan pemeriksaan startup.
Jangan menjalankan dua salinan sesi WhatsApp secara bersamaan. WhatsApp dapat
meminta pairing ulang meskipun data sesi berhasil dipulihkan.

Latihan tidak otomatis menghapus container/volume/data apa pun. Catat lokasi
pengujian; petugas IT dapat menghapus hanya proyek latihan setelah dipastikan tidak
diperlukan. Data hasil dekripsi sementara dihapus oleh helper ketika operasi selesai;
mati listrik dapat meninggalkan direktori privat `restore-*`. Lindungi dan tangani
berkas itu sesuai kebijakan enkripsi disk. Jika pemulihan gagal, pertahankan arsip
asli dan ulangi ke direktori baru, bukan ke volume yang sudah terisi sebagian.

Untuk arsip aplikasi lama `.absbackup` saja, gunakan prosedur offline yang sudah
ada pada [BACKUPS.md](BACKUPS.md). Sesi WhatsApp/CA/config tidak ada dalam arsip itu.

## 9. Pembaruan dan perbaikan

Menjalankan installer kembali pada direktori yang sama menampilkan:
**1. Perbarui Absensa; 2. Perbaiki instalasi; 3. Batal**. Batal tidak mengubah
konfigurasi atau memulai layanan. Direktori lama tanpa `state.json` tidak dianggap
instalasi baru dan tidak ditimpa. Instalasi berbasis source/Compose lama memerlukan
migrasi data terencana menggunakan backup dan pemulihan, bukan mengganti sandi env.

Pembaruan mengambil rilis stabil terbaru; draft/prerelease dikecualikan. Arsip
diperiksa SHA-256, kemudian provenance Sigstore/GitHub diverifikasi untuk repositori,
workflow rilis, dan tag yang tepat. Digest image terdapat di manifest terverifikasi,
sehingga perubahan tag image tidak mengganti image yang dipasang. Checksum saja
bukan bukti keaslian. Bootstrap `main` tetap harus dipercaya/ditinjau pengguna;
provenance tidak membuktikan kode pengelola bebas kerentanan.

Urutan update: verifikasi rilis → validasi manifest/Compose → unduh image →
hentikan layanan → backup lengkap dan autentikasi → simpan jurnal transaksi →
migrasi → startup → health check dan HTTPS → catat versi selesai. Update antar
major dihentikan kecuali pengelola menyiapkan jalur khusus. Tidak ada downgrade
atau rollback database otomatis. **Mengganti image lama tidak membatalkan migrasi.**

Jika terhenti, jalankan `./absensa perbaiki`. Untuk backup yang terputus sebelum
migrasi, layanan sebelumnya dapat dipulihkan. Untuk migrasi yang terhenti,
perbaikan menawarkan mencoba lagi **versi tujuan yang sama**. Bila container
pemeliharaan sebelumnya masih berjalan, tunggu sebelum mencoba lagi. Jika migrasi
terus gagal, pulihkan arsip sebelum update ke proyek baru dan lakukan pengalihan
terencana. Jangan menghapus jurnal transaksi untuk memaksa versi lama berjalan.

Perbaikan membuat ulang konfigurasi Caddy dan nilai image dari konfigurasi lokal,
mengambil kembali berkas rilis yang hilang dengan verifikasi, serta membuat ulang
container yang dibutuhkan. Tidak mengganti sandi, akun, database, atau volume.
Volume data instalasi yang sudah aktif diperiksa sebelum startup/migrasi. Jika
hilang, alat berhenti agar database kosong tidak diam-diam menggantikan data
sekolah; periksa penyimpanan Docker atau pulihkan backup ke proyek baru.
Jika `production.env`/`state.json` hilang atau rusak, alat berhenti: rahasia tidak
bisa ditebak; gunakan cadangan lengkap. Jika launcher/file pengelola hilang,
jalankan bootstrap GitHub kembali pada direktori yang sama.

## 10. Gangguan umum

| Pesan/gejala | Tindakan |
| --- | --- |
| Rilis tidak tersedia / GitHub 404 | Pengelola harus menerbitkan rilis stabil dengan artefak lengkap; periksa internet dan visibilitas repositori. |
| Verifikasi provenance gagal | Periksa tanggal/jam, akses Sigstore/GitHub, `gh attestation verify --help`, dan tag. Jangan melewati verifikasi. |
| Docker tidak dapat diakses | Minta IT memeriksa daemon, konteks soket lokal dan izin akun; jangan mengubah container lain. |
| Alamat subnet Docker habis | Minta IT memeriksa jaringan Docker yang benar-benar tidak digunakan atau sediakan server lain. Jangan melakukan prune atau menghapus jaringan aplikasi sekolah. Setelah diperbaiki, jalankan perbaiki; pemulihan yang gagal diulang ke direktori baru. |
| Port sudah digunakan | Pilih port HTTPS berbeda, misalnya 8443, atau integrasikan proxy. Jangan hentikan e-Rapor/web server lain. |
| HTTPS tidak siap | `./absensa log caddy`, periksa DNS/token/domain/jam server. Tidak ada fallback HTTP. |
| Browser tidak percaya sertifikat | Pasang CA publik yang benar pada perangkat dan cocokkan fingerprint; jangan bypass peringatan. |
| Server bisa membuka tetapi ponsel tidak | Periksa DNS lokal, Wi-Fi tamu/client isolation, IP/port, firewall host/VM/Windows, NAT WSL bersama IT. |
| Cadangan gagal | Periksa media terpasang, ruang kosong, izin UID 10001, kunci, log backup dan halaman Cadangan. Update tidak dilanjutkan. |
| `perbaiki` berhenti saat migrasi | Pertahankan jurnal dan arsip; periksa log database dan pulihkan ke proyek baru bila perlu. |
| Layanan sehat tetapi WhatsApp belum bekerja | Pairing QR dan akses internet WhatsApp diperiksa terpisah. |
| Server restart tetapi aplikasi tidak kembali | Pastikan Docker/VM aktif otomatis dan layanan sebelumnya tidak sengaja dihentikan; WSL/Desktop bisa memerlukan login. |

`operations.log` hanya berisi tahap/tanggal, tidak berisi environment atau keluaran
SQL. `./absensa log` menyamarkan rahasia yang dikenal. Log aplikasi masih dapat
mengandung informasi operasional sekolah: jangan membagikan log mentah kepada
publik. Jangan membagikan `docker inspect`, env, kunci, atau arsip tanpa kontrol.

## Referensi dan batas pengujian

Keputusan kompatibilitas mengikuti [Docker Linux](https://docs.docker.com/engine/install/ubuntu/),
[Docker Windows](https://docs.docker.com/desktop/setup/install/windows-install/),
[WSL](https://learn.microsoft.com/windows/wsl/install),
[Caddy HTTPS](https://caddyserver.com/docs/automatic-https),
[modul Cloudflare](https://github.com/caddy-dns/cloudflare), dan
[verifikasi provenance GitHub](https://cli.github.com/manual/gh_attestation_verify).
Lihat [catatan pengujian installer](INSTALLER-VALIDATION.md) untuk hasil nyata dan
lingkungan yang belum diuji. Pemasangan CA di perangkat, DNS-01 akun sekolah,
Windows/Windows Server dan firewall/router sekolah tetap memerlukan uji lapangan.
