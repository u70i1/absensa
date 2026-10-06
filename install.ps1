# Absensa native Windows Server bootstrap. PowerShell 5.1; payload comes from one stable release.
[CmdletBinding()]
param([string]$Version = '', [string]$DownloadOnly = '')
$ErrorActionPreference = 'Stop'

function Assert-AbsensaPlatform {
    param($OperatingSystem, [string]$Architecture, [bool]$Administrator)
    if ($OperatingSystem.ProductType -eq 1 -or [int]$OperatingSystem.BuildNumber -notin @(17763,20348,26100) -or $Architecture -ne 'AMD64' -or -not [Environment]::Is64BitProcess) {
        throw 'Diperlukan Windows Server 2019, 2022, atau 2025 amd64 dan Windows PowerShell 64-bit. Windows desktop tidak didukung installer native ini.'
    }
    if (-not $Administrator) { throw 'Klik kanan Windows PowerShell, pilih Run as administrator, lalu jalankan perintah pemasangan kembali.' }
}

function Protect-AbsensaDirectory {
    param([string]$Path)
    $full = [IO.Path]::GetFullPath($Path)
    $parent = $full
    while ($parent) {
        if ((Test-Path -LiteralPath $parent) -and ((Get-Item -LiteralPath $parent).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'Direktori instalasi tidak boleh melewati tautan/junction.' }
        $parent = [IO.Path]::GetDirectoryName($parent)
    }
    [IO.Directory]::CreateDirectory($full) | Out-Null
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    foreach ($id in @('S-1-5-18', 'S-1-5-32-544')) {
        $sid = New-Object Security.Principal.SecurityIdentifier($id)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow')
        $acl.AddAccessRule($rule)
    }
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    Set-Acl -LiteralPath $full -AclObject $acl
}

function Get-AbsensaFile {
    param([string]$Url, [string]$Destination)
    if (-not $Url.StartsWith('https://')) { throw 'Unduhan harus HTTPS.' }
    # HttpClient forbids HTTPS -> HTTP redirects even on PowerShell 5.1/.NET Framework.
    Add-Type -AssemblyName System.Net.Http
    $handler = New-Object Net.Http.HttpClientHandler
    $handler.AllowAutoRedirect = $false
    $client = New-Object Net.Http.HttpClient($handler)
    $client.Timeout = [TimeSpan]::FromMinutes(30)
    $client.DefaultRequestHeaders.UserAgent.ParseAdd('Absensa-Windows-Installer')
    try {
        for ($redirect = 0; $redirect -lt 10; $redirect++) {
            $response = $client.GetAsync($Url, [Net.Http.HttpCompletionOption]::ResponseHeadersRead).GetAwaiter().GetResult()
            if ([int]$response.StatusCode -in @(301,302,303,307,308)) {
                $next = New-Object Uri([Uri]$Url, $response.Headers.Location)
                $response.Dispose()
                if ($next.Scheme -ne 'https') { throw 'Pengalihan unduhan bukan HTTPS.' }
                $Url = $next.AbsoluteUri
                continue
            }
            $response.EnsureSuccessStatusCode() | Out-Null
            $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $file = [IO.File]::Open($Destination, [IO.FileMode]::CreateNew)
            try {
                $buffer = New-Object byte[] 1048576
                [long]$total = 0
                while (($count = $stream.Read($buffer,0,$buffer.Length)) -gt 0) {
                    $total += $count
                    if ($total -gt 2147483648) { throw 'Unduhan melebihi batas 2 GiB.' }
                    $file.Write($buffer,0,$count)
                }
                $file.Flush($true)
            } finally { $file.Dispose(); $stream.Dispose(); $response.Dispose() }
            return
        }
        throw 'Terlalu banyak pengalihan unduhan.'
    } finally { $client.Dispose(); $handler.Dispose() }
}

function Expand-AbsensaZip {
    param([string]$Archive, [string]$Destination)
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        $seen = New-Object 'System.Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
        [long]$size = 0
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName
            $parts = $name.TrimEnd('/').Split('/')
            $size += $entry.Length
            if ($name.StartsWith('/') -or $name.Contains('\') -or $name.Contains(':') -or $parts.Count -eq 0 -or -not $seen.Add($name.TrimEnd('/')) -or $size -gt 6442450944 -or $seen.Count -gt 150000 -or (($entry.ExternalAttributes -shr 16) -band 61440) -eq 40960) { throw 'Arsip rilis tidak aman.' }
            foreach ($part in $parts) {
                if (-not $part -or $part -in @('.','..') -or $part -match '[\x00-\x1f<>"|?*]' -or $part.EndsWith('.') -or $part.EndsWith(' ') -or $part -match '^(?i:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\.|$)') { throw 'Nama berkas arsip tidak aman.' }
            }
        }
        # New destination, validated complete inventory, no overwrite or reparse points.
        if (Test-Path -LiteralPath $Destination) { throw 'Tujuan ekstraksi harus baru.' }
        [IO.Directory]::CreateDirectory($Destination) | Out-Null
        foreach ($entry in $zip.Entries) {
            $path = Join-Path $Destination $entry.FullName
            if ($entry.FullName.EndsWith('/')) { [IO.Directory]::CreateDirectory($path) | Out-Null; continue }
            [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($path)) | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $path, $false)
        }
    } finally { $zip.Dispose() }
}

