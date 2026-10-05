# Impor dan ekspor data

<!-- TODO: Nyatakan bahwa impor/ekspor data sekolah dilakukan administrator. Sumber pemeriksaan: admin_import.py, import_service.py, import_archive_service.py, export_service.py, dan admin_selection.py. -->

## Templat dan hasil ekspor

### Workbook gabungan siswa dan kelas

<!-- TODO: Jelaskan lembar instructions, students, classes, kolom wajib, serta lembar petunjuk yang sudah tersedia dalam workbook. VISUAL: struktur workbook dari unduhan aplikasi. -->

### Identitas tetap dan kelas baru

<!-- TODO: Jelaskan ID siswa/kelas yang harus dipertahankan, ID KELAS pada siswa, slot N1–N100 untuk kelas baru, serta kolom jenjang/nama kelas yang berupa rumus. Nilai sementara berlaku dalam workbook masing-masing. -->

### NISN, nomor wali, dan status

<!-- TODO: Jelaskan pengisian sebagai teks untuk mempertahankan nol di depan, format nomor, serta validasi status sesuai templat aktual. Contoh isian akan dibuat pemilik setelah memeriksa template. -->

## Format dan batas file impor

### File Excel

<!-- TODO: Jelaskan .xlsx maksimal 10 MiB dan batas keseluruhan 10.000 baris; jangan menambahkan dukungan CSV. -->

### Arsip beberapa workbook

<!-- TODO: Jelaskan ZIP, RAR, 7z, TAR, TAR.GZ/TGZ, TAR.BZ2/TBZ2, TAR.XZ/TXZ; batas unggahan 100 MiB, 100 workbook, dan batas isi yang diperiksa. Arsip terenkripsi/tautan tidak diterima. -->

### Foto dalam folder photos/

<!-- TODO: Jelaskan workbook di akar arsip, satu folder pembungkus opsional, penamaan foto menurut NISN sepuluh digit, format/batas foto, kecocokan terhadap baris siswa, serta foto lama yang dipertahankan bila tidak ada penggantinya. VISUAL: ilustrasi susunan folder, tanpa file atau data fiktif. -->

## Pratinjau dan koreksi sebelum menyimpan

### Data baru, perubahan, dan baris yang tidak berubah

<!-- TODO: Jelaskan tabel penambahan/perubahan, warna penanda, sumber file, foto yang disiapkan, serta baris tanpa perubahan yang dilewati. VISUAL: pratinjau nyata yang disamarkan. -->

### Membaca kesalahan dan mengedit draf

<!-- TODO: Jelaskan lokasi file/lembar/baris/kolom, edit baris di pratinjau, dan periksa ulang. Jangan menganggap setiap kesalahan file dapat diperbaiki melalui draf. -->

### Membatalkan, mengonfirmasi, dan masa berlaku

<!-- TODO: Jelaskan satu jam masa pratinjau, kepemilikan pada admin pengunggah, pemeriksaan perubahan data sejak pratinjau, sekali penerapan, dan tidak tersimpannya perubahan saat dibatalkan. -->

## Aturan penerapan data

<!-- TODO: Jelaskan penerapan seluruh unggahan sekaligus, penolakan bila ada kesalahan, pencocokan kelas yang sama, konflik data antarworkbook, dan tidak adanya penghapusan lewat baris yang dihilangkan. Siswa baru perlu ID kelas; siswa yang sudah ada dapat menjadi tanpa kelas. -->

## Cakupan ekspor

### Siswa berdasarkan filter atau pilihan

<!-- TODO: Jelaskan ekspor semua hasil filter dan ekspor pilihan; seluruh kelas tetap disertakan dalam workbook. Foto tidak dibundel pada ekspor spreadsheet. -->

### Siswa dari kelas terpilih

<!-- TODO: Jelaskan hasil ekspor kelas terpilih sebagai siswa kelas tersebut dengan workbook gabungan. -->

### Log presensi harian

<!-- TODO: Jelaskan workbook log sesuai tanggal/pencarian nama, urutan/kolom dari generator aktual, dan bahwa file log bukan templat impor siswa/kelas. -->

## Terkait

- [Menyiapkan data sekolah](../memulai/administrator/menyiapkan-data.md)
- [Siswa](siswa.md)
- [Kelas](kelas.md)
- [Log presensi](log-presensi.md)
