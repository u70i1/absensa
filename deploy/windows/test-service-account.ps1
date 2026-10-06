# Administrator-only SCM regression test for ephemeral Windows CI runners.
# Creates one uniquely named, stopped service; never starts its dummy executable.
# The full smoke test separately verifies the packaged services actually run.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
if ($env:OS -ne 'Windows_NT') { throw 'This test requires Windows and Administrator privileges.' }
$principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'This test requires Administrator privileges.'
}
$name = 'AbsensaAccountTest_' + [Guid]::NewGuid().ToString('N')
if (Get-Service -Name $name -ErrorAction SilentlyContinue) { throw 'Refusing an existing service.' }
$created = $false
try {
    New-Service -Name $name -BinaryPathName ('"{0}\System32\cmd.exe"' -f $env:SystemRoot) -StartupType Manual | Out-Null
    $created = $true
    foreach ($attempt in @(1,2)) {
        # The same production operation must work on creation and repair.
        & (Join-Path $PSScriptRoot 'host.ps1') -Action service -Name $name
        $service = Get-CimInstance Win32_Service -Filter "Name='$name'"
        if (-not $service -or $service.StartName -ne "NT SERVICE\$name" -or
            $service.StartMode -ne 'Manual' -or $service.State -ne 'Stopped') {
            throw "Virtual service identity or lifecycle changed unexpectedly on attempt $attempt."
        }
        $properties = Get-ItemProperty -LiteralPath "HKLM:\SYSTEM\CurrentControlSet\Services\$name"
        if ($properties.ServiceSidType -ne 1) { throw 'Unrestricted service SID was not enabled.' }
        # Account translation is required by the following production ACL grants.
        $account = New-Object Security.Principal.NTAccount("NT SERVICE\$name")
        $sid = $account.Translate([Security.Principal.SecurityIdentifier])
        if ($sid.Value -notlike 'S-1-5-80-*') { throw 'Virtual service SID did not resolve.' }
    }
    Write-Host 'Native SCM virtual account, SID resolution and repeat configuration passed.'
} finally {
    if ($created) {
        & "$env:SystemRoot\System32\sc.exe" delete $name
        if ($LASTEXITCODE -ne 0) { throw "Cannot remove CI-owned test service $name." }
    }
}
