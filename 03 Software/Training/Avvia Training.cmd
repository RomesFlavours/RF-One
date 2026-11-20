@echo off
cd /d "%~dp0..\RF-One Web"
python training_local.py --serve
pause
