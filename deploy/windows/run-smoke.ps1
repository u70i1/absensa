# CI-only driver: preserve early failures even when installation never creates logs.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$Package,
    [Parameter(Mandatory=$true)][string]$LogDirectory,
    [string]$Python = (Get-Command python -ErrorAction Stop).Source,
    [string]$SmokeScript = (Join-Path $PSScriptRoot 'smoke.py')
)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$stdout = Join-Path $LogDirectory 'smoke.stdout.log'
$stderr = Join-Path $LogDirectory 'smoke.stderr.log'
$status = Join-Path $LogDirectory 'smoke.status.log'
'Starting native Windows smoke drill.' | Set-Content -LiteralPath $status
# PS 5.1 can treat native stderr in a pipeline as a terminating ErrorRecord.
# Direct file redirection preserves the child's real exit code and both streams.
$process = Start-Process -FilePath $Python -ArgumentList @('-u', "`"$SmokeScript`"", "`"$Package`"") -NoNewWindow -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
"Exit code: $($process.ExitCode)" | Add-Content -LiteralPath $status
Get-Content -LiteralPath $stdout | ForEach-Object { Write-Host "smoke stdout | $_" }
Get-Content -LiteralPath $stderr | ForEach-Object { Write-Host "smoke stderr | $_" }
exit $process.ExitCode
