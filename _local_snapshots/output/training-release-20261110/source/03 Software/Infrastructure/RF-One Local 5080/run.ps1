# Runs rfone_local.py with THIS PC's Python (Bank Local Environment\machines\<COMPUTERNAME>.json).
# Used by the .cmd files; arguments are passed through (e.g. "start", "stop --port 5080").
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$machine = Join-Path $here ("..\Bank Local Environment\machines\" + $env:COMPUTERNAME + ".json")
if (-not (Test-Path $machine)) {
    Write-Host "Questo PC ($env:COMPUTERNAME) non e' configurato: esegui prima 'Configura PC.cmd' del Bank Local Environment."
    exit 1
}
$python = (Get-Content $machine -Raw | ConvertFrom-Json).python
if (-not (Test-Path $python)) { Write-Host "Python indicato nel file macchina non trovato: $python"; exit 1 }
& $python (Join-Path $here "rfone_local.py") @args
exit $LASTEXITCODE
