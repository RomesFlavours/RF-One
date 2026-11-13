@echo off
rem RF-One Selection - prepara la cartella da caricare sull'hosting Aruba (pagina candidati).
rem Chiede la password della casella rfone@romesflavours.com (non viene mostrata ne salvata in OneDrive).
rem La cartella pronta e': %LOCALAPPDATA%\RF-One\Selection\aruba-careers-upload
rem Con "verifica" accende anche check.php per controllare il piano Aruba:
rem     Prepara Pagina Candidati Aruba.cmd verifica
cd /d "%~dp0"
if /i "%~1"=="verifica" (
  python make_upload.py --with-check
) else (
  python make_upload.py
)
echo.
if exist "%LOCALAPPDATA%\RF-One\Selection\aruba-careers-upload" explorer "%LOCALAPPDATA%\RF-One\Selection\aruba-careers-upload"
pause
