# Persiapan penggunaan

Sebelum mencatat presensi, sekolah perlu memasang Absensa, menyiapkan data
siswa, dan menentukan perangkat yang akan dipakai. Pekerjaan ini bisa diurus
oleh satu orang atau dibagi sesuai kebutuhan sekolah.

## Memasang Absensa

Sekolah perlu memasang Absensa pada komputer yang akan menjalankan aplikasi.
Untuk Linux, perintah pemasangan singkatnya adalah:

```bash
curl -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh | bash
```

Perintah ini memerlukan berkas pemasang di `main` dan rilis stabil Absensa.
Jika rilis belum tersedia, pemasangan belum dapat diselesaikan.

Pemasang akan meminta beberapa pilihan, termasuk alamat aplikasi dan zona
waktu sekolah. Untuk persyaratan komputer, pilihan Windows, dan langkah
pemasangan yang ada saat ini, baca [panduan pemasangan](https://github.com/u70i1/absensa/blob/main/deploy/README.md).

Ikuti [panduan memasang Absensa](instalasi.md) untuk langkah Windows dengan
WSL2, Windows Server dengan VM Linux, dan pilihan yang ditanyakan pemasang.

Simpan alamat aplikasi serta nama pengguna dan kata sandi administrator yang
dibuat saat pemasangan. Alamat ini akan dipakai untuk membuka Absensa dari
perangkat sekolah.

## Membuka aplikasi

Hubungkan perangkat ke jaringan sekolah, buka browser, lalu masukkan alamat
Absensa yang telah ditetapkan. Halaman awal menampilkan **Buka presensi** dan
**Dashboard admin**. Jika halaman tidak terbuka, periksa alamat dan sambungan
jaringan sekolah.

{Gambar: halaman awal Absensa di browser, tanpa alamat atau data pribadi}

## Menyiapkan data siswa

Data bisa dimasukkan satu per satu atau melalui berkas Excel. Ikuti [panduan
menyiapkan data sekolah](administrator/menyiapkan-data.md) saat memasukkannya.

## Menyiapkan perangkat dan akses presensi

Perangkat didefinisikan oleh perangkat dimana operator bisa masuk. Satu akun
tentunya hanya dapat login dalam satu perangkat. Ketika sebuah perangkat sudah
teridentifikasi dengan akun perangkat, barulah operator dapat login dalam
perangkat tersebut dengan nama dan PIN yang sudah didaftarkan oleh admin.

Mulailah dari [Menyiapkan data sekolah](administrator/menyiapkan-data.md),
lanjutkan ke [Menyiapkan akses dan perangkat](administrator/mengatur-akses.md),
lalu [Masuk sebagai operator](operator/masuk.md).
