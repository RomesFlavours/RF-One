@echo off
rem Cambio PC: on the PC you leave it closes and saves; on the PC you resume it restores.
rem "Cambio PC.cmd riapri" reopens on the same PC without switching.
setlocal
cd /d "%~dp0"
set "MODE=auto"
if /i "%~1"=="riapri" set "MODE=arrive"
set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3.12"
)
if not defined PY (
  echo BLOCCATO: Python 3.12 non trovato su questo PC. Installarlo da python.org e riprovare.
  pause
  exit /b 1
)
%PY% -B "03 Software\Infrastructure\Local Continuity\cambio_pc.py" %MODE%
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (powershell -NoProfile -Command "[console]::beep(1000,300)") else (powershell -NoProfile -Command "[console]::beep(1000,300);Start-Sleep -m 200;[console]::beep(1000,300);Start-Sleep -m 200;[console]::beep(1000,400)")
pause
exit /b %RC%
