@echo off
rem RF-One Selection integrato - ambiente locale (RF-One + Selection sullo stesso indirizzo).
rem Dati fuori da OneDrive: %LOCALAPPDATA%\RF-One\Selection
rem --ai --ai-cv: AI attiva su posizioni, messaggi, CV e risposte (autorizzato dal Product Owner il 21/10/2026).
rem L'AI usa AWS Bedrock: se la sessione AWS e' scaduta eseguire "aws login --profile rfone-dev-login".
cd /d "%~dp0"
if "%AWS_PROFILE%"=="" set AWS_PROFILE=rfone-dev-login
rem Codici di verifica candidati: email via SMTP Aruba (configurare una volta: python configure_smtp.py local); SMS solo con un numero registrato su AWS.
if "%RFONE_EMAIL_FROM_ADDRESS%"=="" set RFONE_EMAIL_FROM_ADDRESS=rfone@romesflavours.com
rem set RFONE_SMS_ORIGINATION_IDENTITY=+1XXXXXXXXXX   (da attivare quando il numero AWS sara approvato)
rem Log di ogni avvio/arresto (per capire perche il server si ferma); se Python termina, riavvio automatico.
rem Chiudere questa finestra ferma Selection.
set "SELECTION_LOG=%LOCALAPPDATA%\RF-One\Selection\server.log"
if not exist "%LOCALAPPDATA%\RF-One\Selection" mkdir "%LOCALAPPDATA%\RF-One\Selection"
start "" http://127.0.0.1:5096/selection/
:avvio
echo [%date% %time%] starting server >> "%SELECTION_LOG%"
echo Selection running at http://127.0.0.1:5096/selection/  -  Keep this window open.  Log: %SELECTION_LOG%
python local_server.py --port 5096 --ai --ai-cv >> "%SELECTION_LOG%" 2>&1
echo [%date% %time%] server stopped, code %errorlevel% - restarting in 10 seconds >> "%SELECTION_LOG%"
echo Server stopped (see log). Restarting in 10 seconds...
timeout /t 10 /nobreak >nul
goto avvio
