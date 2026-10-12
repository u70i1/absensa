# Absensa v1.1.1

Rilis perbaikan instalasi dan pemulihan Windows. Jalur Linux, format konfigurasi,
PostgreSQL mayor 18, dan skema database tetap kompatibel; tidak ada migrasi baru.
Tag serta artefak rilis sebelumnya tidak diubah.

## Perbaikan

- Probe HTTPS untuk IPv4 menghubungi alamat yang dikonfigurasi, sehingga Caddy
  `tls internal` dapat memilih sertifikat IP tanpa SNI. Probe DNS tetap menuju
  loopback. Verifikasi CA, nama/IP sertifikat, dan TLS tetap wajib.
- Finalisasi mempertahankan jurnal sampai migrasi, health check, ekspor CA lokal,
  dan pengaturan startup otomatis berhasil. Kegagalan tetap menghentikan aplikasi
  dan dapat dilanjutkan dengan `repair` tanpa membuat ulang data sekolah.
- Bootstrap v1.1.1 dengan `-Version v1.1.1` dapat memulihkan instalasi v1.1.0 yang
  belum initialized dan masih pada transaksi `install`, setelah verifikasi paket.
  Pengecualian ini tidak berlaku pada migrasi/restore terhenti atau instalasi sehat.
- `admin` tersedia setelah repair berhasil, memakai validasi dan hash aplikasi,
  dan mempertahankan akun yang sudah ada. Instalasi baru tetap menawarkan akun pertama.
- Diagnostik menyebut komponen, alamat/port, exception tersamarkan, percobaan dan
  waktu berlalu. `status` membantu pemeriksaan instalasi belum selesai; kegagalan
  tetap tercatat setelah layanan dihentikan.
- Respons SCM 1060 ketika memeriksa layanan yang belum terpasang dan 1062 ketika
  menghentikan layanan yang sudah berhenti tidak lagi dicatat sebagai error.
- Interrupt penghentian layanan ditangani tanpa traceback yang menyesatkan;
  exception lain dan exit abnormal tetap dilaporkan.
- JSON UTF-8 dengan BOM diterima. JSON/encoding/field/jurnal yang rusak menghasilkan
  pesan pemulihan yang jelas; penulisan tetap atomik dan rahasia tidak dibuat ulang.
- Diagnostik LAN meliputi IPv4 aktif (termasuk Hyper-V), DNS, DHCP, dan profil
  firewall. Tidak ada perubahan adapter, firewall, DNS, atau trust store otomatis
  oleh pemeriksaan ini. Panduan menjelaskan IP tetap, distribusi CA dan akses klien.

## Pemakaian dan validasi

Ikuti [panduan Windows](https://github.com/u70i1/absensa/blob/v1.1.1/deploy/windows/README.md)
dan [catatan validasi](https://github.com/u70i1/absensa/blob/v1.1.1/deploy/windows/VALIDATION.md).
Setelah repair berhasil, buat administrator pertama melalui PowerShell Administrator:

```powershell
& 'C:\Program Files\Absensa\absensa.ps1' admin
```

Uji lokal mencakup Caddy nyata, penolakan CA/nama sertifikat yang salah, transaksi,
SCM simulasi, JSON/BOM, dan bootstrap/password hash aplikasi dengan PostgreSQL nyata.
Pengujian lokal Linux **tidak membuktikan kompatibilitas Windows Server 2019**.
Build paket Windows dan smoke test native 2022/2025 harus diulang untuk commit ini.
Server 2019 tetap memerlukan instalasi IPv4 tetap dengan port 8443, repair,
login dashboard dari LAN, stop/start dan reboot tanpa login, serta uji runtime
PostgreSQL/Chromium pada mesin asli. Bukti CI rilis sebelumnya bukan bukti v1.1.1.

Versi ini baru disiapkan; belum ditag, dipush, atau diterbitkan. Bootstrap hanya
menerima rilis stabil lengkap yang telah diterbitkan, bukan draft.
Artefak tetap `absensa-linux-amd64.tar.gz`, `absensa-windows-amd64.zip`, `install.ps1`,
`SHA256SUMS`, `SHA256SUMS.windows`, `provenance.jsonl`, `provenance-windows.jsonl`.
