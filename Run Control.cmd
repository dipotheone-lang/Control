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

rem UTF-8 in the console. The page is bilingual and charter section 4
rem requires both languages in full - on the default Windows codepage the
rem Arabic half renders as mojibake, so half the page is unreadable in the
rem one place somebody actually reads it. The saved file is UTF-8 either
rem way; this is only about the screen. If the console font has no Arabic
rem glyphs, open the saved file instead - the path is printed at the end.
chcp 65001 >nul 2>&1

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

echo == 1 of 3: updating ==
rem The tracking branch, not a named one: a hardcoded branch stops
rem updating the day it is merged and deleted, and does so silently.
git pull --ff-only
if errorlevel 1 (
  echo    no update applied - offline, or local edits in the way.
  echo    Running the version already on disk.
)
python -m pip install -e . --quiet >nul 2>&1

echo.
echo == 2 of 3: the horizon ==
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

rem The other half of the picture, written but not printed. The horizon
rem says how many rules fire no countdown; this says what each one is
rem waiting on and who holds the answer. Printing both every morning
rem would bury the one that changes daily, so this is a file to open on
rem the day somebody chases them.
python -m control statutory --missing --control-root "%CONTROL_ROOT%" >nul 2>&1

rem And the same gaps written as messages to forward. Control drafts and
rem never sends (section 10) - these go out from the CEO, not the system.
python -m control statutory --ask --control-root "%CONTROL_ROOT%" >nul 2>&1

echo.
echo == 3 of 3: the run ==
echo    The horizon above is the page. This is the record: the deadline
echo    engine plans the section 2.1 alerts (T-7, T-3, T-1 and the day
echo    itself), writes them, and posts to the database and the
echo    hash-chained log.
echo.
echo    Nothing is sent. Until Graph is provisioned there is no transport,
echo    so an alert section 10 asks to SEND is written and reported as
echo    NOT DELIVERED - which is the honest state, not a failure of this
echo    run. Watch for that line.
echo.
rem UB_ROOT is not read in this scope. It is passed because the command
rem requires it, and an unreachable one is reported and stepped past
rem rather than halting - nothing here touches the drive.
if not defined UB_ROOT set "UB_ROOT=E:\UBCSIS Co Date Jan 2026"
python -m control cycle --control-root "%CONTROL_ROOT%" --ub-root "%UB_ROOT%" --run-mode SUPERVISED --learning-mode OBSERVE --level 2
if errorlevel 1 (
  echo.
  echo    The run above stopped. The horizon printed earlier still stands -
  echo    it is computed from the calendar alone and does not depend on
  echo    this step.
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

echo   Today's pages:
echo     %CONTROL_ROOT%\reports\statutory-%TODAY%.txt
echo     %CONTROL_ROOT%\reports\statutory-missing-%TODAY%.txt
echo        ^- what each silent rule is waiting on, and who holds the answer.
echo     %CONTROL_ROOT%\reports\statutory-ask-%TODAY%.txt
echo        ^- the same gaps as messages to forward, one per person.
echo.

if defined INTERACTIVE pause
endlocal
exit /b 0

:open
if exist %1 start "" %1
exit /b 0
