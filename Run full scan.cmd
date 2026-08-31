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
rem  A RULE THIS FILE LEARNED THE HARD WAY: no parentheses in `echo`
rem  text. Inside a parenthesised block cmd treats the first `)` it meets
rem  as the end of the block, so `echo ... (section 1.1).` closed the
rem  block early and left `.` as a stray command. The script died right
rem  after printing the horizon, and the run, the missing-dates page and
rem  the requests never happened. Use a dash or a comma instead.
rem ===========================================================================

setlocal
title Control - full run
cd /d "%~dp0"

rem UTF-8 in the console: Arabic filenames and citations are normal in
rem this output (charter section 4), and the default Windows codepage
rem renders them as mojibake. Files are written UTF-8 either way.
chcp 65001 >nul 2>&1

rem /scheduled: no prompts, no opened documents. A scheduled task that
rem ends on `pause` waits forever with nobody there to press a key, and
rem one that opens documents on an unattended machine leaves them open.
set "INTERACTIVE=1"
if /I "%~1"=="/scheduled" set "INTERACTIVE="

rem CONTROL_ROOT is NOT the repository - on the operating machine it is
rem Documents\UnitedBrothers\CONTROL while this file lives in
rem Documents\Control. setup-laptop.ps1 sets
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
rem Pull THIS branch from origin by name, rather than whatever upstream
rem the local branch happens to be tracking.
rem
rem On 31-Aug-2026 the operating machine sat 28 commits behind for days
rem while reporting "Already up to date" on every run: the local branch
rem was tracking a different remote branch that had not moved, so the
rem pull was correct and pointed at the wrong place. A silent no-op is
rem the worst shape an update failure can take, because nothing looks
rem wrong. Reading the branch name here keeps it from being hardcoded,
rem which was the original reason for a bare `git pull`.
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BRANCH=%%b"
if not defined BRANCH set "BRANCH=HEAD"
if "%BRANCH%"=="HEAD" (
  echo    detached HEAD - not updating. Check out a branch first.
) else (
  echo    branch: %BRANCH%
  git pull --ff-only origin "%BRANCH%"
  if errorlevel 1 (
    echo    no update applied - offline, or local edits in the way.
    echo    Running the version already on disk.
  )
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

rem A transcript, because the summary that matters is at the end of a run
rem that scrolls for hours, and a console buffer is not a record. Tee
rem rather than redirect: a run showing nothing for an hour is
rem indistinguishable from one that has hung.
rem
rem PowerShell only as a subprocess with -Command, never as a script
rem file, so the machine's execution policy is not involved.
set "LOGDIR=%CONTROL_ROOT%\reports\runs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" >nul 2>&1
for /f %%d in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm"') do set "STAMP=%%d"
set "LOG=%LOGDIR%\run-%STAMP%.txt"

powershell -NoProfile -Command "python -m control phase1 --ocr 2>&1 | Tee-Object -FilePath '%LOG%'"

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
echo   Full transcript of this run:
echo     %LOG%
echo.
echo   The gate above names every open item and the one person who can
echo   close it. Control closes none of them by design - section 16:
echo   a gate the system could close alone would not be a gate.
echo.
if defined INTERACTIVE pause
endlocal
