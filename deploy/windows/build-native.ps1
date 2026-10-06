# Build native libraries in CI, never on a school's server.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$Output)
$ErrorActionPreference = 'Stop'
$baseline = '434307da09bc05b2c86996dccc8b2351fc0d5d37'
$work = Join-Path $env:RUNNER_TEMP ('absensa-native-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $work | Out-Null
& git clone --no-checkout https://github.com/microsoft/vcpkg.git (Join-Path $work 'vcpkg')
if ($LASTEXITCODE -ne 0) { throw 'vcpkg clone gagal.' }
& git -C (Join-Path $work 'vcpkg') checkout --detach $baseline
if ($LASTEXITCODE -ne 0) { throw 'vcpkg baseline gagal.' }
& (Join-Path $work 'vcpkg\bootstrap-vcpkg.bat') -disableMetrics
if ($LASTEXITCODE -ne 0) { throw 'vcpkg bootstrap gagal.' }
# vcpkg port sources and tools are checked against their recorded SHA512 pins.
& (Join-Path $work 'vcpkg\vcpkg.exe') install --triplet x64-windows --x-manifest-root=$PSScriptRoot --x-install-root="$work\installed"
if ($LASTEXITCODE -ne 0) { throw 'Build cairo/libarchive gagal.' }
New-Item -ItemType Directory -Force -Path $Output | Out-Null
Copy-Item "$work\installed\x64-windows\bin\*.dll" $Output
Copy-Item "$work\installed\x64-windows\share" (Join-Path $Output 'licenses') -Recurse
# App-local MSVC runtime: avoids a global redistributable installation/reboot.
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vs = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
$crt = Get-ChildItem "$vs\VC\Redist\MSVC\*\x64\Microsoft.VC*.CRT" -Directory | Sort-Object FullName -Descending | Select-Object -First 1
if (-not $crt) { throw 'MSVC redistributable tidak ditemukan.' }
Copy-Item (Join-Path $crt.FullName '*.dll') $Output
@{ vcpkg = $baseline; crt = $crt.Parent.Parent.Name; triplet = 'x64-windows' } | ConvertTo-Json | Set-Content -Encoding ASCII (Join-Path $Output 'build.json')
# Match CairoCFFI's Windows loader name without changing business logic.
if (Test-Path (Join-Path $Output 'cairo.dll')) { Copy-Item (Join-Path $Output 'cairo.dll') (Join-Path $Output 'libcairo-2.dll') }
if (Test-Path (Join-Path $Output 'libarchive.dll')) { Copy-Item (Join-Path $Output 'libarchive.dll') (Join-Path $Output 'archive.dll') }
