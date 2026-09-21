# setup_autostart.ps1 - registers the app to start with Windows + keeps it alive
# run by setup_autostart.bat (already elevated)

param([Parameter(Mandatory=$true)][string]$AppDir)

$ErrorActionPreference = 'Continue'
$bat = Join-Path $AppDir 'run_server.bat'
if (-not (Test-Path $bat)) { Write-Host "  [!] run_server.bat not found in $AppDir"; exit 1 }

try {
    # ---- 1) scheduled task: run at startup, highest rights, restart on failure
    $action    = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument ('/c "' + $bat + '"') -WorkingDirectory $AppDir
    $trigger   = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
    $settings  = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
                    -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
    Register-ScheduledTask -TaskName 'MehranAiShabestar' -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings -Force | Out-Null
    Write-Host "  [OK] scheduled task 'MehranAiShabestar' registered (runs at boot)."
} catch {
    Write-Host ("  [!] could not register the scheduled task: " + $_.Exception.Message)
}

try {
    # ---- 2) startup folder shortcut (fallback, runs at logon)
    $startup = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'
    if (Test-Path $startup) {
        $lnk = Join-Path $startup 'MehranAiShabestar.lnk'
        $sh  = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
        $sh.TargetPath       = $bat
        $sh.WorkingDirectory = $AppDir
        $sh.WindowStyle      = 7          # minimized
        $sh.Description      = 'MehranAiShabestar server'
        $sh.Save()
        Write-Host "  [OK] startup shortcut created (fallback at logon)."
    }
} catch {
    Write-Host ("  [!] startup shortcut failed: " + $_.Exception.Message)
}

try {
    # ---- 3) firewall rules for the ports the app uses
    foreach ($p in 8000..8010) {
        $name = "MehranAiShabestar $p"
        $exists = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
        if (-not $exists) {
            New-NetFirewallRule -DisplayName $name -Direction Inbound -Action Allow `
                -Protocol TCP -LocalPort $p -Profile Any -ErrorAction Stop | Out-Null
        }
    }
    Write-Host "  [OK] firewall ports 8000-8010 are open."
} catch {
    Write-Host ("  [!] firewall could not be changed: " + $_.Exception.Message)
}

try {
    # ---- 4) stop an old copy if it is running
    Get-NetTCPConnection -LocalPort 8000..8010 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique |
        ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
    Start-Sleep -Seconds 2
} catch { }

Write-Host ""
Write-Host "  READY - the app will start by itself on every reboot."
Write-Host "  To turn it off:  schtasks /delete /tn MehranAiShabestar /f"
