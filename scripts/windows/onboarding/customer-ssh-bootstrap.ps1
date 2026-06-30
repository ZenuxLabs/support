<#
.SYNOPSIS
  Bootstrap a new customer Windows PC for private SSH support.

.DESCRIPTION
  One customer-visible script for the first support session. It installs
  Tailscale, enrolls the device into the tailnet, then configures regular
  Windows OpenSSH Server for key-only support access over the private Tailscale
  address.

  This is not Tailscale SSH. It uses Windows OpenSSH Server.

.PARAMETER TailscaleAuthKey
  Ticket-scoped Tailscale auth key. Can also be provided via TAILSCALE_AUTH_KEY.

.PARAMETER AuthorizedKey
  SSH public key to authorize for the support user. Can also be provided via
  ZENUX_SUPPORT_SSH_AUTHORIZED_KEY.

.PARAMETER Hostname
  Tailscale hostname. Defaults to ZENUX_SUPPORT_HOSTNAME, TAILSCALE_HOSTNAME,
  or the Windows COMPUTERNAME.

.PARAMETER SupportUser
  Local Windows user to create or update. Defaults to zenux-support.

.PARAMETER TicketId
  Ticket identifier recorded in local account metadata where possible.

.PARAMETER ExpiresHours
  Temporary support account expiry in hours. Defaults to 24.

.NOTES
  Must be run as Administrator on the Windows endpoint.
#>

[CmdletBinding()]
param(
    [string]$TailscaleAuthKey = $env:TAILSCALE_AUTH_KEY,
    [string]$AuthorizedKey = $env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY,
    [string]$Hostname = $(if ($env:ZENUX_SUPPORT_HOSTNAME) { $env:ZENUX_SUPPORT_HOSTNAME } elseif ($env:TAILSCALE_HOSTNAME) { $env:TAILSCALE_HOSTNAME } else { $env:COMPUTERNAME }),
    [string]$SupportUser = $(if ($env:ZENUX_SUPPORT_SSH_USER) { $env:ZENUX_SUPPORT_SSH_USER } else { "zenux-support" }),
    [string]$TicketId = $env:ZENUX_SUPPORT_TICKET_ID,
    [int]$ExpiresHours = 24
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated Administrator PowerShell session."
    }
}

function Ensure-Tailscale {
    if (Get-Command tailscale.exe -ErrorAction SilentlyContinue) {
        Write-Host "[*] Tailscale is already installed." -ForegroundColor Gray
        return
    }

    if (Get-Command winget.exe -ErrorAction SilentlyContinue) {
        Write-Host "[*] Installing Tailscale via winget..." -ForegroundColor Cyan
        winget install Tailscale.Tailscale --silent --accept-source-agreements --accept-package-agreements
    } else {
        Write-Host "[*] winget not found, downloading Tailscale installer..." -ForegroundColor Yellow
        $installer = Join-Path $env:TEMP "TailscaleSetup.exe"
        Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe" -OutFile $installer
        Start-Process -FilePath $installer -ArgumentList "/quiet" -Wait
        Remove-Item $installer -Force
    }

    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")

    if (-not (Get-Command tailscale.exe -ErrorAction SilentlyContinue)) {
        throw "Tailscale install completed, but tailscale.exe was not found in PATH."
    }
}

function Wait-TailscaleDaemon {
    Write-Host "[*] Waiting for Tailscale daemon..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds(60)
    do {
        try {
            $status = & tailscale.exe status --json 2>$null | ConvertFrom-Json
            if ($status) {
                return
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    } while ((Get-Date) -lt $deadline)

    throw "Tailscale daemon did not become ready within 60 seconds."
}

function Connect-Tailscale {
    param(
        [Parameter(Mandatory = $true)][string]$AuthKey,
        [Parameter(Mandatory = $true)][string]$Name
    )

    Write-Host "[*] Enrolling device into Tailscale..." -ForegroundColor Cyan
    & tailscale.exe up `
        --auth-key $AuthKey `
        --hostname $Name `
        --unattended `
        --accept-routes=false `
        --accept-dns=false
}

function Invoke-WindowsSshOnboarding {
    param(
        [Parameter(Mandatory = $true)][string]$PublicKey,
        [Parameter(Mandatory = $true)][string]$User,
        [int]$Hours,
        [string]$Ticket
    )

    $scriptPath = Join-Path $env:TEMP "windows-ssh-onboard.ps1"
    Invoke-WebRequest -Uri "https://support.gal.run/windows-ssh-onboard.ps1" -OutFile $scriptPath

    $args = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", $scriptPath,
        "-AuthorizedKey", $PublicKey,
        "-SupportUser", $User,
        "-ExpiresHours", $Hours
    )

    if ($Ticket) {
        $args += @("-TicketId", $Ticket)
    }

    & powershell.exe @args
}

Assert-Administrator

if (-not $TailscaleAuthKey) {
    throw "No TailscaleAuthKey provided. Set TAILSCALE_AUTH_KEY or pass -TailscaleAuthKey."
}

if (-not $AuthorizedKey) {
    throw "No AuthorizedKey provided. Set ZENUX_SUPPORT_SSH_AUTHORIZED_KEY or pass -AuthorizedKey."
}

if ($AuthorizedKey.Trim() -notmatch "^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))\s+") {
    throw "AuthorizedKey does not look like an OpenSSH public key."
}

Ensure-Tailscale
Wait-TailscaleDaemon
Connect-Tailscale -AuthKey $TailscaleAuthKey -Name $Hostname
Invoke-WindowsSshOnboarding -PublicKey $AuthorizedKey -User $SupportUser -Hours $ExpiresHours -Ticket $TicketId

$status = & tailscale.exe status --json | ConvertFrom-Json
$self = $status.Self

Write-Host ""
Write-Host "Customer SSH bootstrap complete." -ForegroundColor Green
Write-Host "Hostname: $Hostname"
Write-Host "User:     $SupportUser"
if ($self.TailscaleIPs) {
    Write-Host "Tailscale IPs: $($self.TailscaleIPs -join ', ')"
}
Write-Host ""
Write-Host "Connect from support machine:"
Write-Host "  ssh $SupportUser@<tailscale-ip-or-name>"
