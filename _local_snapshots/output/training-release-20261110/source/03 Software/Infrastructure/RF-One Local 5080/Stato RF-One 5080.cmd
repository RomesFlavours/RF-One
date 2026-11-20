@echo off
REM Stato di RF-One sulla 5080 (see README.md). Changes nothing.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" status %*
echo.
pause
