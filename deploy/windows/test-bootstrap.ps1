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
    foreach ($name in @('../outside','C:/outside','folder\outside','folder/file:ads','folder/NUL.txt','folder/a.','folder/a ')) {
        $archive = Join-Path $temp ([Guid]::NewGuid().ToString('N') + '.zip')
        $zip = [IO.Compression.ZipFile]::Open($archive, [IO.Compression.ZipArchiveMode]::Create)
        $zip.CreateEntry($name) | Out-Null
        $zip.Dispose()
        $rejected = $false
        try { Expand-AbsensaZip $archive (Join-Path $temp ([Guid]::NewGuid().ToString('N'))) } catch { $rejected = $true }
        if (-not $rejected) { throw "Unsafe ZIP entry accepted: $name" }
    }
    Write-Host 'Bootstrap syntax, Server build gates, checksum and unsafe archive tests passed.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
