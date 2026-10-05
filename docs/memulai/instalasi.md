# Memasang Absensa

Absensa dipasang sekali pada komputer sekolah yang akan menjalankannya. Setelah
itu, guru dan staf membuka alamat Absensa dari perangkat masing-masing.
Orang yang memasang aplikasi boleh menjadi administrator sekaligus operator.

Pemasangan membutuhkan berkas `install.sh` atau `install.ps1` di `main` serta
rilis stabil Absensa yang lengkap. Jika rilis belum tersedia, pemasang akan
berhenti sebelum menjalankan aplikasi.

## Pilih komputer yang akan menjalankan Absensa

| Komputer sekolah | Jalur pemasangan |
| --- | --- |
| Windows 11 | Siapkan Ubuntu atau Debian di WSL2, lalu jalankan `install.ps1` dari PowerShell. |
| Windows 10 | Jalur WSL2 yang sama, selama Windows dan Docker masih mendapat dukungan keamanan yang sesuai. Pemasang memeriksa versi Windows. |
| Windows Server | Buat mesin virtual (VM) Ubuntu Server 24.04 LTS 64-bit, lalu jalankan `install.sh` di dalam VM. `install.ps1` tidak memasang Absensa langsung di Windows Server. |
| Ubuntu 22.04/24.04 atau Debian 12/13 64-bit | Jalankan `install.sh` langsung dari terminal Linux. |

