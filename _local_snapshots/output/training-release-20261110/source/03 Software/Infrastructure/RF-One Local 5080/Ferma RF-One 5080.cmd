@echo off
REM Ferma RF-One sulla 5080 (see README.md). Extra arguments are passed through.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" stop %*
echo.
pause
