@echo off

cd /d "%~dp0"

if exist "%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe" (
  "%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe" -B "%~dp0local_server.py" --port 5096
) else (
  py -3.12 -B "%~dp0local_server.py" --port 5096
)

pause

