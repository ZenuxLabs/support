<#
.SYNOPSIS
  Production-oriented Windows OpenSSH onboarding over private transport.

.DESCRIPTION
  Installs and configures Windows OpenSSH Server for key-only support access.
  This is regular Windows OpenSSH, intended to be reached over Tailscale or
  another private transport. It is not Tailscale SSH.

  Defaults are intentionally conservative:
    - creates a temporary non-admin local user
    - installs one SSH public key
    - disables password authentication
    - restricts inbound TCP/22 to Tailscale address ranges
    - restricts sshd login to the support user

.PARAMETER AuthorizedKey
  SSH public key to authorize for the support user. Can also be provided via
  ZENUX_SUPPORT_SSH_AUTHORIZED_KEY.

.PARAMETER SupportUser
  Local Windows user to create or update. Defaults to zenux-support.

.PARAMETER TicketId
  Ticket identifier recorded in the local user description.

.PARAMETER ExpiresHours
  Temporary account expiry in hours. Defaults to 24.

.PARAMETER AllowedRemoteAddress
  Remote address ranges allowed by Windows Firewall for TCP/22.
  Defaults to Tailscale IPv4 and IPv6 ranges.

.PARAMETER SkipAllowUsersRestriction
  Do not add an AllowUsers directive for the support user.

.PARAMETER AllowPasswordAuth
  Leave SSH password authentication enabled. Not recommended for production.

.NOTES
  Must be run as Administrator on the Windows endpoint.
#>

[CmdletBinding()]
param(
    [string]$AuthorizedKey = $env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY,
    [string]$SupportUser = $(if ($env:ZENUX_SUPPORT_SSH_USER) { $env:ZENUX_SUPPORT_SSH_USER } else { "zenux-support" }),
    [string]$TicketId = $env:ZENUX_SUPPORT_TICKET_ID,
    [int]$ExpiresHours = $(if ($env:ZENUX_SUPPORT_EXPIRES_HOURS) { [int]$env:ZENUX_SUPPORT_EXPIRES_HOURS } else { 24 }),
    [string[]]$AllowedRemoteAddress = @("100.64.0.0/10", "fd7a:115c:a1e0::/48"),
    [switch]$SkipAllowUsersRestriction,
    [switch]$AllowPasswordAuth
)

$ErrorActionPreference = "Stop"

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "This script must be run from an elevated Administrator PowerShell session."
    }
}

function New-RandomPassword {
    $bytes = New-Object byte[] 32
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($bytes)
        return [Convert]::ToBase64String($bytes)
    } finally {
        $rng.Dispose()
    }
}

function Set-SshdConfigDirective {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Key,
        [Parameter(Mandatory = $true)][string]$Value
    )

    $lines = @()
    if (Test-Path $Path) {
        $lines = @(Get-Content -Path $Path)
    }

    $matchIndex = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*Match\s+") {
            $matchIndex = $i
            break
        }
    }

    $globalLines = $lines
    $matchLines = @()
    if ($matchIndex -eq 0) {
        $globalLines = @()
        $matchLines = @($lines)
    } elseif ($matchIndex -gt 0) {
        $globalLines = @($lines[0..($matchIndex - 1)])
        $matchLines = @($lines[$matchIndex..($lines.Count - 1)])
    }

    $pattern = "^\s*#?\s*$([regex]::Escape($Key))\s+"
    $replaced = $false
    $updated = foreach ($line in $globalLines) {
        if ($line -match $pattern) {
            if (-not $replaced) {
                "$Key $Value"
                $replaced = $true
            }
        } else {
            $line
        }
    }

    if (-not $replaced) {
        $updated += "$Key $Value"
    }

    if ($matchLines.Count -gt 0) {
        $updated += $matchLines
    }

    Set-Content -Path $Path -Value $updated -Encoding ascii
}

function Ensure-OpenSshServer {
    $capabilityName = "OpenSSH.Server~~~~0.0.1.0"
    $capability = Get-WindowsCapability -Online -Name $capabilityName
    if ($capability.State -ne "Installed") {
        Write-Host "[*] Installing OpenSSH Server Windows capability..." -ForegroundColor Cyan
        Add-WindowsCapability -Online -Name $capabilityName | Out-Null
    } else {
        Write-Host "[*] OpenSSH Server is already installed." -ForegroundColor Gray
    }

    Set-Service -Name sshd -StartupType Automatic
    Start-Service -Name sshd

    $sshDir = Join-Path $env:ProgramData "ssh"
    $sshdConfig = Join-Path $sshDir "sshd_config"
    if (-not (Test-Path $sshdConfig)) {
        Start-Service -Name sshd
        Start-Sleep -Seconds 2
    }

    if (-not (Test-Path $sshdConfig)) {
        throw "OpenSSH Server did not create $sshdConfig."
    }

    $backup = "$sshdConfig.pml-backup-$(Get-Date -Format yyyyMMddHHmmss)"
    Copy-Item -Path $sshdConfig -Destination $backup -Force
    Write-Host "[*] Backed up sshd_config to $backup" -ForegroundColor Gray

    return $sshdConfig
}

