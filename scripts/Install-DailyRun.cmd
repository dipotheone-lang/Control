@echo off
rem ===========================================================================
rem  Control - run itself every morning.
rem
rem  Registers a Windows scheduled task so the scan, the registers, the
rem  reports and the gate refresh without anyone opening a terminal.
rem
rem  WHAT THIS IS NOT. It does not make Control live, and it does not
rem  satisfy Phase 2. Decision D-08 is explicit that a transport needing a
rem  powered laptop with Outlook open cannot hold a schedule - a missed
rem  class 1 alert is the charter's most expensive failure - and refuses
rem  this route at startup in SUPERVISED and LIVE. This is a discovery and
rem  dry-run convenience. Graph must be provisioned before Phase 2.
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
echo   Outlook must be open and signed in for the mailbox step to work.
echo   When it is not, that step is skipped and the run says so - it does
echo   not fail silently and it does not record an absence from a partial
echo   sweep (section 5.1).
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
