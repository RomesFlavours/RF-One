@echo off
REM Configura PC - local Bank environment (see README.md). Extra arguments are passed through.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" setup %*
echo.
pause
