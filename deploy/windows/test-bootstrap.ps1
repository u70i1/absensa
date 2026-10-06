$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
foreach ($file in @((Join-Path $repo 'install.ps1')) + @(Get-ChildItem $PSScriptRoot -Filter '*.ps1' | ForEach-Object FullName)) {
    $tokens = $null; $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($file, [ref]$tokens, [ref]$errors) | Out-Null
    if ($errors.Count) { throw ($errors | Out-String) }
}
. (Join-Path $repo 'install.ps1')
foreach ($build in @(17763,20348,26100)) { Assert-AbsensaPlatform ([PSCustomObject]@{ ProductType=3; BuildNumber=$build }) 'AMD64' $true }
foreach ($case in @(@(1,26100,'AMD64',$true),@(3,14393,'AMD64',$true),@(3,17763,'ARM64',$true),@(3,17763,'AMD64',$false))) {
    $rejected = $false
    try { Assert-AbsensaPlatform ([PSCustomObject]@{ ProductType=$case[0]; BuildNumber=$case[1] }) $case[2] $case[3] } catch { $rejected = $true }
    if (-not $rejected) { throw 'Platform unsupported was accepted.' }
}
$temp = Join-Path ([IO.Path]::GetTempPath()) ('absensa-package-tests-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
try {
    $file = Join-Path $temp 'payload'
    [IO.File]::WriteAllText($file, 'fixture')
    $sum = Join-Path $temp 'SHA256SUMS.windows'
    [IO.File]::WriteAllText($sum, (Get-FileHash $file -Algorithm SHA256).Hash.ToLowerInvariant() + "  payload`n")
    Test-AbsensaChecksum $file $sum 'payload'
    [IO.File]::WriteAllText($file, 'tampered')
    $rejected = $false
    try { Test-AbsensaChecksum $file $sum 'payload' } catch { $rejected = $true }
    if (-not $rejected) { throw 'Tampered bytes accepted.' }
    # Valid extraction must work too: rejection-only tests could pass if all ZIPs fail.
    $archive = Join-Path $temp 'valid release.zip'
    $zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
    try {
        $entry = $zip.CreateEntry('folder with spaces/payload.txt')
        $writer = New-Object IO.StreamWriter($entry.Open())
        try { $writer.Write('verified fixture') } finally { $writer.Dispose() }
    } finally { $zip.Dispose() }
    $destination = Join-Path $temp 'Program Files fixture'
    Expand-AbsensaZip $archive $destination
    if ([IO.File]::ReadAllText((Join-Path $destination 'folder with spaces/payload.txt')) -ne 'verified fixture') {
        throw 'Valid release ZIP did not extract correctly.'
    }
    $rejected = $false
    try { Expand-AbsensaZip $archive $destination } catch { $rejected = $true }
    if (-not $rejected) { throw 'Existing extraction destination was overwritten.' }
    foreach ($name in @('../outside','C:/outside','folder\outside','folder/file:ads','folder/NUL.txt','folder/a.','folder/a ')) {
        $archive = Join-Path $temp ([Guid]::NewGuid().ToString('N') + '.zip')
        $zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
        $zip.CreateEntry($name) | Out-Null
        $zip.Dispose()
        $rejected = $false
        try { Expand-AbsensaZip $archive (Join-Path $temp ([Guid]::NewGuid().ToString('N'))) } catch { $rejected = $true }
        if (-not $rejected) { throw "Unsafe ZIP entry accepted: $name" }
    }
    & (Join-Path $PSScriptRoot 'test-build-source.ps1')
    Write-Host 'Bootstrap syntax, Server build gates, checksum, valid ZIP extraction and unsafe archive tests passed.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
