@echo off
rem C-Bank Prototype: local only, reads the operational Bank read-only.
set "PY=%LOCALAPPDATA%\RF-One\Bank\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Bank Python environment not found: %PY%
  echo Run "Configura PC" of the Bank Local Environment first.
  pause
  exit /b 1
)
start "" http://127.0.0.1:5090/
"%PY%" -I "%~dp0serve.py"
pause
