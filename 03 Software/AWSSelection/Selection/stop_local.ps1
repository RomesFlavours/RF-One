$selectionScript = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'local_server.py')).Path
$selectionProcesses = Get-CimInstance Win32_Process -Filter "name = 'python.exe'" | Where-Object {
    $_.CommandLine -and $_.CommandLine.Contains($selectionScript) -and $_.CommandLine -match '--port\s+5096'
}
$selectionProcesses | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
Write-Output 'Selezione locale arrestata. RFBank e il database condiviso non sono stati arrestati.'
