# Runs bank_local_env with THIS PC's Python (machines\<COMPUTERNAME>.json), from this folder.
# Used by the .cmd files; arguments are passed through (e.g. "start --migrate").
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$machine = Join-Path $here ("machines\" + $env:COMPUTERNAME + ".json")
if (Test-Path $machine) {
    $python = (Get-Content $machine -Raw | ConvertFrom-Json).python
} elseif ($args.Count -gt 0 -and $args[0] -eq "setup") {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) { Write-Host "Python 3.12 non trovato: installalo, poi rilancia Configura PC."; exit 1 }
} else {
    Write-Host "Questo PC ($env:COMPUTERNAME) non e' configurato: esegui prima 'Configura PC.cmd'."
    exit 1
}
if (-not (Test-Path $python)) { Write-Host "Python indicato nel file macchina non trovato: $python"; exit 1 }
Push-Location $here
try {
    & $python -m bank_local_env @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
