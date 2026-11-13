from pathlib import Path
import json, secrets, shutil, socket, subprocess, sys

statefile=Path(__file__).with_name('copy_employee_directory_aws.json')
d=json.loads(statefile.read_text(encoding='utf-8'));root=Path(d['folder'])
assert d['phases']['restore']=='ALL_TABLE_COUNTS_AND_DIRECTORY_HASHES_VERIFIED'
port=5094
while True:
    sock=socket.socket()
    try:sock.bind(('127.0.0.1',port));sock.close();break
    except OSError:sock.close();port+=1
d['web_port']=port
d['local_url']=f'http://127.0.0.1:{port}/administration/employees'
(root/'verification.json').write_text(json.dumps(d,indent=2),encoding='utf-8')
shutil.copyfile(Path(__file__).with_name('employee_directory_local_launcher.py'),root/'launch_local.py')
(root/'local-session.key').write_text(secrets.token_urlsafe(48),encoding='utf-8')
for name in ('disabled-aws-config','disabled-aws-credentials'):(root/name).write_text('',encoding='utf-8')
start=r'''$ErrorActionPreference = 'Stop'
$copyRoot = $PSScriptRoot
$pgControl = Join-Path $copyRoot 'runtime\pgsql\bin\pg_ctl.exe'
$pgData = Join-Path $copyRoot 'postgres-data'
& $pgControl -D $pgData status *> $null
if ($LASTEXITCODE -ne 0) {
    & $pgControl -D $pgData -l (Join-Path $copyRoot 'postgres.log') -w start
    if ($LASTEXITCODE -ne 0) { throw 'Local PostgreSQL did not start.' }
}
$copyState = Get-Content -LiteralPath (Join-Path $copyRoot 'verification.json') -Raw | ConvertFrom-Json
$alreadyRunning = $false
$pidPath = Join-Path $copyRoot 'web.pid'
if (Test-Path -LiteralPath $pidPath) {
    $savedPid = [int](Get-Content -LiteralPath $pidPath)
    $existing = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    $alreadyRunning = $existing -and $existing.CommandLine -and $existing.CommandLine.Contains((Join-Path $copyRoot 'launch_local.py'))
}
if (-not $alreadyRunning) {
    $arguments = '"' + (Join-Path $copyRoot 'launch_local.py') + '"'
    $process = Start-Process -FilePath '__PYTHON__' -ArgumentList $arguments -WorkingDirectory $copyRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $copyRoot 'web.stdout.log') -RedirectStandardError (Join-Path $copyRoot 'web.stderr.log')
    Set-Content -LiteralPath $pidPath -Value $process.Id
}
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try { $result = Invoke-WebRequest -Uri $copyState.local_url -UseBasicParsing -TimeoutSec 2; break }
    catch { Start-Sleep -Milliseconds 500 }
}
Start-Process $copyState.local_url
'''.replace('__PYTHON__',sys.executable.replace("'","''"))
stop=r'''$ErrorActionPreference = 'Stop'
$copyRoot = $PSScriptRoot
$pidPath = Join-Path $copyRoot 'web.pid'
if (Test-Path -LiteralPath $pidPath) {
    $savedPid = [int](Get-Content -LiteralPath $pidPath)
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $savedPid" -ErrorAction SilentlyContinue
    if ($process -and $process.CommandLine -and $process.CommandLine.Contains((Join-Path $copyRoot 'launch_local.py'))) {
        Stop-Process -Id $savedPid
    }
    Remove-Item -LiteralPath $pidPath
}
& (Join-Path $copyRoot 'runtime\pgsql\bin\pg_ctl.exe') -D (Join-Path $copyRoot 'postgres-data') -m fast -w stop
'''
(root/'Avvia Anagrafica.ps1').write_text(start,encoding='utf-8-sig')
(root/'Ferma Anagrafica.ps1').write_text(stop,encoding='utf-8-sig')
for verb in ('Avvia','Ferma'):
    (root/f'{verb} Anagrafica.cmd').write_text('@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0'+verb+' Anagrafica.ps1"\r\n',encoding='ascii')
check=subprocess.run([sys.executable,str(root/'launch_local.py'),'--check'],capture_output=True,text=True)
if check.returncode:
    (root/'local-check-error.log').write_text(check.stderr,encoding='utf-8')
    print(check.stderr[-5000:]);raise SystemExit(check.returncode)
smoke=json.loads(check.stdout.strip().splitlines()[-1])
d['local_smoke_test']=smoke;d['status']='COMPLETE';d['phases']['local_app']='AUTHENTICATED_DIRECTORY_AND_DETAIL_HTTP_200'
for file in (statefile,root/'verification.json'):file.write_text(json.dumps(d,indent=2),encoding='utf-8')
(root/'README.txt').write_text(f'''ANAGRAFICA RF1 — COPIA LOCALE DA AWS

Snapshot: {d['database']['snapshot_time']}
Immagine effettivamente copiata: {d['image_digest']}
Schema: {', '.join(d['database']['schema_revision'])}
Database completo condiviso: {len(d['database']['tables'])} tabelle, {sum(v['rows'] for v in d['database']['tables'].values())} righe.
Codice estratto dall'immagine AWS in source/; nessuna modifica ai suoi file.
Il pacchetto S3 aws-build-source.zip e conservato separatamente: puo differire dall'immagine online.

AVVIO: doppio clic su Avvia Anagrafica.cmd
ARRESTO: doppio clic su Ferma Anagrafica.cmd
Pagina: {d['local_url']}
Accesso locale diretto, senza login o firma, con sessione automatica dell’owner/amministratore copiato.
Le modifiche eseguite qui riguardano esclusivamente questa copia locale.

PostgreSQL portatile incluso, solo 127.0.0.1:{d['local_database']['port']}.
Launcher locale esterno ai sorgenti: integrazioni AWS/Clover e sincronizzazioni disabilitate.
Non vengono avviati worker, migrazioni, seed o sincronizzazioni automatiche.
L'interfaccia locale espone Anagrafica, account e login; gli altri moduli non sono avviati.
Il dump condiviso include i dati degli altri moduli per conservare i riferimenti.
Gli allegati S3 degli altri moduli non fanno parte di questa copia Anagrafica.
Non copiare questa cartella su Git/OneDrive e non trasferire il database locale verso AWS.

VERIFICA: tutte le tabelle hanno lo stesso numero di righe della snapshot.
Hash dei contenuti verificati per dipendenti, collegamenti, alias, account e turni.
Lista e scheda dipendente verificate con sessione di test locale autorizzata (HTTP 200).
Hash dei file e del dump, provenienza e dettagli in verification.json.
Dump di ripristino iniziale: rfone-aws.dump. Contiene dati personali e hash di account.
La regola di rete temporanea creata per l'export e stata rimossa.
Nessuna scrittura sul database AWS e nessun deploy.
''',encoding='utf-8')
print(json.dumps({'folder':str(root),'url':d['local_url'],'check':smoke},indent=2))
