@echo off
setlocal
cd /d "%~dp0"
py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32" >nul 2>&1
if errorlevel 1 (
  echo Serve Python 3.12 a 64 bit su questo computer.
  pause
  exit /b 1
)
py -3.12 -B "03 Software\Infrastructure\Local Continuity\continuity.py" check
if errorlevel 1 (
  echo Copia di recupero non completa. Attendi la sincronizzazione OneDrive.
  pause
  exit /b 1
)
set "RFONE_RESUME=%LOCALAPPDATA%\RF-One\Continuity\python312"
if not exist "%RFONE_RESUME%\Scripts\python.exe" py -3.12 -m venv "%RFONE_RESUME%"
"%RFONE_RESUME%\Scripts\python.exe" -m pip install --no-index --find-links "output\local-continuity\current\wheels" -r "output\local-continuity\current\requirements.lock.txt"
if errorlevel 1 (
  echo Dipendenze o sincronizzazione OneDrive incomplete. Nessun database ripristinato.
  pause
  exit /b 1
)
"%RFONE_RESUME%\Scripts\python.exe" -B "03 Software\Infrastructure\Local Continuity\continuity.py" launch
pause
