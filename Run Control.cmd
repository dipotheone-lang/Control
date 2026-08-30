@echo off
rem ===========================================================================
rem  Control - the statutory horizon, in one double-click.
rem
rem  Decision D-15 narrowed Control to class 1 statutory obligations and
rem  no mailbox read. This is that scope's whole operating output: what
rem  is due in the next 30 days, who owns it, and what is counting down
rem  to nothing at all.
rem
rem  It takes seconds. It reads config\statutory-calendar.yaml and
rem  nothing else - no mailbox, no drive scan, no OCR - so it works on a
rem  machine where Outlook is closed and E: is unplugged.
rem
rem  It sends nothing. Every outbound message Control produces is a draft
rem  in outbox\pending-approval, in every mode, with no override for
rem  urgency or seniority (charter section 10).
rem
rem  The full discovery run is still here, unchanged, in
rem  "Run full scan.cmd" - widening the scope later means closing the
rem  section 12 pre-conditions, not rebuilding anything.
rem ===========================================================================

setlocal
title Control - statutory horizon
cd /d "%~dp0"

rem /scheduled: no prompts and nothing opened. A scheduled task that ends
rem on `pause` waits forever with nobody there to press a key.
set "INTERACTIVE=1"
if /I "%~1"=="/scheduled" set "INTERACTIVE="

rem %~dp0 ends in a backslash, and a quoted path ending in one escapes
rem the closing quote. Strip it once here rather than in three places.
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
if not defined CONTROL_ROOT set "CONTROL_ROOT=%HERE%"

rem The scope is set here rather than left to the environment. A default
rem picked up from a machine that was set up months ago would be the
rem wider one, and Control halts on an unrecognised value precisely so a
rem scope is never inherited by accident (section 5.6).
set "OPERATING_SCOPE=STATUTORY_ONLY"

echo ===========================================================================
echo   CONTROL - statutory horizon
echo ===========================================================================
echo   CONTROL_ROOT : %CONTROL_ROOT%
echo   Scope        : STATUTORY_ONLY (D-15) - class 1 only, no mailbox read
echo.

echo == 1 of 2: updating ==
rem The tracking branch, not a named one: a hardcoded branch stops
rem updating the day it is merged and deleted, and does so silently.
git pull --ff-only
if errorlevel 1 (
  echo    no update applied - offline, or local edits in the way.
  echo    Running the version already on disk.
)
python -m pip install -e . --quiet >nul 2>&1

echo.
echo == 2 of 2: the horizon ==
echo.
python -m control statutory --control-root "%CONTROL_ROOT%"
if errorlevel 1 (
  echo.
  echo   The run stopped above. Control halts rather than carrying on with
  echo   a partial view - an empty horizon and a horizon that failed to
  echo   build look identical on the page, and only one of them is safe to
  echo   act on (section 1.1).
  if defined INTERACTIVE pause
  endlocal
  exit /b 1
)

echo.
echo ===========================================================================
echo   Not one of these dates has been confirmed by a tax advisor (O-03).
echo   They alert early, which is what the charter asks for - but nobody
echo   qualified has checked them, and time passing does not check them.
echo   O-03 is the one open item between this and a verified calendar.
echo ===========================================================================
echo.

rem Today's page, saved. The console scrolls; reports\ does not.
rem
rem The date is fetched outside the `if` block on purpose: a variable set
rem inside a parenthesised block and read in the same block expands to
rem what it held before the block started, which here would be nothing.
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd"') do set "TODAY=%%d"
if defined INTERACTIVE call :open "%CONTROL_ROOT%\reports\statutory-%TODAY%.txt"

if defined INTERACTIVE pause
endlocal
exit /b 0

:open
if exist %1 start "" %1
exit /b 0
