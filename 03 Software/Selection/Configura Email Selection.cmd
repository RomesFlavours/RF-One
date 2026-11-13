@echo off
rem Configura una sola volta l email di Selection (codici di verifica ai candidati) sulla casella Aruba rfone@romesflavours.com.
rem Chiede la password (non viene mostrata), la prova con un messaggio verso rfone@romesflavours.com,
rem poi la salva protetta su questo PC e in AWS Secrets Manager. La password non viene mai scritta in chiaro.
cd /d "%~dp0"
if "%AWS_PROFILE%"=="" set AWS_PROFILE=rfone-dev-login
python configure_smtp.py setup
pause
