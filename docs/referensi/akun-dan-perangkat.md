# Akun dan perangkat tepercaya

<!-- TODO: Sumber pemeriksaan: admin_auth_service.py, access_auth_service.py, access_management_service.py, login_throttle_service.py, serta halaman akses/masuk. -->

## Peran dan akses fitur

### Administrator

<!-- TODO: Susun cakupan pengelolaan data, akses, dan layanan. Akun admin dibuat/reset melalui prosedur pemasangan; tidak ada pengelolaan daftar admin pada halaman Akses & Perangkat. -->

[Panduan pemasangan terpisah](https://github.com/u70i1/absensa/blob/main/deploy/README.md)

### Operator

<!-- TODO: Susun cakupan pencatatan presensi dan riwayat hari ini. Operator tidak diberi pengelolaan data sekolah, dan tidak memiliki pembatasan kelas individual. VISUAL: tabel perbandingan hak akses yang akan ditulis pemilik. -->

### Perangkat tepercaya

<!-- TODO: Jelaskan akun perangkat sebagai syarat sebelum masuk operator, bukan peran pengelola data. -->

## Masuk dan sesi administrator

<!-- TODO: Jelaskan nama pengguna/kata sandi, keluar, batas percobaan, serta masa sesi yang mengikuti konfigurasi pemasangan (nilai awal 12 jam). -->

## Pengelolaan akun operator

<!-- TODO: Jelaskan nama 1–100 karakter, ID untuk membedakan nama sama, PIN enam digit, status aktif/nonaktif, edit dan hapus. Penggantian PIN atau penonaktifan mengakhiri sesi operator di seluruh perangkat. -->

## Pengelolaan perangkat

### Nama pengguna, kata sandi, dan status

<!-- TODO: Jelaskan nama pengguna tanpa membedakan kapital, keunikan nama, panjang kata sandi 8–1.024 karakter, dan aktif/nonaktif. VISUAL: daftar perangkat tanpa rahasia. -->

### Satu browser untuk setiap akun perangkat

<!-- TODO: Jelaskan pengikatan browser dan bahwa hilangnya cookie tidak membebaskan ikatan di server. -->

### Reset koneksi dan pencabutan akses

<!-- TODO: Jelaskan Reset koneksi, pergantian kata sandi, penonaktifan, dan penghapusan perangkat; sesi operator pada perangkat ikut berakhir. Perubahan nama saja tidak mencabut sesi. -->

## Urutan masuk dan pilihan keluar operator

<!-- TODO: Jelaskan login perangkat lalu operator, sesi operator pada browser, Keluar sebagai operator, serta Keluar dari perangkat pada layar login. Hindari uraian token/API. -->

## Batas percobaan dan penguncian sementara

### Kata sandi administrator dan perangkat

<!-- TODO: Jelaskan anggaran login lima percobaan per akun dan 30 per sumber dalam lima menit, termasuk login yang berhasil, serta waktu tunggu yang ditampilkan. -->

### PIN operator

<!-- TODO: Jelaskan lima kesalahan PIN berurutan mengunci login operator pada perangkat selama lima menit; mengganti pilihan operator tidak melewati batas, dan reset admin dapat membersihkannya. -->

## Terkait

- [Menyiapkan akses dan perangkat](../memulai/administrator/mengatur-akses.md)
- [Masuk dan berganti operator](../memulai/operator/masuk.md)
- [Pemecahan masalah](../memulai/pemecahan-masalah.md)
