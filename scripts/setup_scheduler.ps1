<#
.SYNOPSIS
    Portable Windows Task Scheduler setup for the FBR daily update.

.DESCRIPTION
    Registers (or removes) a Windows scheduled task that runs the
    project's daily FBR update pipeline every day at 03:00.

    The script is fully PORTABLE:
    - it discovers the project root from its own location, so the
      whole project folder can be copied anywhere (or to another
      user's machine) and this script re-run there;
    - it locates the Python interpreter dynamically (project
      .venv first, then the py launcher, then python on PATH);
    - it validates required dependencies before registering;
    - it locates the daily update script dynamically.

    The scheduled task itself is registered with the absolute
    paths resolved AT REGISTRATION TIME (a Windows limitation),
    with the project root as the working directory. Moving the
    project simply requires re-running this script.

.PARAMETER Uninstall
    Remove the scheduled task instead of registering it.

.PARAMETER TaskName
    Name of the scheduled task. Default: "FBR Daily Update".

.PARAMETER Time
    Daily run time (24h HH:mm). Default: "03:00".

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler.ps1

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\setup_scheduler.ps1 -Uninstall
#>

[CmdletBinding()]
param(
    [switch]$Uninstall,
    [string]$TaskName = "FBR Daily Update",
    [string]$Time = "03:00"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[SETUP] $Message"
}

function Write-Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "[FAILED] $Message" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------
# 1. Discover the project root (parent of this script folder)
# ------------------------------------------------------------

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Write-Step "Project root        : $ProjectRoot"

# ------------------------------------------------------------
# 2. Uninstall mode
# ------------------------------------------------------------

if ($Uninstall) {
    Write-Step "Removing scheduled task '$TaskName'..."
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host ""
        Write-Host "[SUCCESS] Scheduled task '$TaskName' removed." -ForegroundColor Green
    }
    else {
        Write-Host ""
        Write-Host "[SUCCESS] No scheduled task named '$TaskName' existed." -ForegroundColor Green
    }
    exit 0
}

# ------------------------------------------------------------
# 3. Locate the Python interpreter (portable discovery)
#
#    The script collects every plausible interpreter (project
#    .venv, all py-launcher versions, PATH python) and selects
#    the FIRST one that actually has the project dependencies.
# ------------------------------------------------------------

function Test-PythonDeps {
    param([string]$Exe)

    if (-not $Exe -or -not (Test-Path $Exe)) {
        return $false
    }

    $code = "import faiss, numpy, rank_bm25, sentence_transformers, dotenv, fastapi"

    # Native-command stderr must not abort the script while
    # $ErrorActionPreference is Stop.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    try {
        & $Exe -c $code 2>$null | Out-Null
        $ok = ($LASTEXITCODE -eq 0)
    }
    catch {
        $ok = $false
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }

    return $ok
}

$PythonCandidates = @()

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $PythonCandidates += $VenvPython
}

$PyLauncher = Get-Command "py" -ErrorAction SilentlyContinue
if ($PyLauncher) {
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"

    $LauncherList = @()

    try {
        # py -0p lists every installed interpreter with its path.
        $LauncherList = (& py -0p 2>$null) | Where-Object { $_ }
    }
    catch {
        $LauncherList = @()
    }

    try {
        $DefaultPy = (& py -3 -c "import sys; print(sys.executable)") 2>$null
        if ($LASTEXITCODE -eq 0 -and $DefaultPy) {
            $LauncherList += ($DefaultPy | Select-Object -First 1)
        }
    }
    catch {
    }

    $ErrorActionPreference = $previousPreference

    foreach ($line in $LauncherList) {
        if ($line -match '([A-Za-z]:\\[^\s]+python\.exe)') {
            $PythonCandidates += $Matches[1]
        }
    }
}

$PathPython = Get-Command "python" -ErrorAction SilentlyContinue
if ($PathPython) {
    $PythonCandidates += $PathPython.Source
}

$PythonExe = $null
$RejectedCandidates = @()

foreach ($Candidate in ($PythonCandidates | Select-Object -Unique)) {
    if (Test-PythonDeps -Exe $Candidate) {
        $PythonExe = $Candidate
        break
    }
    $RejectedCandidates += $Candidate
}

if (-not $PythonExe) {
    $Tried = ($PythonCandidates | Select-Object -Unique) -join "`n  "
    Write-Fail ("No Python interpreter with the project dependencies was found." + `
        "`nCandidates checked:`n  $Tried" + `
        "`nInstall the dependencies with:`n  python -m pip install -r requirements.txt")
}

Write-Step "Python (validated)   : $PythonExe"

if ($RejectedCandidates.Count -gt 0) {
    Write-Step "Skipped (no deps)    : $($RejectedCandidates.Count -join ', ')"
    Write-Host "         interpreters without project deps: $($RejectedCandidates -join '; ')"
}

# ------------------------------------------------------------
# 4. Locate the daily update script dynamically
# ------------------------------------------------------------

$UpdateScript = Join-Path $ProjectRoot "scripts\daily_update.py"

if (-not (Test-Path $UpdateScript)) {
    Write-Fail "Daily update script not found at: $UpdateScript"
}

Write-Step "Daily update script  : $UpdateScript"

# ------------------------------------------------------------
# 6. Register the scheduled task (daily at $Time)
# ------------------------------------------------------------

Write-Step "Registering scheduled task '$TaskName' (daily at $Time)..."

try {
    $Action = New-ScheduledTaskAction `
        -Execute $PythonExe `
        -Argument "-B `"$UpdateScript`"" `
        -WorkingDirectory $ProjectRoot

    $Trigger = New-ScheduledTaskTrigger -Daily -At $Time

    $Settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries

    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Force | Out-Null
}
catch {
    Write-Fail "Could not register the scheduled task: $($_.Exception.Message)"
}

# ------------------------------------------------------------
# 7. Verify registration
# ------------------------------------------------------------

$Registered = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if (-not $Registered) {
    Write-Fail "Registration did not produce a scheduled task."
}

Write-Host ""
Write-Host "[SUCCESS] Scheduled task registered." -ForegroundColor Green
Write-Host "  Task name       : $TaskName"
Write-Host "  Schedule        : Daily at $Time"
Write-Host "  Command         : `"$PythonExe`" -B `"$UpdateScript`""
Write-Host "  Working directory: $ProjectRoot"
Write-Host ""
Write-Host "Next occurrence and run history are visible in Task Scheduler"
Write-Host "(taskschd.msc) under the name '$TaskName'."
Write-Host ""
Write-Host "NOTE: If the project folder is moved or copied to another"
Write-Host "machine, re-run this script there - it re-discovers every"
Write-Host "path dynamically."
