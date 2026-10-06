# Native host operations. Invoked with argument arrays; never evaluates downloaded strings.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][ValidateSet('private','grant','grant-installer','revoke-installer','service','firewall','unfirewall','platform')][string]$Action,
    [string]$Path, [string]$Name, [string]$Rights = 'ReadAndExecute',
    [int]$Port = 443, [string]$Address = 'LocalSubnet'
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
if ($Action -eq 'platform') {
    $os = Get-CimInstance Win32_OperatingSystem
    if ($os.ProductType -eq 1 -or [int]$os.BuildNumber -notin @(17763,20348,26100) -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') {
        throw 'Diperlukan Windows Server 2019/2022/2025 amd64.'
    }
    if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Buka Windows PowerShell sebagai Administrator.'
    }
} elseif ($Action -eq 'private') {
    $item = Get-Item -LiteralPath $Path
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Jalur tautan tidak diizinkan.' }
    $acl = if ($item.PSIsContainer) { New-Object Security.AccessControl.DirectorySecurity } else { New-Object Security.AccessControl.FileSecurity }
    $acl.SetAccessRuleProtection($true, $false)
    $inherit = if ($item.PSIsContainer) { 'ContainerInherit,ObjectInherit' } else { 'None' }
    foreach ($sid in @('S-1-5-18','S-1-5-32-544')) {
        $identity = New-Object Security.Principal.SecurityIdentifier($sid)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity,'FullControl',$inherit,'None','Allow')
        $acl.AddAccessRule($rule)
    }
    $acl.SetOwner((New-Object Security.Principal.SecurityIdentifier('S-1-5-32-544')))
    Set-Acl -LiteralPath $Path -AclObject $acl
} elseif ($Action -in @('grant-installer','revoke-installer')) {
    # initdb re-executes after disabling Administrators in its token. Grant only
    # the invoking user's SID, then remove that exact ACE after initialization.
    $acl = Get-Acl -LiteralPath $Path
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $inherit = if ((Get-Item -LiteralPath $Path).PSIsContainer -and $Rights -ne 'Traverse') { 'ContainerInherit,ObjectInherit' } else { 'None' }
    $rule = New-Object Security.AccessControl.FileSystemAccessRule($identity,$Rights,$inherit,'None','Allow')
    if ($Action -eq 'grant-installer') { $acl.AddAccessRule($rule) } else { $acl.RemoveAccessRuleSpecific($rule) }
    Set-Acl -LiteralPath $Path -AclObject $acl
} elseif ($Action -eq 'grant') {
    if ($Name -notmatch '^Absensa(PostgreSQL|Web|Scheduler|Backup|WhatsApp|Caddy)$') { throw 'Layanan tidak dikenal.' }
    $acl = Get-Acl -LiteralPath $Path
    $inherit = if ((Get-Item -LiteralPath $Path).PSIsContainer) { 'ContainerInherit,ObjectInherit' } else { 'None' }
    $rule = New-Object Security.AccessControl.FileSystemAccessRule("NT SERVICE\$Name",$Rights,$inherit,'None','Allow')
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
} elseif ($Action -eq 'service') {
    & "$env:SystemRoot\System32\sc.exe" config $Name obj= "NT SERVICE\$Name" password= '""'
    if ($LASTEXITCODE -ne 0) { throw 'Identitas layanan gagal diatur.' }
    & "$env:SystemRoot\System32\sc.exe" sidtype $Name unrestricted
    if ($LASTEXITCODE -ne 0) { throw 'SID layanan gagal diatur.' }
} elseif ($Action -eq 'firewall') {
    # Never adopt or remove another application's rule.
    $existing = Get-NetFirewallRule -Name 'Absensa-Native-HTTPS' -ErrorAction SilentlyContinue
    if ($existing -and $existing.Group -ne 'Absensa native') { throw 'Nama aturan firewall sudah digunakan.' }
    if ($existing) { $existing | Remove-NetFirewallRule }
    New-NetFirewallRule -Name 'Absensa-Native-HTTPS' -DisplayName 'Absensa HTTPS LAN' -Group 'Absensa native' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -RemoteAddress $Address -Profile Domain,Private -Program $Path | Out-Null
    Write-Host "Firewall: TCP $Port, jaringan Domain/Private, sumber $Address."
} elseif ($Action -eq 'unfirewall') {
    Get-NetFirewallRule -Name 'Absensa-Native-HTTPS' -ErrorAction SilentlyContinue | Where-Object Group -eq 'Absensa native' | Remove-NetFirewallRule
}
