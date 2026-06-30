<#
.SYNOPSIS
  Remove temporary Windows OpenSSH support access.

.DESCRIPTION
  Removes the temporary support user created by windows-ssh-onboard.ps1 and
  removes the ZenuxLabs Support Fabric private SSH firewall rule. It can optionally
  leave sshd installed for customer-managed use.

.NOTES
  Must be run as Administrator on the Windows endpoint.
#>

[CmdletBinding()]
param(
    [string]$SupportUser = $(if ($env:ZENUX_SUPPORT_SSH_USER) { $env:ZENUX_SUPPORT_SSH_USER } else { "zenux-support" }),
    [switch]$StopSshd,
    [switch]$DisableSshd
)

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "This script must be run from an elevated Administrator PowerShell session."
}

$user = Get-LocalUser -Name $SupportUser -ErrorAction SilentlyContinue
if ($user) {
    Remove-LocalUser -Name $SupportUser
    Write-Host "[*] Removed local user '$SupportUser'." -ForegroundColor Cyan
} else {
    Write-Host "[*] Local user '$SupportUser' was not present." -ForegroundColor Gray
}

Get-NetFirewallRule -DisplayName "ZenuxLabs Support Fabric SSH over private transport" -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

Write-Host "[*] Removed ZenuxLabs Support Fabric SSH firewall rule if it existed." -ForegroundColor Cyan

if ($StopSshd -or $DisableSshd) {
    Stop-Service -Name sshd -ErrorAction SilentlyContinue
    Write-Host "[*] Stopped sshd." -ForegroundColor Cyan
}

if ($DisableSshd) {
    Set-Service -Name sshd -StartupType Disabled -ErrorAction SilentlyContinue
    Write-Host "[*] Disabled sshd startup." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Windows OpenSSH support offboarding complete." -ForegroundColor Green
