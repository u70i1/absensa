# Fixture cmdlets: this test never changes adapters, firewall rules or trust.
$ErrorActionPreference = 'Stop'
function Get-NetIPInterface {
    param($AddressFamily)
    @([PSCustomObject]@{InterfaceIndex=7; InterfaceAlias='vEthernet (LAN)'; Dhcp='Enabled'; ConnectionState='Connected'},
      [PSCustomObject]@{InterfaceIndex=8; InterfaceAlias='Ethernet'; Dhcp='Disabled'; ConnectionState='Disconnected'})
}
function Get-NetIPAddress {
    param($InterfaceIndex, $AddressFamily)
    if ($InterfaceIndex -ne 7) { throw 'Disconnected interface was queried.' }
    @([PSCustomObject]@{IPAddress='192.168.0.10'; AddressState='Preferred'},
      [PSCustomObject]@{IPAddress='192.168.0.11'; AddressState='Tentative'})
}
function Get-NetConnectionProfile { [PSCustomObject]@{InterfaceAlias='vEthernet (LAN)'; NetworkCategory='Public'} }
function Get-NetFirewallProfile { [PSCustomObject]@{Name='Public'; Enabled=$true} }
$report = (& "$PSScriptRoot/host.ps1" -Action network) | ConvertFrom-Json
if ($report.addresses.Count -ne 1 -or $report.addresses[0].address -ne '192.168.0.10' -or
    $report.addresses[0].interface -ne 'vEthernet (LAN)' -or $report.addresses[0].dhcp -ne 'Enabled') {
    throw 'Active virtual IPv4/DHCP reporting failed.'
}
if ($report.profiles[0].category -ne 'Public' -or $report.firewall[0].enabled -ne $true) {
    throw 'Firewall profile reporting failed.'
}
Write-Host 'Read-only network diagnostics passed.'
