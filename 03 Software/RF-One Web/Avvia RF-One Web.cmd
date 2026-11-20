@echo off
rem Starts RF-One Web on this PC (see local_server.py). Local data stays in
rem %LOCALAPPDATA%\RF-One\RF-One Web\, outside OneDrive. Close this window to stop.
cd /d "%~dp0"
where py >nul 2>nul && (py -3.12 local_server.py %*) || (python local_server.py %*)
pause
