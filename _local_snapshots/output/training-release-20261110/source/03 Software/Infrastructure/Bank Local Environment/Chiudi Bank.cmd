@echo off
REM Chiudi Bank - local Bank environment (see README.md). Extra arguments are passed through.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" close %*
echo.
pause
