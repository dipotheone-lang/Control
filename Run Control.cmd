@echo off
rem ===========================================================================
rem  Control - everything the machine can do, in one double-click.
rem
rem  A .cmd rather than a PowerShell script on purpose: a .ps1 can be
rem  refused by the machine's execution policy, and a runner that needs a
rem  policy change before it will start is not a runner you can hand to
rem  somebody. This needs nothing but a double-click.
rem
rem  It sends no mail. Every outbound message Control produces is a draft
rem  in outbox\pending-approval, in every mode, with no override for
rem  urgency or seniority (charter section 10).
rem ===========================================================================

setlocal
title Control - full run
cd /d "%~dp0"

rem /scheduled: no prompts, no opened documents. A scheduled task that
rem ends on `pause` waits forever with nobody there to press a key, and
rem one that opens documents on an unattended machine leaves them open.
set "INTERACTIVE=1"
if /I "%~1"=="/scheduled" set "INTERACTIVE="

rem The repository is CONTROL_ROOT on this machine. setup-laptop.ps1 sets
rem both variables for the user; these defaults only cover the case where
rem it has not been run yet, so the file works on a fresh checkout.
rem %~dp0 ends in a backslash, and a quoted path ending in one escapes
rem the closing quote. Strip it once here rather than in five places.
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
if not defined CONTROL_ROOT set "CONTROL_ROOT=%HERE%"
if not defined UB_ROOT set "UB_ROOT=E:\UBCSIS Co Date Jan 2026"

echo ===========================================================================
echo   CONTROL - full run
echo ===========================================================================
echo   CONTROL_ROOT : %CONTROL_ROOT%
echo   UB_ROOT      : %UB_ROOT%
echo.
echo   Before this runs: open CLASSIC Outlook and leave it signed in.
echo   The new Outlook app has no automation interface, so the mailbox
echo   step will be skipped and say so.
echo.
echo   Nothing here sends mail.
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
echo == 2 of 3: is this machine ready ==
python -m control doctor
if errorlevel 1 (
  echo.
  echo    doctor reported something missing above. The run continues:
  echo    each step is skipped rather than fatal when its input is absent,
  echo    and the summary at the end names what was skipped.
)

echo.
echo == 3 of 3: the run ==
echo    Mailbox scan, drive scan, contract terms, registers, golden-set
echo    cases, a full dry run, the reports, and the gate. This takes a
echo    while - OCR on scanned contracts is most of it.
echo.
python -m control phase1 --ocr

echo.
echo ===========================================================================
echo   DONE - opening what was produced
echo ===========================================================================

rem The two documents worth reading, in the order the charter puts them.
rem Section 6 says to read the commercial exposure first: it will contain
rem dates needing action before the system is even finished.
if defined INTERACTIVE (
  if exist "%CONTROL_ROOT%\discovery\COMMERCIAL-EXPOSURE.md" (
    start "" "%CONTROL_ROOT%\discovery\COMMERCIAL-EXPOSURE.md"
  )
  if exist "%CONTROL_ROOT%\discovery\PROPOSED-CLASS2-REGISTERS.md" (
    start "" "%CONTROL_ROOT%\discovery\PROPOSED-CLASS2-REGISTERS.md"
  )
)

echo.
echo   The gate above names every open item and the one person who can
echo   close it. Control closes none of them by design (section 16):
echo   a gate the system could close alone would not be a gate.
echo.
if defined INTERACTIVE pause
endlocal