function Ensure-SupportUser {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [string]$Ticket,
        [int]$Hours
    )

    $expires = (Get-Date).AddHours($Hours)
    $description = "ZenuxLabs Support Fabric temporary SSH support"
    if ($Ticket) {
        $description = "$description ticket $Ticket"
    }

    $existing = Get-LocalUser -Name $Name -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "[*] Updating existing local user '$Name'." -ForegroundColor Gray
        Enable-LocalUser -Name $Name
        Set-LocalUser -Name $Name -AccountExpires $expires -Description $description
    } else {
        Write-Host "[*] Creating temporary local user '$Name'." -ForegroundColor Cyan
        $password = ConvertTo-SecureString (New-RandomPassword) -AsPlainText -Force
        New-LocalUser `
            -Name $Name `
            -Password $password `
            -AccountExpires $expires `
            -Description $description | Out-Null
    }

    return $expires
}

function Set-AuthorizedKey {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$PublicKey
    )

    $profileDir = Join-Path $env:SystemDrive "Users\$Name"
    $sshDir = Join-Path $profileDir ".ssh"
    $authorizedKeys = Join-Path $sshDir "authorized_keys"
    $account = "$env:COMPUTERNAME\$Name"

    New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
    if (-not (Test-Path $authorizedKeys)) {
        New-Item -ItemType File -Path $authorizedKeys -Force | Out-Null
    }

    $trimmedKey = $PublicKey.Trim()
    $existing = ""
    if (Test-Path $authorizedKeys) {
        $existing = Get-Content -Path $authorizedKeys -Raw -ErrorAction SilentlyContinue
    }
    if ($existing -notmatch [regex]::Escape($trimmedKey)) {
        Add-Content -Path $authorizedKeys -Value $trimmedKey -Encoding ascii
    }

    icacls.exe $profileDir /inheritance:r /grant "SYSTEM:(OI)(CI)F" /grant "Administrators:(OI)(CI)F" /grant "${account}:(OI)(CI)F" | Out-Null
    icacls.exe $sshDir /inheritance:r /grant "SYSTEM:(OI)(CI)F" /grant "Administrators:(OI)(CI)F" /grant "${account}:(OI)(CI)F" | Out-Null
    icacls.exe $authorizedKeys /inheritance:r /grant "SYSTEM:F" /grant "Administrators:F" /grant "${account}:R" | Out-Null

    Write-Host "[*] Installed public key for '$Name'." -ForegroundColor Cyan
}

function Set-PrivateSshFirewall {
    param([string[]]$RemoteAddress)

    Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP" -ErrorAction SilentlyContinue |
        Disable-NetFirewallRule

    Get-NetFirewallRule -DisplayName "ZenuxLabs Support Fabric SSH over private transport" -ErrorAction SilentlyContinue |
        Remove-NetFirewallRule

    New-NetFirewallRule `
        -DisplayName "ZenuxLabs Support Fabric SSH over private transport" `
        -Direction Inbound `
        -Action Allow `
        -Protocol TCP `
        -LocalPort 22 `
        -RemoteAddress $RemoteAddress `
        -Profile Any | Out-Null

    Write-Host "[*] Restricted inbound TCP/22 to: $($RemoteAddress -join ', ')" -ForegroundColor Cyan
}

Assert-Administrator

if (-not $AuthorizedKey) {
    throw "No AuthorizedKey provided. Set ZENUX_SUPPORT_SSH_AUTHORIZED_KEY or pass -AuthorizedKey."
}

if ($AuthorizedKey.Trim() -notmatch "^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))\s+") {
    throw "AuthorizedKey does not look like an OpenSSH public key."
}

$expiry = Ensure-SupportUser -Name $SupportUser -Ticket $TicketId -Hours $ExpiresHours
$sshdConfig = Ensure-OpenSshServer
Set-AuthorizedKey -Name $SupportUser -PublicKey $AuthorizedKey

Set-SshdConfigDirective -Path $sshdConfig -Key "PubkeyAuthentication" -Value "yes"
Set-SshdConfigDirective -Path $sshdConfig -Key "PermitEmptyPasswords" -Value "no"
Set-SshdConfigDirective -Path $sshdConfig -Key "PasswordAuthentication" -Value $(if ($AllowPasswordAuth) { "yes" } else { "no" })
Set-SshdConfigDirective -Path $sshdConfig -Key "KbdInteractiveAuthentication" -Value "no"
Set-SshdConfigDirective -Path $sshdConfig -Key "AllowTcpForwarding" -Value "no"
Set-SshdConfigDirective -Path $sshdConfig -Key "AllowAgentForwarding" -Value "no"
Set-SshdConfigDirective -Path $sshdConfig -Key "X11Forwarding" -Value "no"

if (-not $SkipAllowUsersRestriction) {
    Set-SshdConfigDirective -Path $sshdConfig -Key "AllowUsers" -Value $SupportUser
}

New-Item -Path "HKLM:\SOFTWARE\OpenSSH" -Force | Out-Null
New-ItemProperty `
    -Path "HKLM:\SOFTWARE\OpenSSH" `
    -Name DefaultShell `
    -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" `
    -PropertyType String `
    -Force | Out-Null

$sshd = Get-Command sshd.exe -ErrorAction SilentlyContinue
if ($sshd) {
    & $sshd.Source -t -f $sshdConfig
}

Restart-Service -Name sshd
Set-PrivateSshFirewall -RemoteAddress $AllowedRemoteAddress

Write-Host ""
Write-Host "Windows OpenSSH onboarding complete." -ForegroundColor Green
Write-Host "User:       $SupportUser"
Write-Host "Expires:    $expiry"
Write-Host "Transport:  Tailscale or another private network path"
Write-Host "Firewall:   TCP/22 allowed from $($AllowedRemoteAddress -join ', ')"
Write-Host ""
Write-Host "Connect from support machine:"
Write-Host "  ssh $SupportUser@<tailscale-ip-or-name>"
