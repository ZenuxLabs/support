<#
.SYNOPSIS
  One-command fleet onboarding entry point for a new Windows machine.

.DESCRIPTION
  This is the short front door for Windows fleet onboarding. Windows cannot use
  Tailscale's built-in SSH server, so onboarding means: join the tailnet, then
  run regular Windows OpenSSH Server reached over the Tailscale transport. This
  wrapper collects the one unavoidable input (the tagged Tailscale auth key),
  bakes in everything else (support SSH key, hostname, durable account), and
  hands off to the hash-verified runner.

  Run from an ELEVATED PowerShell on the new machine:

      irm {{SUPPORT_BASE_URL}}/join.ps1 | iex

  Non-interactive (CI / unattended): preset the env vars and pipe as above.
      $env:TAILSCALE_AUTH_KEY = 'tskey-auth-...'
      $env:ZENUX_SUPPORT_HOSTNAME = 'windows-2'   # optional; defaults to COMPUTERNAME

  The auth key must be a TAGGED key (tag:worker, tag:shared) — tags are applied
  from the key, matching the rest of the fleet. This wrapper itself carries NO
  secret; the actual onboard script is SHA256-verified through /manifest.json.
#>

$ErrorActionPreference = "Stop"

# --- Serving base URL -----------------------------------------------------
# Resolution: caller env -> value baked in at build time by the operating
# instance ({{SUPPORT_BASE_URL}}) -> fail. The OSS engine bakes no domain; a
# deployed instance serves its own host (this is fetched from that host).
$bakedBaseUrl = '{{SUPPORT_BASE_URL}}'
$baseUrl =
    if ($env:ZENUX_SUPPORT_BASE_URL) { $env:ZENUX_SUPPORT_BASE_URL }
    elseif ($bakedBaseUrl -and $bakedBaseUrl -notlike '*{{*') { $bakedBaseUrl }
    else { throw "No support base URL baked in. Re-fetch join.ps1 from your support host, or set ZENUX_SUPPORT_BASE_URL." }
$baseUrl = $baseUrl.TrimEnd('/')

# --- Must be elevated -----------------------------------------------------
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]$identity
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "This must run in an ELEVATED PowerShell (Run as Administrator)." -ForegroundColor Yellow
    Write-Host "Open PowerShell as Administrator, then re-run:" -ForegroundColor Yellow
    Write-Host "  irm $baseUrl/join.ps1 | iex" -ForegroundColor Yellow
    return
}

# --- 1. Tagged Tailscale auth key (the one unavoidable input) -------------
$authKey = $env:TAILSCALE_AUTH_KEY
if (-not $authKey) {
    $secure = Read-Host "Paste the tagged Tailscale auth key (tskey-...)" -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $authKey = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
}
$authKey = $authKey.Trim()
if ($authKey -notmatch '^tskey-') {
    throw "That does not look like a Tailscale auth key (expected to start with 'tskey-')."
}

# --- 2. Hostname (default = this machine's name) --------------------------
$hostName = if ($env:ZENUX_SUPPORT_HOSTNAME) { $env:ZENUX_SUPPORT_HOSTNAME } else { $env:COMPUTERNAME.ToLower() }

# --- 3. SSH authorized key -------------------------------------------------
# Resolution order: caller env -> key baked in at deploy time by the operating
# instance (worker build fills {{SUPPORT_AUTHORIZED_KEY}}) -> prompt. The OSS
# build leaves it empty so self-hosters authorize THEIR own key, not anyone
# else's. A public SSH key is not a secret.
$bakedKey = '{{SUPPORT_AUTHORIZED_KEY}}'
$authorizedKey =
    if ($env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY) { $env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY }
    elseif ($bakedKey -and $bakedKey -notlike '*{{*') { $bakedKey }
    else { Read-Host "Paste the SSH public key to authorize for support access (ssh-ed25519 ...)" }
if ($authorizedKey.Trim() -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521))\s+') {
    throw "That does not look like an OpenSSH public key."
}

$env:TAILSCALE_AUTH_KEY = $authKey
$env:ZENUX_SUPPORT_HOSTNAME = $hostName
$env:ZENUX_SUPPORT_SSH_AUTHORIZED_KEY = $authorizedKey
$env:ZENUX_SUPPORT_SSH_USER = "zenux-support"
# Inherited by the verified child scripts so their secondary downloads resolve
# to this same host (no hardcoded domain).
$env:ZENUX_SUPPORT_BASE_URL = $baseUrl
# Durable fleet account (~10y) rather than the 24h support-session default.
# Passed via env (inherited by the child scripts), NOT -ScriptArgs: an array
# does not survive the `powershell -File` boundary in run-verified.ps1, so
# `-ExpiresHours 87600` arrived as a bare `-ExpiresHours` with no value.
$env:ZENUX_SUPPORT_EXPIRES_HOURS = "87600"

Write-Host ""
Write-Host "[*] Onboarding '$hostName' to the tailnet (Tailscale + key-only Windows OpenSSH)..." -ForegroundColor Cyan

# --- 4. Fetch the hash-verifying runner; run the verified bootstrap -------
$runner = Join-Path $env:TEMP "zenux-run-verified.ps1"
Invoke-WebRequest -Uri "$baseUrl/run-verified.ps1" -OutFile $runner
try {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $runner `
        -ManifestUrl "$baseUrl/manifest.json" `
        -Script "customer-ssh-bootstrap.ps1"
} finally {
    Remove-Item $runner -Force -ErrorAction SilentlyContinue
}
# The runner is a child powershell.exe; its failure does NOT throw here. Check the
# exit code so a failed onboard is not reported as success (windows-2 lesson).
if ($LASTEXITCODE -ne 0) {
    throw "Onboarding failed (run-verified.ps1 exit $LASTEXITCODE); '$hostName' is NOT fully onboarded."
}

Write-Host ""
Write-Host "Done. From the controller (mac-pro-1):" -ForegroundColor Green
Write-Host "  tailscale ping $hostName"
Write-Host "  ssh $hostName"
