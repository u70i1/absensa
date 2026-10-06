$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'build-libraries.ps1')
$temp = Join-Path ([IO.Path]::GetTempPath()) ('absensa-dll-tests-' + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($temp) | Out-Null
try {
    # Fixture bytes test file naming/copying; actual DLL loading is a Windows CI gate.
    foreach ($cairo in @('cairo-2.dll','cairo.dll','libcairo-2.dll')) {
        foreach ($archive in @('archive.dll','libarchive.dll')) {
            $directory = Join-Path $temp ([Guid]::NewGuid().ToString('N') + ' with spaces')
            [IO.Directory]::CreateDirectory($directory) | Out-Null
            [IO.File]::WriteAllText((Join-Path $directory $cairo), 'Cairo fixture bytes')
            [IO.File]::WriteAllText((Join-Path $directory $archive), 'Archive fixture bytes')
            $mapping = Set-AbsensaLibraryAliases -Directory $directory
            if ($mapping['libcairo-2.dll'] -ne $cairo -or $mapping['archive.dll'] -ne $archive) {
                throw 'Native DLL alias mapping was not recorded correctly.'
            }
            if ([IO.File]::ReadAllText((Join-Path $directory 'libcairo-2.dll')) -ne 'Cairo fixture bytes' -or
                [IO.File]::ReadAllText((Join-Path $directory 'archive.dll')) -ne 'Archive fixture bytes' -or
                -not (Test-Path -LiteralPath (Join-Path $directory $cairo))) {
                throw 'Native DLL alias copy changed bytes or removed the upstream filename.'
            }
            $null = Set-AbsensaLibraryAliases -Directory $directory
        }
    }
    $directory = Join-Path $temp 'wrong library'
    [IO.Directory]::CreateDirectory($directory) | Out-Null
    [IO.File]::WriteAllText((Join-Path $directory 'cairo-gobject-2.dll'), 'not Cairo')
    [IO.File]::WriteAllText((Join-Path $directory 'archive.dll'), 'Archive fixture bytes')
    $rejected = $false
    try { $null = Set-AbsensaLibraryAliases -Directory $directory } catch {
        $rejected = $_.Exception.Message -match 'libcairo-2.dll.*cairo-gobject-2.dll'
    }
    if (-not $rejected) { throw 'Missing Cairo was accepted or its diagnostic omitted available DLLs.' }
    [IO.File]::WriteAllText((Join-Path $directory 'cairo-2.dll'), 'Cairo fixture bytes')
    Remove-Item -LiteralPath (Join-Path $directory 'archive.dll')
    $rejected = $false
    try { $null = Set-AbsensaLibraryAliases -Directory $directory } catch {
        $rejected = $_.Exception.Message -match 'Native library archive.dll is missing'
    }
    if (-not $rejected) { throw 'Missing libarchive was accepted.' }
    Write-Host 'Native DLL naming, aliases, spaces, idempotency and missing-library tests passed.'
} finally { Remove-Item -LiteralPath $temp -Recurse -Force }
