<#
.SYNOPSIS
  Put the whole Control system on this machine - one run.

  Installs dependencies, creates CONTROL_ROOT from the repository's
  config templates, initialises the database and audit chain, checks
  Outlook, and reports readiness.

  Safe to re-run: existing configuration is never overwritten.

.EXAMPLE
  .\scripts\setup-laptop.ps1
  .\scripts\setup-laptop.ps1 -ControlRoot "D:\UnitedBrothers\CONTROL"
#>
param(
    [string]$ControlRoot = "$env:USERPROFILE\Documents\UnitedBrothers\CONTROL",
    [string]$UbRoot = "E:\UBCSIS Co Date Jan 2026",
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot

Write-Host "== Control - machine setup ==" -ForegroundColor Cyan
Write-Host "repository:   $repo"
Write-Host "CONTROL_ROOT: $ControlRoot"
Write-Host "UB_ROOT:      $UbRoot"
Write-Host ""

# ---- 1. dependencies ------------------------------------------------------
if (-not $SkipInstall) {
    Write-Host "== Step 1: dependencies ==" -ForegroundColor Cyan
    Push-Location $repo
    try {
        python -m pip install -e ".[dev]" --quiet
        python -m pip install pywin32 --quiet     # Outlook COM (Windows only)
        Write-Host "  installed"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "== Step 1: dependencies skipped ==" -ForegroundColor Cyan
}

# ---- 2. CONTROL_ROOT ------------------------------------------------------
Write-Host ""
Write-Host "== Step 2: CONTROL_ROOT ==" -ForegroundColor Cyan
Push-Location $repo
try {
    python -m control init --control-root $ControlRoot
} finally {
    Pop-Location
}

# ---- 3. persist the environment variable ---------------------------------
Write-Host ""
Write-Host "== Step 3: environment ==" -ForegroundColor Cyan
[Environment]::SetEnvironmentVariable("CONTROL_ROOT", $ControlRoot, "User")
$env:CONTROL_ROOT = $ControlRoot
Write-Host "  CONTROL_ROOT set for this user (new shells will have it)"

# UB_ROOT is the company folder (open decision O-09, closed 16-Aug-2026).
# The cycle and discovery commands refuse to run without it rather than
# operating on a partial view (charter 13.2).
[Environment]::SetEnvironmentVariable("UB_ROOT", $UbRoot, "User")
$env:UB_ROOT = $UbRoot
Write-Host "  UB_ROOT set for this user"
if (-not (Test-Path -LiteralPath $UbRoot)) {
    Write-Host "  WARNING: $UbRoot is not reachable from this machine." -ForegroundColor Yellow
    Write-Host "  Startup halts on an unreachable UB_ROOT. Re-run with -UbRoot <path>."
}

# ---- 4. readiness ---------------------------------------------------------
Write-Host ""
Write-Host "== Step 4: readiness ==" -ForegroundColor Cyan
Push-Location $repo
try {
    python -m control doctor --control-root $ControlRoot
    $doctorExit = $LASTEXITCODE
    Write-Host ""
    Write-Host "== Step 5: integrity ==" -ForegroundColor Cyan
    python -m control verify --control-root $ControlRoot
} finally {
    Pop-Location
}

Write-Host ""
if ($doctorExit -eq 0) {
    Write-Host "Ready." -ForegroundColor Green
} else {
    Write-Host "Setup finished with warnings - see above." -ForegroundColor Yellow
}
Write-Host "Next: docs\RUNBOOK.md - the commands in order."
Write-Host "Start with:  python -m control contracts"
Write-Host ""
Write-Host "Reminder: CONTROL_ROOT holds mail-derived data and is not in git."
Write-Host "Back it up encrypted, daily, in full (charter 5.2)."
