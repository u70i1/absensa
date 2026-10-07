$ErrorActionPreference = 'Stop'
$temp = Join-Path ([IO.Path]::GetTempPath()) ('absensa-smoke-logs-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
try {
    $probe = Join-Path $temp 'fake smoke.py'
    @'
import sys
assert sys.argv[1] == "package with spaces"
print("early fixture output", flush=True)
print("early fixture error", file=sys.stderr, flush=True)
sys.exit(7)
'@ | Set-Content -LiteralPath $probe -Encoding ASCII
    $shell = (Get-Process -Id $PID).Path
    $python = (Get-Command python -ErrorAction Stop).Source
    foreach ($expected in @(7,0)) {
        if ($expected -eq 0) {
            (Get-Content -LiteralPath $probe -Raw).Replace('sys.exit(7)', 'sys.exit(0)') | Set-Content -LiteralPath $probe -Encoding ASCII
        }
        $logs = Join-Path $temp "logs $expected"
        & $shell -NoProfile -File (Join-Path $PSScriptRoot 'run-smoke.ps1') -Package 'package with spaces' -LogDirectory $logs -Python $python -SmokeScript $probe
        if ($LASTEXITCODE -ne $expected) { throw "Smoke wrapper lost exit code $expected." }
        if ((Get-Content -LiteralPath (Join-Path $logs 'smoke.stdout.log') -Raw) -notmatch 'early fixture output') { throw 'Missing stdout artifact.' }
        if ((Get-Content -LiteralPath (Join-Path $logs 'smoke.stderr.log') -Raw) -notmatch 'early fixture error') { throw 'Missing stderr artifact.' }
        if ((Get-Content -LiteralPath (Join-Path $logs 'smoke.status.log') -Raw) -notmatch "Exit code: $expected") { throw 'Missing exit status artifact.' }
    }
    # Do not leave the intentionally nonzero fixture status in the calling CI step.
    $global:LASTEXITCODE = 0
    Write-Host 'Smoke logging, paths with spaces, and success/failure exit codes passed.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
