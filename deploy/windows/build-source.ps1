# CI-only source download fallback. Trust remains in the pinned vcpkg port.
function Save-AbsensaGperfSource {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory=$true)][string]$VcpkgRoot,
        [scriptblock]$Download = {
            param($Url, $Destination)
            Invoke-WebRequest -UseBasicParsing -Uri $Url -OutFile $Destination -TimeoutSec 45 | Out-Null
        }
    )
    $port = Join-Path $VcpkgRoot 'ports/gperf'
    $metadata = Get-Content -LiteralPath (Join-Path $port 'vcpkg.json') -Raw | ConvertFrom-Json
    $version = $metadata.version
    $portfile = Get-Content -LiteralPath (Join-Path $port 'portfile.cmake') -Raw
    $pins = [regex]::Matches($portfile, 'SHA512\s+([a-fA-F0-9]{128})\b')
    if ($version -notmatch '^\d+\.\d+(\.\d+)?$' -or $pins.Count -ne 1) {
        throw 'Pinned gperf version/SHA512 could not be read. Review the vcpkg baseline before building.'
    }
    $expected = $pins[0].Groups[1].Value.ToLowerInvariant()
    $downloads = Join-Path $VcpkgRoot 'downloads'
    [IO.Directory]::CreateDirectory($downloads) | Out-Null
    $target = Join-Path $downloads "gperf-$version.tar.gz"
    if (Test-Path -LiteralPath $target) {
        if ((Get-FileHash -LiteralPath $target -Algorithm SHA512).Hash.ToLowerInvariant() -ne $expected) {
            throw 'Cached gperf source does not match the pinned SHA512.'
        }
        return
    }
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    foreach ($url in @(
        "https://www.mirrorservice.org/sites/ftp.gnu.org/gnu/gperf/gperf-$version.tar.gz",
        "https://mirrors.kernel.org/gnu/gperf/gperf-$version.tar.gz",
        "https://ftp.gnu.org/gnu/gperf/gperf-$version.tar.gz"
    )) {
        $partial = $target + '.' + [Guid]::NewGuid().ToString('N') + '.partial'
        try {
            Write-Host "Downloading pinned gperf $version from $url..."
            & $Download $url $partial
            if ((Get-FileHash -LiteralPath $partial -Algorithm SHA512).Hash.ToLowerInvariant() -ne $expected) {
                throw 'Source SHA512 does not match the pinned vcpkg port.'
            }
            Move-Item -LiteralPath $partial -Destination $target -ErrorAction Stop
            Write-Host 'gperf source verified; vcpkg will also verify it before compiling.'
            return
        } catch {
            Write-Warning "gperf mirror failed: $url. $($_.Exception.Message)"
        } finally {
            if (Test-Path -LiteralPath $partial) { Remove-Item -LiteralPath $partial -Force }
        }
    }
    throw 'Could not download verified gperf source. Check GNU mirror availability and rerun this build; do not bypass the source checksum.'
}