Siapkan komputer dengan sedikitnya 2 inti prosesor, RAM 4 GB untuk Docker,
dan ruang kosong 10 GB. Penyimpanan 40 GB atau lebih lebih masuk akal untuk
data, foto, dan cadangan. Pemasangan pertama memerlukan internet. Tentukan
alamat jaringan sekolah yang tetap agar perangkat lain tidak kehilangan
alamat Absensa setelah komputer dinyalakan ulang.
Jika memakai Docker Desktop di Windows, komputer Windows memerlukan sedikitnya
8 GB RAM menurut [persyaratan Docker](https://docs.docker.com/desktop/setup/install/windows-install/).

{Gambar: pilihan jalur Windows dengan WSL2, Windows Server dengan VM, dan Linux}

## Windows 11 atau Windows 10: siapkan WSL2

WSL2 menjalankan Linux di Windows. Absensa memakai Linux di dalam WSL2;
`install.ps1` membantu membuka pemasang Linux dari PowerShell.

1. Buka **PowerShell sebagai administrator**. Lihat nama Ubuntu yang tersedia,
   lalu pasang Ubuntu 24.04 jika muncul dalam daftar:

   ```powershell
   wsl --list --online
   wsl --install -d Ubuntu-24.04
   ```

   Ikuti permintaan mulai ulang Windows. Saat Ubuntu pertama kali terbuka,
   buat nama pengguna dan kata sandi Linux. Jika Ubuntu 24.04 tidak ada dalam
   daftar, ikuti [panduan WSL dari Microsoft](https://learn.microsoft.com/windows/wsl/install)
   untuk memilih distribusi yang didukung Absensa.

2. Periksa WSL dan distribusi yang baru dipasang:

   ```powershell
   wsl --version
   wsl --list --verbose
   ```

   Distribusi yang dipilih harus menunjukkan versi **2**. Pemasang Absensa
   memerlukan WSL versi 2.1.5 atau lebih baru. Jika masih versi 1, selesaikan
   [pengaturan WSL](https://learn.microsoft.com/windows/wsl/basic-commands)
   sebelum melanjutkan.

3. Siapkan Docker untuk distribusi itu. Jika memakai Docker Desktop, unduh dan
   pasang dari [situs resmi Docker](https://docs.docker.com/desktop/setup/install/windows-install/),
   jalankan dengan mesin Linux, lalu aktifkan distribusi Ubuntu di **Settings →
   Resources → WSL Integration**. Pilihan lain adalah Docker Engine di dalam
   WSL2. Buka terminal Ubuntu, lalu periksa bahwa `docker info` dan
   `docker compose version` dapat dijalankan. Lihat [panduan integrasi WSL
   dari Docker](https://docs.docker.com/desktop/features/wsl/) jika Docker
   belum terlihat dari terminal Ubuntu.

4. Kembali ke PowerShell. Unduh dan baca pemasang Windows, lalu jalankan:

   ```powershell
   Invoke-WebRequest 'https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1' -OutFile install.ps1
   Get-Content .\install.ps1
   powershell -NoProfile -File .\install.ps1
   ```

   Pemasang menampilkan daftar distribusi WSL. Ketik nama distribusi yang
   tadi Anda periksa. Setelah mengunduh `install.sh` ke WSL, pemasang
   menampilkan lokasi berkasnya dan meminta jawaban **ya** sebelum
   menjalankannya. Lanjutkan dengan [pilihan pemasangan Linux](#pilihan-yang-ditanyakan-pemasang).

Simpan berkas Absensa di lokasi Linux yang ditawarkan pemasang, seperti
`~/absensa`. Folder Windows seperti `/mnt/c` dan OneDrive bukan lokasi
pemasangan yang didukung. Setelah selesai, jalankan perintah `./absensa`
dari terminal distribusi WSL yang sama.

Keberhasilan membuka Absensa di komputer Windows belum membuktikan bahwa
komputer lain di Wi-Fi sekolah dapat membukanya. WSL2 biasanya memakai
jaringan NAT; alamat WSL dapat berubah. Pada Windows 11, mode jaringan
*mirrored* dapat membantu akses dari LAN, tetapi pengaturan jaringan dan
firewall tetap perlu diuji dari perangkat lain. Ikuti [panduan jaringan
WSL dari Microsoft](https://learn.microsoft.com/windows/wsl/networking).
Untuk komputer yang harus melayani sekolah setelah restart tanpa login
pengguna, gunakan VM Linux yang diatur untuk menyala otomatis.

## Windows Server: pasang di VM Linux

Pada Windows Server, gunakan Hyper-V atau pengelola VM sekolah:

1. Pasang peran Hyper-V jika belum tersedia, lalu buat *virtual switch*
   eksternal yang terhubung ke jaringan sekolah. Ikuti [panduan Hyper-V dari
   Microsoft](https://learn.microsoft.com/windows-server/virtualization/hyper-v/get-started/create-a-virtual-switch-for-hyper-v-virtual-machines).
2. Buat VM dari berkas ISO Ubuntu Server 24.04 LTS 64-bit. Sediakan sedikitnya
   2 inti prosesor, 4 GB RAM, dan ruang penyimpanan sesuai kebutuhan di atas.
   Hubungkan VM ke *virtual switch* tadi.
3. Selesaikan pemasangan Ubuntu. Atur alamat LAN VM agar tetap, lalu pastikan
   VM menyala kembali setelah Windows Server dinyalakan ulang.

Masuk ke terminal Ubuntu **di dalam VM**, lalu gunakan [perintah Linux di
bawah](#linux-ubuntu-debian-atau-vm). Semua pilihan pemasangan berikutnya
diisi di terminal VM. Perangkat sekolah nanti membuka alamat VM, bukan
alamat khusus WSL. Pengaturan VM, jaringan, dan startup dilakukan pada
Windows Server sebelum menjalankan pemasang Absensa.

{Gambar: Ubuntu Server berjalan di VM Windows Server dan terhubung ke LAN sekolah}

## Linux: Ubuntu, Debian, atau VM

Buka terminal dengan akun Linux yang akan mengelola Absensa. Unduh dan baca
berkas pemasang sebelum menjalankannya:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh -o install.sh
less install.sh
bash install.sh
```

Jika sekolah sudah meninjau pemasang dan ingin memakai perintah singkat,
perintahnya adalah:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh | bash
```

Jalankan dari terminal yang bisa menerima jawaban. Pemasang memeriksa versi
Linux, arsitektur komputer, paket yang diperlukan, Docker, lalu rilis Absensa.
Jika paket perlu dipasang, ia meminta izin untuk memasangnya. Setelah itu,
isi pilihan berikut sesuai jaringan dan kebijakan sekolah.

## Pilihan yang ditanyakan pemasang

Langkah ini muncul setelah `install.sh` berjalan, baik dari terminal Linux,
WSL2, maupun VM. Ikuti pertanyaan di layar secara berurutan:

1. **Direktori instalasi.** Tekan **Enter** untuk memakai lokasi yang
   ditawarkan, biasanya `~/absensa`, atau masukkan lokasi lain yang masih
   kosong. Gunakan folder di Linux; pada WSL2, jangan pilih `/mnt/c` atau
   OneDrive. Pemasang dapat menanyakan lokasi yang sama sekali lagi sebelum
   pengaturan dimulai. Pertahankan pilihan tadi.
2. **Izin memasang paket.** Jika ada paket atau Docker yang belum tersedia,
   pemasang menampilkan apa yang perlu dipasang dan bertanya **Izinkan
   pemasangan paket dan penggunaan hak administrator?** Jawab **ya** jika
   sekolah sudah menyetujui pemasangan tersebut. Jika Anda menjawab
   **tidak**, pemasang berhenti dan dapat dijalankan lagi setelah paket
   disiapkan.
3. **Pemeriksaan rilis.** Pemasang mencari rilis stabil Absensa dan memeriksa
   berkasnya sebelum melanjutkan. Tahap ini tidak meminta isian. Jika rilis
   tidak ditemukan atau pemeriksaan gagal, baca pesan yang tampil dan coba
   lagi setelah penyebabnya diperbaiki.
4. **Cara mengamankan alamat aplikasi.** Pada pertanyaan **HTTPS**, pilih
   `1` untuk **CA lokal** jika sekolah memakai alamat IP atau nama lokal.
   Pilih `2` jika domain sekolah dikelola di Cloudflare; pemasang akan meminta
   token Cloudflare. Pilih `3` jika sekolah sudah memiliki *reverse proxy*.
   Rincian pilihan `2` dan `3` ada di [panduan HTTPS](https://github.com/u70i1/absensa/blob/main/deploy/README.md#5-https-dan-wi-fi-sekolah).
5. **Nama domain atau IPv4 LAN tetap.** Masukkan alamat yang akan dipakai
   perangkat sekolah, tanpa `https://` dan tanpa garis miring. Untuk CA lokal,
   alamat itu bisa berupa IP tetap di jaringan sekolah, misalnya
   `192.168.1.10`. Pastikan alamat tersebut memang milik komputer atau VM
   yang menjalankan Absensa.
6. **Port HTTPS.** Untuk CA lokal atau Cloudflare, tekan **Enter** untuk
   memakai `443` jika tersedia. Jika port itu sudah dipakai, pilih port
   kosong, misalnya `8443`, lalu sertakan port dalam alamat browser:
   `https://192.168.1.10:8443`. Pada pilihan *reverse proxy*, pemasang
   menawarkan `8443` untuk sambungan di komputer server; alamat yang dibuka
   pengguna mengikuti pengaturan *reverse proxy* sekolah.
7. **Zona waktu.** Pilih `1` untuk WIB, `2` untuk WITA, atau `3` untuk WIT.
   Pilihan ini menentukan batas hari presensi dan waktu yang tampil pada
   catatan. Periksa sebelum melanjutkan karena zona waktu tidak diubah dari
   halaman aplikasi.
8. **Direktori cadangan.** Tekan **Enter** untuk membuat folder `backups`
   yang ditawarkan, atau masukkan lokasi kosong pada disk lain yang sudah
   terpasang. Pemasang akan membuat folder baru di lokasi itu.
9. **Waktu cadangan database/foto.** Tekan **Enter** untuk memakai
   `10:00,17:00`, atau isi satu atau dua waktu dalam bentuk `HH:MM`.
   Waktunya mengikuti zona waktu yang dipilih pada langkah 7.
10. **Jumlah hari cadangan disimpan.** Tekan **Enter** untuk `14` hari, atau
    masukkan jumlah hari yang sesuai dengan ruang penyimpanan sekolah.
11. **Periksa ringkasan.** Pemasang menampilkan lokasi, alamat HTTPS, port,
    dan jadwal cadangan. Jika sudah benar, jawab **ya** pada **Terapkan
    konfigurasi dan unduh image?** Pemasang lalu menyiapkan aplikasi dan
    membuat `recovery.key`, yaitu kunci yang diperlukan untuk pemulihan
    cadangan. Catat lokasi kunci tersebut.
12. **Nyalakan aplikasi.** Jawab **ya** pada **Nyalakan Absensa sekarang?**
    agar database disiapkan dan layanan mulai berjalan. Jika memilih
    **tidak**, buka folder instalasi kemudian jalankan `./absensa mulai`.
    Pertanyaan akun administrator pada langkah 13 akan muncul saat aplikasi
    pertama kali dinyalakan. Cadangan lengkap dapat dibuat kemudian dengan
    `./absensa cadangkan`, dan jadwalnya dengan `./absensa jadwal`.
13. **Buat administrator pertama.** Jawab **ya**, isi nama pengguna, lalu
    masukkan sandi dua kali. Sandi harus sedikitnya 12 karakter dan tidak
    ditampilkan saat diketik. Simpan informasi masuk sesuai aturan sekolah.
14. **Buat cadangan lengkap pertama.** Jawab **ya** agar pemasang membuat
    dan memeriksa cadangan awal. Simpan `recovery.key` di tempat yang
    berbeda dari berkas cadangan.
15. **Jadwalkan cadangan lengkap.** Jika penjadwal `cron` tersedia, pemasang
    menawarkan jadwal harian. Jawab **ya** bila sekolah ingin mengaktifkannya,
    lalu pilih jam dan jumlah arsip yang disimpan. Jika `cron` belum tersedia,
    cadangan database/foto tetap dapat berjalan. Setelah `cron` disiapkan,
    jalankan `./absensa jadwal` dari folder instalasi untuk mengatur cadangan
    lengkap.

## Setelah pemasangan

1. Catat alamat Absensa yang ditampilkan. Buka dari komputer pemasangan,
   lalu coba lagi dari perangkat lain di jaringan sekolah. Jika memakai port
   selain `443`, sertakan port pada alamat.
2. Jika memilih **CA lokal**, pasang sertifikat publik `root-ca.crt` pada
   setiap perangkat yang akan membuka Absensa. Cocokkan sidik jari sertifikat
   yang ditampilkan pemasang. Jangan memindahkan `recovery.key` atau
   `production.env` ke perangkat pengguna. Petunjuk per perangkat ada di
   [panduan HTTPS](https://github.com/u70i1/absensa/blob/main/deploy/README.md#5-https-dan-wi-fi-sekolah).
3. Simpan `recovery.key` di tempat terpisah dari cadangan. Dari terminal Linux
   atau WSL tempat Absensa dipasang, periksa layanan dengan `./absensa status`
   dan `./absensa periksa` dari folder instalasi.
4. Buka **Dashboard admin** dan masuk dengan akun yang dibuat tadi. Setelah
   itu, lanjutkan ke [persiapan data siswa dan perangkat](persiapan.md#menyiapkan-data-siswa).

Pemberitahuan WhatsApp memerlukan pengaturan tersendiri dari halaman admin.
Pemasangan yang berhasil belum berarti nomor WhatsApp sekolah sudah terhubung.
Jika ada pesan kesalahan saat instalasi, baca [panduan pemasangan dan
pemulihan](https://github.com/u70i1/absensa/blob/main/deploy/README.md)
sebelum mengulangnya pada folder yang sama.
