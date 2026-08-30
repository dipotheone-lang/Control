@echo off
rem ===========================================================================
rem  Control - once per machine.
rem
rem  Installs dependencies, creates CONTROL_ROOT from the config templates,
rem  initialises the database and the hash-chained audit log, and sets
rem  CONTROL_ROOT and UB_ROOT for your user - which is what lets every
rem  later run need no paths typed at all.
rem
rem  Safe to re-run. Existing configuration is never overwritten: those
rem  files carry decisions, and a setup script that resets them would
rem  quietly undo a CEO decision (charter section 17).
rem
rem  -ExecutionPolicy Bypass is scoped to this one process. It does not
rem  change the machine's policy.
rem ===========================================================================

setlocal
title Control - first-time setup
cd /d "%~dp0"

echo ===========================================================================
echo   CONTROL - first-time setup
echo ===========================================================================
echo.
echo   This installs what Control needs and points it at the company drive.
echo   Nothing is sent. Nothing outside CONTROL_ROOT is written to.
echo.
echo   If the drive letter is not E:, edit the line below in this file
echo   before running, or pass -UbRoot when calling the script directly.
echo.
pause

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%\scripts\setup-laptop.ps1" -ControlRoot "%HERE%" -UbRoot "E:\UBCSIS Co Date Jan 2026"

echo.
echo ===========================================================================
echo   Setup finished. From now on: double-click "Run Control.cmd".
echo ===========================================================================
echo.
echo   Close this window and open a new one before the first run, so the
echo   CONTROL_ROOT and UB_ROOT variables are picked up.
echo.
pause
endlocal
