<#
.SYNOPSIS
  Download, hash-verify, and run a support script from the published manifest.

.DESCRIPTION
  This runner is the transition path away from direct `irm ... | iex` for
  support scripts. It downloads manifest.json, verifies the selected script
  SHA256 hash, optionally verifies Authenticode signature status, then executes
  the script with the provided arguments.

  Production still needs a signed or otherwise pinned delivery path for this
  runner itself.

.PARAMETER Script
  Script name from manifest.json, for example crash-check.ps1.

.PARAMETER ManifestUrl
  Manifest URL. Defaults to the operating instance's /manifest.json — resolved
  from ZENUX_SUPPORT_MANIFEST_URL, ZENUX_SUPPORT_BASE_URL, or the base URL baked
  in at build time. The OSS engine hardcodes no domain.

.PARAMETER Destination
  Local directory used for downloaded scripts.

.PARAMETER RequireSignature
  Require the downloaded target script to have a valid Authenticode signature.

.PARAMETER KeepScript
  Keep the downloaded target script on disk after execution.

.PARAMETER ScriptArgs
  Arguments passed through to the target script.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Script,

    [string]$ManifestUrl = $(if ($env:ZENUX_SUPPORT_MANIFEST_URL) { $env:ZENUX_SUPPORT_MANIFEST_URL } elseif ($env:ZENUX_SUPPORT_BASE_URL) { $env:ZENUX_SUPPORT_BASE_URL.TrimEnd('/') + "/manifest.json" } elseif ('{{SUPPORT_BASE_URL}}' -and '{{SUPPORT_BASE_URL}}' -notlike '*{{*') { '{{SUPPORT_BASE_URL}}'.TrimEnd('/') + "/manifest.json" } else { throw "No manifest URL. Set ZENUX_SUPPORT_MANIFEST_URL or ZENUX_SUPPORT_BASE_URL (or build with SUPPORT_BASE_URL)." }),

    [string]$Destination = $(Join-Path $env:TEMP "zenux-support"),

    [switch]$RequireSignature,

    [switch]$KeepScript,

    [string[]]$ScriptArgs = @()
)

$ErrorActionPreference = "Stop"

function Join-Url {
    param(
        [Parameter(Mandatory = $true)][string]$BaseUrl,
        [Parameter(Mandatory = $true)][string]$Path
    )

    if ($Path -match "^https?://") {
        return $Path
    }

    return $BaseUrl.TrimEnd("/") + "/" + $Path.TrimStart("/")
}

function Get-ManifestEntry {
    param(
        [Parameter(Mandatory = $true)]$Manifest,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $entry = @($Manifest.scripts | Where-Object { $_.name -eq $Name }) | Select-Object -First 1
    if (-not $entry) {
        $available = @($Manifest.scripts | ForEach-Object { $_.name }) -join ", "
        throw "Script '$Name' was not found in manifest. Available scripts: $available"
    }
    return $entry
}

New-Item -ItemType Directory -Path $Destination -Force | Out-Null

Write-Host "[*] Downloading support manifest: $ManifestUrl" -ForegroundColor Cyan
$manifest = Invoke-RestMethod -Uri $ManifestUrl
$entry = Get-ManifestEntry -Manifest $manifest -Name $Script

$scriptUrl = Join-Url -BaseUrl $manifest.baseUrl -Path $entry.path
$scriptPath = Join-Path $Destination $entry.name

Write-Host "[*] Downloading $($entry.name)" -ForegroundColor Cyan
Invoke-WebRequest -Uri $scriptUrl -OutFile $scriptPath

$actualHash = (Get-FileHash -Algorithm SHA256 -Path $scriptPath).Hash.ToLowerInvariant()
$expectedHash = [string]$entry.sha256
if ($actualHash -ne $expectedHash.ToLowerInvariant()) {
    Remove-Item -Path $scriptPath -Force -ErrorAction SilentlyContinue
    throw "Hash verification failed for $($entry.name). Expected $expectedHash but got $actualHash."
}

Write-Host "[*] SHA256 verified: $actualHash" -ForegroundColor Green

if ($RequireSignature) {
    $signature = Get-AuthenticodeSignature -FilePath $scriptPath
    if ($signature.Status -ne "Valid") {
        Remove-Item -Path $scriptPath -Force -ErrorAction SilentlyContinue
        throw "Authenticode signature verification failed for $($entry.name): $($signature.Status)"
    }
    Write-Host "[*] Authenticode signature verified." -ForegroundColor Green
}

try {
    Write-Host "[*] Running $($entry.name)" -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File $scriptPath @ScriptArgs
    $exitCode = if ($LASTEXITCODE -is [int]) { $LASTEXITCODE } else { 0 }
    if ($exitCode -ne 0) {
        throw "Script exited with code $exitCode."
    }
} finally {
    if (-not $KeepScript) {
        Remove-Item -Path $scriptPath -Force -ErrorAction SilentlyContinue
    }
}
