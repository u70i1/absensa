# Absensa — Aplikasi Presensi Siswa untuk Sekolah

Absensa membantu sekolah mencatat kehadiran siswa, mengelola data siswa dan kelas,
serta memberi tahu orang tua atau wali tentang ketidakhadiran melalui WhatsApp.
Aplikasi dipasang di komputer server sekolah dan dibuka melalui browser pada
perangkat yang terhubung ke jaringan sekolah.

**Baru mengenal Absensa?** Mulai dari [fitur utama](#fitur-utama).
Jika ingin memasangnya di sekolah, pilih [pemasangan sendiri](#instalasi-cepat)
atau [layanan bantuan pemasangan](#layanan-bantuan-pemasangan).

## Untuk siapa?

- **Guru dan petugas presensi:** mencatat kehadiran dengan memindai kartu siswa
  atau mengetik NISN (Nomor Induk Siswa Nasional).
- **Tata usaha dan pengelola sekolah:** menyiapkan data siswa, kelas, kartu,
  serta memeriksa dan mengunduh catatan kehadiran.
- **Petugas IT sekolah:** memasang dan merawat aplikasi, mengatur akses perangkat,
  serta menjaga cadangan data.

Guru dan petugas presensi cukup menggunakan browser setelah aplikasi disiapkan.

## Fitur utama

| Fitur | Manfaat untuk sekolah |
| --- | --- |
| **Presensi siswa** | Catat kehadiran dengan memindai barcode kartu atau memasukkan NISN. |
| **Data siswa dan kelas** | Kelola identitas, foto, kelas, dan nomor WhatsApp orang tua atau wali. |
| **Impor dan ekspor Excel** | Masukkan banyak data sekaligus dan unduh data untuk kebutuhan sekolah. |
| **Kartu siswa** | Cetak atau unduh kartu dengan foto dan barcode untuk presensi. |
| **Log presensi** | Periksa dan unduh catatan kehadiran siswa. |
| **Notifikasi WhatsApp** | Kirim pemberitahuan kepada wali siswa yang belum tercatat hadir, sesuai pengaturan sekolah. |
| **Akun dan perangkat** | Atur siapa yang bertugas dan perangkat yang boleh mencatat presensi. |
| **Cadangan data** | Buat dan simpan salinan data agar tersedia saat diperlukan untuk pemulihan. |

Presensi melalui jaringan lokal sekolah dapat digunakan tanpa internet setelah
pemasangan selesai. Pemasangan awal dan layanan WhatsApp memerlukan internet.

## Instalasi cepat

Pemasangan dilakukan **sekali pada komputer server sekolah** oleh petugas IT.
Setelah itu, guru membuka alamat aplikasi yang diberikan petugas tersebut.
Jika sekolah membutuhkan bantuan, gunakan [layanan bantuan pemasangan](#layanan-bantuan-pemasangan).

Pilih sesuai sistem operasi server. Installer memerlukan rilis stabil dengan
paket untuk sistem operasi tersebut; rincian persiapan ada di
[panduan instalasi lengkap](deploy/README.md).

### Windows Server

Untuk **Windows Server 2022 atau 2025, 64-bit (amd64)**. Buka
**Windows PowerShell 64-bit sebagai Administrator**, lalu jalankan:

```powershell
irm https://raw.githubusercontent.com/u70i1/absensa/main/install.ps1 | iex
```

Ikuti pertanyaan yang muncul untuk menyiapkan alamat aplikasi dan akun
administrator pertama. Lihat [panduan Windows Server](deploy/windows/README.md)
untuk persyaratan dan langkah lengkap. Windows Server 2019 masih memerlukan
[pengujian pada mesin sekolah](deploy/windows/VALIDATION.md) sebelum digunakan.

### Linux

Untuk **Ubuntu Server 22.04/24.04 LTS atau Debian 12/13, 64-bit (amd64)**.
Buka terminal, unduh installer, periksa isinya, lalu jalankan:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh -o install.sh
less install.sh
bash install.sh
```

Tekan **q** untuk keluar setelah membaca installer, lalu jalankan perintah terakhir.
Ikuti pertanyaan yang muncul. Lihat [panduan Linux](deploy/README.md)
untuk persyaratan komputer dan pengaturan jaringan.

### Setelah terpasang

1. Buka alamat **HTTPS** yang ditampilkan installer dan masuk sebagai administrator.
2. Siapkan data siswa dan kelas, lalu buat akun petugas serta daftarkan perangkat presensi.
3. Siapkan kartu siswa jika diperlukan dan hubungkan WhatsApp jika akan digunakan.
4. Coba pencatatan presensi dari perangkat sekolah dan simpan cadangan data.

## Layanan bantuan pemasangan

**Sekolah dapat meminta bantuan pemasangan Absensa** dengan mengirim email ke
[kontakabsensa@gmail.com](mailto:kontakabsensa@gmail.com).

Gunakan subjek **Permintaan Pemasangan Absensa**. Sertakan nama sekolah,
kota/kabupaten, nama dan nomor kontak penanggung jawab, serta keterangan singkat
komputer yang tersedia. Jika belum tahu spesifikasi komputer atau kebutuhan
pemasangannya, cukup ceritakan kondisi sekolah agar dapat dibahas melalui email.

## Dokumentasi lengkap

Buka **[Dokumentasi Absensa](https://u70i1.github.io/absensa/)** untuk menemukan
panduan pemasangan dan penggunaan sesuai tugas di sekolah. Sebagian panduan
penggunaan masih dalam penyusunan; petunjuk pemasangan tersedia.

| Kebutuhan | Buka panduan |
| --- | --- |
| Memasang aplikasi di sekolah | [Panduan pemasangan](https://u70i1.github.io/absensa/memulai/instalasi/) |
| Pemasangan dan pemeliharaan oleh petugas IT | [Panduan teknis instalasi](deploy/README.md) |
| Menyimpan cadangan ke USB atau disk eksternal | [Panduan cadangan untuk petugas sekolah](deploy/PANDUAN-CADANGAN.md) |
| Menjalankan aplikasi untuk pengembangan | [Panduan pengembangan lokal](RUNNING.md) |
| Mempelajari kode dan berkontribusi | [Catatan teknis](DEVELOPMENT.md) · [Rencana pengembangan](ROADMAP.md) |
