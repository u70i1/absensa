$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build-source.ps1')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('absensa-source-tests-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
try {
    $port = Join-Path $temp 'ports/gperf'
    [IO.Directory]::CreateDirectory($port) | Out-Null
    $fixture = Join-Path $temp 'source.fixture'
    [IO.File]::WriteAllText($fixture, 'pinned source fixture')
    $hash = (Get-FileHash -LiteralPath $fixture -Algorithm SHA512).Hash.ToLowerInvariant()
    [IO.File]::WriteAllText((Join-Path $port 'vcpkg.json'), '{"version":"3.3"}')
    [IO.File]::WriteAllText((Join-Path $port 'portfile.cmake'), 'SHA512 ' + $hash)
    $attempts = New-Object 'System.Collections.Generic.List[string]'
    $download = {
        param($Url, $Destination)
        $attempts.Add($Url)
        if ($attempts.Count -eq 1) { throw 'Simulated primary mirror timeout' }
        [IO.File]::Copy($fixture, $Destination)
    }.GetNewClosure()
    Save-AbsensaGperfSource -VcpkgRoot $temp -Download $download
    $target = Join-Path $temp 'downloads/gperf-3.3.tar.gz'
    if ($attempts.Count -ne 2 -or (Get-FileHash -LiteralPath $target -Algorithm SHA512).Hash.ToLowerInvariant() -ne $hash) {
        throw 'Mirror fallback did not preserve the pinned source hash.'
    }
    Save-AbsensaGperfSource -VcpkgRoot $temp -Download { throw 'Verified cache must not be downloaded again' }
    [IO.File]::WriteAllText($target, 'tampered cache')
    $rejected = $false
    try { Save-AbsensaGperfSource -VcpkgRoot $temp -Download $download } catch { $rejected = $true }
    if (-not $rejected) { throw 'Tampered cached source was accepted.' }
    Remove-Item -LiteralPath $target
    $rejected = $false
    try {
        Save-AbsensaGperfSource -VcpkgRoot $temp -Download {
            param($Url, $Destination)
            [IO.File]::WriteAllText($Destination, 'tampered mirror response')
        }
    } catch { $rejected = $true }
    if (-not $rejected -or (Test-Path -LiteralPath $target) -or @(Get-ChildItem (Join-Path $temp 'downloads') -Filter '*.partial').Count) {
        throw 'Invalid mirror bytes were cached or not cleaned up.'
    }
    Write-Host 'Build source mirror fallback, verified cache and SHA512 tamper tests passed.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
