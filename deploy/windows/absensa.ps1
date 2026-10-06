# Stable launcher: the durable state selects the installed release.
[CmdletBinding()]
param(
    [ValidateSet('status','start','stop','restart','logs','backup','restore','update','admin','repair','activate','uninstall')][string]$Action = 'status',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$Arguments
)
$ErrorActionPreference = 'Stop'
try {
    $location = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'location.json') -Raw | ConvertFrom-Json
    $state = Get-Content -LiteralPath (Join-Path $location.data 'state.json') -Raw | ConvertFrom-Json
    if ($state.version -notmatch '^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$') { throw 'Versi tersimpan tidak sah.' }
    $release = Join-Path $PSScriptRoot "releases\$($state.version)"
    & (Join-Path $release 'python\python.exe') (Join-Path $release 'manage.py') --root $PSScriptRoot --data $location.data $Action @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Operasi belum selesai (kode $LASTEXITCODE). Lihat pesan dan log di atas." }
    if ($Action -eq 'uninstall') {
        $after = Get-Content -LiteralPath (Join-Path $location.data 'state.json') -Raw | ConvertFrom-Json
        if ($after.uninstalled -eq $true) {
            $binaryRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
            $dataRoot = [IO.Path]::GetFullPath($location.data).TrimEnd('\')
            if ($dataRoot -eq $binaryRoot -or $dataRoot.StartsWith($binaryRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Data berada dalam direktori binary. Penghapusan dibatalkan.' }
            if (@(Get-ChildItem -LiteralPath $binaryRoot -Recurse -Force | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }).Count) { throw 'Ada junction/tautan dalam binary. Penghapusan otomatis dibatalkan.' }
            Remove-Item -LiteralPath $binaryRoot -Recurse -Force
            Write-Host "Binary dihapus. Data dan cadangan dipertahankan: $dataRoot"
        }
    }
} catch {
    throw "Absensa: $($_.Exception.Message)"
}
