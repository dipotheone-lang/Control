@echo off
rem ===========================================================================
rem  Control - run itself every morning.
rem
rem  Registers a Windows scheduled task so the statutory horizon is on
rem  screen every morning without anyone opening a terminal.
rem
rem  WHAT THIS IS NOT. It does not make Control live, and it does not
rem  satisfy Phase 2. The scheduled run produces a page on this machine;
rem  it does not deliver an alert to anybody. Decision D-08 is explicit
rem  that a transport needing a powered laptop cannot carry a class 1
rem  alert - the charter's most expensive failure - and refuses that
rem  route at startup in SUPERVISED and LIVE. Graph must be provisioned
rem  before anything sends on a schedule.
rem
rem  So this is a habit, not a control: it puts the horizon in front of
rem  somebody daily. If nobody reads the page, nothing has been alerted.
rem
rem  The run sends nothing, in any mode (section 10).
rem ===========================================================================

setlocal
cd /d "%~dp0.."

set "TASK=Control daily run"
set "AT=07:00"

echo Registering "%TASK%" to run every day at %AT%.
echo   It runs: "%CD%\Run Control.cmd" /scheduled
echo.
echo   That reads config\statutory-calendar.yaml and nothing else. No
echo   mailbox, no drive scan, no OCR (decision D-15), so it does not
echo   need Outlook open or E: plugged in, and it takes seconds.
echo.
echo   It writes reports\statutory-YYYY-MM-DD.txt and stops there.
echo.

schtasks /Create /TN "%TASK%" /TR "\"%CD%\Run Control.cmd\" /scheduled" /SC DAILY /ST %AT% /F
if errorlevel 1 (
  echo.
  echo   Could not register the task. The usual cause is that this window
  echo   is not elevated: right-click this file and Run as administrator.
) else (
  echo.
  echo   Registered. To remove it later:
  echo     schtasks /Delete /TN "%TASK%" /F
)
echo.
pause
endlocal
