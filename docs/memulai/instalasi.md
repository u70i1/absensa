# Memasang Absensa

## Windows Server

Buka **Windows PowerShell 64-bit sebagai Administrator**, lalu jalankan:

```powershell
irm https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1 | iex
```

Installer native menargetkan Windows Server 2019, 2022, dan 2025 amd64. Ia
mengunduh rilis stabil terverifikasi, memasang runtime dan layanan, menyiapkan
database, menjalankan migrasi, lalu menampilkan alamat HTTPS sekolah. Tidak perlu
Git, WSL, Docker Desktop, atau VM. Sediakan IP LAN tetap dan RAM 8 GB.

Binary disimpan di `C:\Program Files\Absensa`; data, foto, konfigurasi, cadangan,
dan log di `C:\ProgramData\Absensa`. Ikuti pertanyaan installer untuk nama DNS/IP,
port HTTPS, sertifikat, dan admin pertama. Jika memakai CA lokal, pasang sertifikat
publik yang ditampilkan pada perangkat sekolah.

Periksa layanan dan versi terpasang:

```powershell
& 'C:\Program Files\Absensa\absensa.ps1' status
```

[Petunjuk lengkap Windows dan pemeliharaan](https://github.com/u70i1/absensa/blob/main/deploy/windows/README.md)
memuat backup, restore, update, log, firewall dan uninstall.
[Status pengujian Windows](https://github.com/u70i1/absensa/blob/main/deploy/windows/VALIDATION.md)
mencatat uji CI native yang lulus pada 2022/2025. Server 2019 diterima installer,
tetapi belum tervalidasi saat runtime; uji mesin nyata diperlukan sebelum produksi.
Paket Windows mulai tersedia pada v1.1.0 setelah rilis stabil diterbitkan.
Rilis v1.0.0 hanya menyediakan paket Linux.

## Linux

Untuk Ubuntu/Debian amd64 yang didukung, buka terminal dan jalankan:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh | bash
```

Ikuti [panduan deployment Linux](https://github.com/u70i1/absensa/blob/main/deploy/README.md).
Linux tetap menggunakan Docker/Compose dan artefak rilis terverifikasi.

## Setelah pemasangan

Buka URL HTTPS yang dicetak installer, masuk sebagai administrator, siapkan data
siswa/kelas, lalu buat akses operator dan perangkat. Hubungkan WhatsApp dari menu
WhatsApp jika digunakan. Uji akses dari perangkat LAN sekolah dan buat cadangan
sebelum mulai operasional.
