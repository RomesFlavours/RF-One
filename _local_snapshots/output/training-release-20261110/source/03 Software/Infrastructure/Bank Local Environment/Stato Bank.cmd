@echo off
REM Stato Bank - local Bank environment (see README.md). Extra arguments are passed through.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" status %*
echo.
pause
