@echo off
rem ===========================================================================
rem  Control - run itself every morning.
rem
rem  Registers a Windows scheduled task so the statutory horizon is on
rem  screen every morning without anyone opening a terminal.
rem
rem  WHAT THIS IS AND IS NOT. It does not make Control live and it does
rem  not satisfy Phase 2. Under decision D-58 the scheduled run does
rem  send class 1 alerts, through Outlook, to ubcsis.com addresses only.
rem
rem  The cost of that route is written into D-58 and is not softened
rem  here: Outlook needs this laptop awake with Outlook running. On the
rem  day a filing falls due with the machine asleep, nobody is told. The
rem  alert is written UNDELIVERED, never marked sent, and attempted
rem  again on the next run - so missing T-7 does not silence T-3, T-1
rem  and the day itself. A repeat failure on the same alert is reported
rem  separately, because one miss is a closed laptop and a repeat is the
rem  transport.
rem
rem  So a scheduled task is not the same as a delivered alert. 07:00
rem  only helps on a morning the laptop is on at 07:00.
rem
rem  Everything the charter holds at DRAFT stays a draft, and the
rem  external gate never opens, by any route, in any mode - section 10.
rem ===========================================================================

setlocal
cd /d "%~dp0.."

set "TASK=Control daily run"
set "AT=07:00"

echo Registering "%TASK%" to run every day at %AT%.
echo   It runs: "%CD%\Run Control.cmd" /scheduled
echo.
echo   That reads config\statutory-calendar.yaml and nothing else. No
echo   mailbox, no drive scan, no OCR - decision D-15 - so it does not
echo   need E: plugged in, and it takes seconds.
echo.
echo   It writes reports\statutory-YYYY-MM-DD.txt, plus the missing-dates
echo   page and the requests to forward, and posts the run to the
echo   database and the hash-chained log.
echo.
echo   Class 1 alerts go out through Outlook - D-58 - so Outlook does
echo   need to be running at 07:00 for anything to be delivered. If it
echo   is not, the alert is written UNDELIVERED and retried, never
echo   marked sent.
echo.

rem Register through PowerShell first. schtasks can only say "07:00 or
rem not at all", and a laptop asleep at 07:00 loses the whole day's
rem alerts. The PowerShell path sets StartWhenAvailable, so a missed
rem 07:00 runs at the next opportunity instead of being skipped.
powershell -NoProfile -ExecutionPolicy Bypass -File "%CD%\scripts\install-daily-run.ps1" -RepoRoot "%CD%" -TaskName "%TASK%" -At %AT%
if not errorlevel 1 goto :done

echo.
echo   PowerShell registration did not succeed. Falling back to schtasks,
echo   which registers the same 07:00 run WITHOUT the catch-up: if the
echo   laptop is asleep at 07:00 that morning is skipped entirely.
echo.
schtasks /Create /TN "%TASK%" /TR "\"%CD%\Run Control.cmd\" /scheduled" /SC DAILY /ST %AT% /F
if errorlevel 1 (
  echo.
  echo   Could not register the task either way. The usual cause is that
  echo   this window is not elevated: right-click this file and Run as
  echo   administrator.
  echo.
  pause
  endlocal
  exit /b 1
)

:done
echo.
echo   To remove it later:
echo     schtasks /Delete /TN "%TASK%" /F
echo.
pause
endlocal
