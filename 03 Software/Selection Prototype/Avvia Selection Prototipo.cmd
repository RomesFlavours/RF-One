@echo off
rem RF-One Selection AI - prototipo locale.
rem --ai    : l'AI propone posizioni e messaggi (nessun dato dei candidati inviato).
rem --ai-cv : attivo su richiesta del Product Owner (21/10/2026): l'AI legge CV e risposte dei candidati.
rem L'AI usa il fornitore configurato in .env (oggi AWS Bedrock): se la sessione AWS e' scaduta eseguire "aws login".
cd /d "%~dp0"
start "" http://127.0.0.1:5095/
python app.py --port 5095 --ai --ai-cv
pause
