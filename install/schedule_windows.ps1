# schedule_windows.ps1 — register the 7 Insider agents with Windows Task Scheduler.
#
# Creates 7 scheduled tasks under the \InsiderRoutines\ folder.
# Idempotent: re-running removes existing tasks and recreates them.
#
# Logs land in %USERPROFILE%\insider-routines\.state\logs\.

$ErrorActionPreference = "Stop"

$Root    = Join-Path $env:USERPROFILE "insider-routines"
$Agents  = Join-Path $Root "agents"
$Logs    = Join-Path (Join-Path $Root ".state") "logs"
$Folder  = "\InsiderRoutines"
$Python  = (Get-Command python -ErrorAction SilentlyContinue)?.Source
if (-not $Python) { $Python = (Get-Command py -ErrorAction SilentlyContinue)?.Source }
if (-not $Python) {
    Write-Error "Python not found on PATH. Install Python 3.10+ first (https://www.python.org/downloads/)."
    exit 1
}

New-Item -ItemType Directory -Force -Path $Logs | Out-Null

function Register-InsiderTask {
    param(
        [string]$Name,
        [string]$Script,
        [Microsoft.Management.Infrastructure.CimInstance]$Trigger
    )

    $taskPath = "$Folder\"
    $taskName = "Insider-$Name"
    $fullName = "$taskPath$taskName"

    # Remove if it exists.
    if (Get-ScheduledTask -TaskName $taskName -TaskPath $taskPath -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -TaskPath $taskPath -Confirm:$false
    }

    $action = New-ScheduledTaskAction `
        -Execute $Python `
        -Argument "`"$Agents\$Script`"" `
        -WorkingDirectory $Root

    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

    Register-ScheduledTask `
        -TaskName $taskName `
        -TaskPath $taskPath `
        -Action $action `
        -Trigger $Trigger `
        -Settings $settings `
        -Description "Insider Routines · $Name" | Out-Null

    Write-Host "  OK   $fullName"
}

Write-Host "Registering Insider agents with Task Scheduler..."

# Eddie — daily 06:00
Register-InsiderTask -Name "eddie" -Script "eddie.py" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 06:00)

# Maggie — weekly Sunday 19:00
Register-InsiderTask -Name "maggie" -Script "maggie.py" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 19:00)

# Frank — weekly Monday 08:00
Register-InsiderTask -Name "frank" -Script "frank.py" `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 08:00)

# Maya — every 6 hours
Register-InsiderTask -Name "maya" -Script "maya.py" `
    -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date) `
                -RepetitionInterval (New-TimeSpan -Hours 6) `
                -RepetitionDuration ([System.TimeSpan]::MaxValue))

# Janet — daily 17:00
Register-InsiderTask -Name "janet" -Script "janet.py" `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 17:00)

# Sophie — every 30 minutes
Register-InsiderTask -Name "sophie" -Script "sophie.py" `
    -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date) `
                -RepetitionInterval (New-TimeSpan -Minutes 30) `
                -RepetitionDuration ([System.TimeSpan]::MaxValue))

# Ross — every 30 minutes
Register-InsiderTask -Name "ross" -Script "ross.py" `
    -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date) `
                -RepetitionInterval (New-TimeSpan -Minutes 30) `
                -RepetitionDuration ([System.TimeSpan]::MaxValue))

Write-Host ""
Write-Host "All 7 agents registered. Logs -> $Logs"
Write-Host "Inspect: Get-ScheduledTask -TaskPath '$Folder\'"
Write-Host "Uninstall: powershell -File `"$Root\install\uninstall_windows.ps1`""
