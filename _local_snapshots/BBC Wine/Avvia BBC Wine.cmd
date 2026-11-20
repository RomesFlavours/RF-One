@echo off
rem Starts BBC Wine locally (127.0.0.1:5110) and opens it in Microsoft Edge, already signed in.
cd /d "%~dp0"
start "BBC Wine" /min python launch_local.py
timeout /t 3 /nobreak >nul
start msedge "http://127.0.0.1:5110/local/start?next=/orders"
