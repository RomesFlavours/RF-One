@echo off
setlocal
cd /d "%~dp0"
if exist "%LOCALAPPDATA%\RF-One\Continuity\python312\Scripts\python.exe" (
  "%LOCALAPPDATA%\RF-One\Continuity\python312\Scripts\python.exe" -B "03 Software\Infrastructure\Local Continuity\continuity.py" prepare-switch
) else (
  py -3.12 -B "03 Software\Infrastructure\Local Continuity\continuity.py" prepare-switch
)
pause
