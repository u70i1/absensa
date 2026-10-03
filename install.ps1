# Absensa: run the shared Linux installer in an existing WSL2 environment.
[CmdletBinding()]
param([string]$Distribution = '')
$ErrorActionPreference = 'Stop'
try {
    $os = Get-CimInstance Win32_OperatingSystem
    $build = [int]$os.BuildNumber
    if ($os.ProductType -ne 1) {
        throw 'Windows Server: gunakan VM Ubuntu Server 24.04 LTS amd64 di hypervisor yang sudah disetujui petugas IT. Docker Desktop tidak didukung. Jalankan install.sh di dalam VM. Installer tidak mengubah Hyper-V, boot, atau jaringan server.'
    }
    if (-not [Environment]::Is64BitOperatingSystem -or $build -lt 19045) {
        throw 'Diperlukan Windows 10 22H2 (19045) atau Windows 11 23H2 (22631+) 64-bit yang masih mendapat pembaruan keamanan. Windows 8/8.1 tidak didukung. Gunakan komputer/VM Linux yang didukung.'
    }
    if ($build -ge 22000 -and $build -lt 22631) {
        throw 'Versi Windows 11 terlalu lama; gunakan Windows 11 23H2 atau lebih baru yang masih didukung.'
    }
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'Rilis Absensa saat ini mendukung amd64. Gunakan server atau VM Linux amd64.'
    }
    if ($build -lt 22000) {
        Write-Host 'Windows 10 memerlukan status dukungan keamanan yang masih berlaku (misalnya ESU yang sesuai). Installer tidak dapat memeriksa langganan ESU.'
        if ((Read-Host 'Apakah petugas IT sudah memastikan Windows dan Docker masih didukung? (ya/tidak)') -ne 'ya') {
            throw 'Gunakan VM/server Ubuntu 24.04 LTS yang didukung.'
        }
    }
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw 'WSL2 belum tersedia. Minta petugas IT mengikuti https://learn.microsoft.com/windows/wsl/install atau menyediakan VM Ubuntu. Perubahan virtualisasi/reboot harus disetujui lebih dahulu.'
    }
    $version = (& wsl.exe --version 2>&1 | Out-String) -replace "`0", ''
    if ($LASTEXITCODE -ne 0 -or $version -notmatch '(\d+)\.(\d+)\.(\d+)') {
        throw 'Versi WSL tidak dapat diperiksa. Minta petugas IT memasang WSL 2.1.5 atau lebih baru.'
    }
    $wslVersion = [version]"$($Matches[1]).$($Matches[2]).$($Matches[3])"
    if ($wslVersion -lt [version]'2.1.5') { throw 'Diperlukan WSL 2.1.5 atau lebih baru.' }
    Write-Host 'Pilih distribusi Ubuntu 22.04/24.04 atau Debian 12/13, bukan docker-desktop.'
    $list = (& wsl.exe --list --verbose 2>&1 | Out-String) -replace "`0", ''
    Write-Host $list
    if (-not $Distribution) { $Distribution = Read-Host 'Nama distribusi WSL yang akan dipakai (contoh Ubuntu-24.04)' }
    if ($Distribution -notmatch '^[A-Za-z0-9._-]+$' -or $Distribution -like 'docker-desktop*') {
        throw 'Nama distribusi tidak sah.'
    }
    $escaped = [regex]::Escape($Distribution)
    if ($list -notmatch "(?m)^\s*\*?\s*$escaped\s+.+\s+2\s*$") { throw 'Distribusi tersebut tidak ditemukan sebagai WSL2. WSL1 tidak didukung.' }
    Write-Host 'Gunakan Docker Desktop dengan integrasi distribusi ini, atau Docker Engine di WSL2. Untuk server sekolah tanpa login pengguna, VM Linux lebih sesuai.'
    Write-Host 'Akses LAN, firewall Windows, dan startup setelah reboot perlu diuji petugas IT. Installer tidak mengubahnya otomatis.'
    # Download first; the exact file is displayed/approved before execution. No iex of a second script.
    & wsl.exe --distribution $Distribution -- bash -lc 'set -e; umask 077; p=$(mktemp /tmp/absensa-install.XXXXXXXX.sh); curl --proto "=https" --proto-redir "=https" -fsSL https://raw.githubusercontent.com/u70i1/absensa/main/install.sh -o "$p"; printf "Installer tersimpan di %s. Baca berkas ini di terminal WSL lain sebelum melanjutkan.\n" "$p"; read -r -p "Jalankan installer yang sudah ditinjau? (ya/tidak): " answer </dev/tty; if [ "$answer" = ya ]; then bash "$p"; else printf "Dibatalkan.\n"; fi'
    if ($LASTEXITCODE -ne 0) { throw 'Installer Linux belum selesai. Periksa pesan di atas, lalu jalankan kembali.' }
} catch {
    Write-Error ("Instalasi Absensa dihentikan. " + $_.Exception.Message)
    exit 1
}
