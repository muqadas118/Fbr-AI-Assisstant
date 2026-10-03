# Registers a Windows Task Scheduler job that runs scripts/daily_update.py daily at 07:00.
# Reuses the PROJECT_ROOT logic from daily_update.py (scripts/ lives under project root).
# If the task already exists, it is updated in place (no duplicates).

$ErrorActionPreference = "Stop"

# Auto-detect project root from this script's location (scripts/ -> parents[1] equivalent)
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ScriptPath = Join-Path $ProjectRoot "scripts\daily_update.py"

if (-not (Test-Path $ScriptPath)) {
    throw "daily_update.py not found at: $ScriptPath"
}

# Resolve python executable (PATH python)
$Python = (Get-Command python -ErrorAction Stop).Source

$TaskName = "FBR Daily Update"
$Action = New-ScheduledTaskAction -Execute $Python -Argument "`"$ScriptPath`"" -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "07:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    Set-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null
    Write-Host "Task '$TaskName' updated. Runs daily at 07:00."
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal | Out-Null
    Write-Host "Task '$TaskName' created. Runs daily at 07:00."
}

Write-Host "Project root : $ProjectRoot"
Write-Host "Command      : $Python `"$ScriptPath`""
Write-Host "Check it     : taskschd.msc -> Task Scheduler Library -> 'FBR Daily Update'"
