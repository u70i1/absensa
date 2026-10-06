# Keep upstream filenames for DLL dependencies and add the Python loader aliases.
function Set-AbsensaLibraryAliases {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$Directory)
    $mapping = @{}
    foreach ($library in @(
        @{ Alias = 'libcairo-2.dll'; Candidates = @('cairo-2.dll','cairo.dll','libcairo-2.dll') },
        @{ Alias = 'archive.dll'; Candidates = @('archive.dll','libarchive.dll') }
    )) {
        $source = @($library.Candidates | Where-Object { Test-Path -LiteralPath (Join-Path $Directory $_) -PathType Leaf })
        if (-not $source.Count) {
            $available = @(Get-ChildItem -LiteralPath $Directory -Filter '*.dll' | ForEach-Object Name) -join ', '
            throw "Native library $($library.Alias) is missing. Expected: $($library.Candidates -join ', '). DLLs found in ${Directory}: $available"
        }
        if ($source[0] -ne $library.Alias) {
            Copy-Item -LiteralPath (Join-Path $Directory $source[0]) -Destination (Join-Path $Directory $library.Alias) -ErrorAction Stop
        }
        $mapping[$library.Alias] = $source[0]
        Write-Host "Native library: $($source[0]) -> $($library.Alias)"
    }
    return $mapping
}
