# scripts/windows/diagnostics/crash-check.ps1
# Run on customer PC to diagnose overheating and shutdown causes.
# Must be run as Administrator for full event log access.

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "  ZenuxLabs Support Fabric Hardware Diagnostic" -ForegroundColor White
Write-Host "  ====================================" -ForegroundColor White
Write-Host "  Reads system info & event logs only. No changes made."
Write-Host "  No personal data collected or transmitted."
Write-Host "  Output visible in this window only."
Write-Host ""

Write-Host "=== SYSTEM INFO ===" -ForegroundColor Cyan
Get-CimInstance Win32_ComputerSystem | Select-Object Manufacturer, Model, TotalPhysicalMemory | Format-List
Get-CimInstance Win32_BIOS | Select-Object Manufacturer, SMBIOSBIOSVersion | Format-List

Write-Host "=== CPU ===" -ForegroundColor Cyan
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, MaxClockSpeed | Format-List

Write-Host "=== GPU ===" -ForegroundColor Cyan
Get-CimInstance Win32_VideoController | Where-Object { $_.Name -notlike "*Remote*" -and $_.Name -notlike "*Hyper-V*" } | ForEach-Object {
    Write-Host "  GPU : $($_.Name)" -ForegroundColor Gray
    Write-Host "  RAM : $([math]::Round($_.AdapterRAM/1GB, 1)) GB" -ForegroundColor Gray
}

Write-Host "=== DISK ===" -ForegroundColor Cyan
Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object DeviceID, @{N='SizeGB';E={[math]::Round($_.Size/1GB,1)}}, @{N='FreeGB';E={[math]::Round($_.FreeSpace/1GB,1)}} | Format-Table

Write-Host "=== POWER PLAN ===" -ForegroundColor Cyan
powercfg /getactivescheme

Write-Host "=== THERMAL EVENTS (last 7 days) ===" -ForegroundColor Cyan
Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddDays(-7)} -MaxEvents 500 -ErrorAction SilentlyContinue |
    Where-Object { $_.Message -match 'thermal|overheat|temperature|throttl' -or $_.Id -eq 86 -or $_.Id -eq 88 } |
    Select-Object TimeCreated, Id, LevelDisplayName, @{N='Message';E={($_.Message -split '\n')[0]}} |
    Format-Table -AutoSize -Wrap

Write-Host "=== CRITICAL & ERROR EVENTS (last 30, System log) ===" -ForegroundColor Cyan
Get-WinEvent -LogName System -MaxEvents 30 -ErrorAction SilentlyContinue |
    Where-Object { $_.LevelDisplayName -eq 'Critical' -or $_.LevelDisplayName -eq 'Error' } |
    Select-Object TimeCreated, Id, ProviderName, LevelDisplayName, @{N='Message';E={($_.Message -split '\n')[0]}} |
    Format-Table -AutoSize -Wrap

Write-Host "=== KERNEL-POWER EVENTS (event ID 41 — unexpected shutdown) ===" -ForegroundColor Cyan
Get-WinEvent -FilterHashtable @{LogName='System'; Id=41} -MaxEvents 5 -ErrorAction SilentlyContinue |
    ForEach-Object {
        Write-Host "  Time: $($_.TimeCreated)" -ForegroundColor Red
        # Extract BugCheckCode, PowerButtonTimestamp, SleepInProgress
        $xml = [xml]$_.ToXml()
        $data = $xml.Event.EventData.Data
        if ($data) {
            foreach ($d in $data) {
                Write-Host "    $($d.Name): $($d.'#text')" -ForegroundColor Gray
            }
        }
        Write-Host "  ---"
    }

Write-Host "=== WHEA-LOGGER EVENTS (hardware errors) ===" -ForegroundColor Cyan
Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Microsoft-Windows-WHEA-Logger'} -MaxEvents 10 -ErrorAction SilentlyContinue |
    Select-Object TimeCreated, LevelDisplayName, @{N='Message';E={($_.Message -split '\n')[0]}} |
    Format-Table -AutoSize -Wrap

Write-Host "=== APPLICATION CRASHES (last 50, Application log) ===" -ForegroundColor Cyan
Get-WinEvent -LogName Application -MaxEvents 50 -ErrorAction SilentlyContinue |
    Where-Object { $_.Id -eq 1000 -or $_.Id -eq 1001 } |
    Select-Object TimeCreated, Id, @{N='Message';E={($_.Message -split '\n')[0..2] -join ' '}} |
    Format-Table -AutoSize -Wrap

Write-Host "=== RELIABILITY (stability index, last 14 days) ===" -ForegroundColor Cyan
try {
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = "powershell.exe"
    $psi.Arguments = "-NoProfile -Command `"Get-CimInstance Win32_ReliabilityRecords | Sort-Object TimeGenerated | Select-Object TimeGenerated, ProductName, RecordNumber, Message | Format-Table -AutoSize -Wrap`""
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false
    $p = [System.Diagnostics.Process]::Start($psi)
    $output = $p.StandardOutput.ReadToEnd()
    $p.WaitForExit(5000)
    $output | Select-String -Pattern "." | Select-Object -Last 20
} catch {
    Write-Host "  Could not read reliability history: $_" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "=== RUNNING PROCESSES (top 10 by CPU) ===" -ForegroundColor Cyan
Get-Process | Sort-Object CPU -Descending | Select-Object -First 10 |
    Select-Object Name, Id, @{N='CPU(s)';E={[math]::Round($_.CPU,1)}}, @{N='MemMB';E={[math]::Round($_.WorkingSet/1MB,1)}} |
    Format-Table -AutoSize

Write-Host ""
Write-Host "Dump complete." -ForegroundColor Green
Write-Host "Check: Kernel-Power 41 = power/shutdown.  WHEA = hardware error.  Thermal event = overheating."