function Test-AbsensaChecksum {
    param([string]$Archive, [string]$ChecksumFile, [string]$Name)
    $matchesFound = @(Get-Content -LiteralPath $ChecksumFile | Where-Object { $_ -match ('^[a-f0-9]{64}  ' + [regex]::Escape($Name) + '$') })
    if ($matchesFound.Count -ne 1 -or (Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $matchesFound[0].Substring(0,64)) { throw 'SHA-256 rilis tidak cocok. Tidak ada kode unduhan yang dijalankan.' }
}

function Install-AbsensaRelease {
    param([string]$RequestedVersion, [string]$DownloadDirectory)
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
    Assert-AbsensaPlatform (Get-CimInstance Win32_OperatingSystem) $env:PROCESSOR_ARCHITECTURE $admin
    $root = Join-Path $env:ProgramFiles 'Absensa'
    $data = Join-Path $env:ProgramData 'Absensa'
    $recoverBinary = $false
    if (-not $DownloadDirectory -and (Test-Path -LiteralPath (Join-Path $data 'state.json'))) {
        $saved = Get-Content -LiteralPath (Join-Path $data 'state.json') -Raw | ConvertFrom-Json
        if ($saved.format -ne 1 -or $saved.root -ne $root -or $saved.data -ne $data -or $saved.version -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw 'Identitas instalasi tidak sah. Pulihkan state.json asli.' }
        $launcher = Join-Path $root 'absensa.ps1'
        $manager = Join-Path $root "releases\$($saved.version)\manage.py"
        if ((Test-Path -LiteralPath $launcher) -and (Test-Path -LiteralPath $manager) -and $saved.uninstalled -ne $true) {
            Write-Host 'Instalasi ditemukan. Memeriksa/memperbaiki versi yang tersimpan...'
            & $launcher repair
            & $launcher admin
            return
        }
        # Reinstall binaries at the recorded version; no implicit upgrade/secret rotation.
        $RequestedVersion = $saved.version
        $recoverBinary = $true
        Write-Host "Memulihkan binary versi tersimpan $RequestedVersion. Data sekolah dipertahankan."
    }
    if (-not $DownloadDirectory) {
        if (-not $recoverBinary) {
            foreach ($path in @($root,$data)) {
                if ((Test-Path -LiteralPath $path) -and @(Get-ChildItem -LiteralPath $path -Force | Where-Object Name -notin @('bootstrap','logs','config','operation.lock')).Count -gt 0) { throw "Direktori $path sudah berisi data tanpa state yang sah. Data tidak ditimpa; lihat panduan pemulihan." }
            }
        }
        if (-not $recoverBinary) {
            Protect-AbsensaDirectory $root
            Protect-AbsensaDirectory $data
        } else {
            if (-not (Test-Path -LiteralPath $root)) { Protect-AbsensaDirectory $root }
        }
        foreach ($folder in @('logs','config','bootstrap')) {
            $folderPath = Join-Path $data $folder
            if (-not (Test-Path -LiteralPath $folderPath)) { Protect-AbsensaDirectory $folderPath }
        }
        $DownloadDirectory = Join-Path $data ('bootstrap\' + [Guid]::NewGuid().ToString('N'))
        $install = $true
    } else { $install = $false }
    Protect-AbsensaDirectory $DownloadDirectory
    $log = Join-Path $DownloadDirectory 'bootstrap.log'
    Start-Transcript -LiteralPath $log | Out-Null
    try {
        if ($RequestedVersion -and $RequestedVersion -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw 'Tag rilis tidak sah.' }
        $endpoint = if ($RequestedVersion) { "tags/$RequestedVersion" } else { 'latest' }
        Get-AbsensaFile "https://api.github.com/repos/u70i1/absensa/releases/$endpoint" (Join-Path $DownloadDirectory 'release-api.json')
        $metadata = Get-Content -LiteralPath (Join-Path $DownloadDirectory 'release-api.json') -Raw | ConvertFrom-Json
        $tag = $metadata.tag_name
        if ($metadata.draft -ne $false -or $metadata.prerelease -ne $false -or $tag -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$' -or ($RequestedVersion -and $tag -ne $RequestedVersion)) { throw 'Rilis stabil lengkap belum tersedia.' }
        $names = @('absensa-windows-amd64.zip','SHA256SUMS.windows','provenance-windows.jsonl')
        foreach ($name in $names) { if (@($metadata.assets | Where-Object name -eq $name).Count -ne 1) { throw "Rilis $tag belum memuat $name. Hubungi pengelola rilis." } }
        Write-Host "Mengunduh Absensa $tag untuk Windows Server amd64..."
        foreach ($name in $names) { Get-AbsensaFile "https://github.com/u70i1/absensa/releases/download/$tag/$name" (Join-Path $DownloadDirectory $name) }
        $archive = Join-Path $DownloadDirectory $names[0]
        Test-AbsensaChecksum $archive (Join-Path $DownloadDirectory 'SHA256SUMS.windows') $names[0]
        # Bootstrapped verifier is pinned independently from the untrusted release.
        $ghZip = Join-Path $DownloadDirectory 'gh.zip'
        Get-AbsensaFile 'https://github.com/cli/cli/releases/download/v2.102.0/gh_2.102.0_windows_amd64.zip' $ghZip
        if ((Get-FileHash -LiteralPath $ghZip -Algorithm SHA256).Hash.ToLowerInvariant() -ne 'ae64e556ecc240b200f7eba60d550e4bb60d78e860e69dd88c449405b86067f4') { throw 'Checksum GitHub CLI tidak cocok.' }
        Expand-AbsensaZip $ghZip (Join-Path $DownloadDirectory 'verifier')
        $gh = @(Get-ChildItem -LiteralPath (Join-Path $DownloadDirectory 'verifier') -Filter gh.exe -Recurse)
        if ($gh.Count -ne 1) { throw 'Paket verifier tidak sah.' }
        Write-Host 'Memverifikasi asal rilis GitHub/Sigstore...'
        & $gh[0].FullName attestation verify $archive --bundle (Join-Path $DownloadDirectory 'provenance-windows.jsonl') --repo u70i1/absensa --hostname github.com --cert-identity "https://github.com/u70i1/absensa/.github/workflows/release.yml@refs/tags/$tag" --source-ref "refs/tags/$tag" --deny-self-hosted-runners
        if ($LASTEXITCODE -ne 0) { throw 'Bukti asal rilis gagal. Periksa koneksi dan jam server; jangan lewati verifikasi.' }
        $payload = Join-Path $DownloadDirectory 'release'
        Expand-AbsensaZip $archive $payload
        $manifest = Get-Content -LiteralPath (Join-Path $payload 'release.json') -Raw | ConvertFrom-Json
        if ($manifest.version -ne $tag -or $manifest.format -ne 1 -or $manifest.platform -ne 'windows' -or $manifest.architecture -ne 'amd64') { throw 'Manifest tidak cocok dengan rilis yang diminta.' }
        if ($install) {
            & (Join-Path $payload 'python\python.exe') (Join-Path $payload 'manage.py') --root $root --data $data --source $payload install
            if ($LASTEXITCODE -ne 0) { throw "Instalasi belum selesai. Data dipertahankan. Jalankan installer kembali; log: $data\logs." }
        }
    } catch { throw "Absensa: $($_.Exception.Message) Log bootstrap: $log" }
    finally { Stop-Transcript | Out-Null }
}

# Dot-sourcing exposes pure validation functions for tests without changing the machine.
if ($MyInvocation.InvocationName -ne '.') { Install-AbsensaRelease $Version $DownloadOnly }
