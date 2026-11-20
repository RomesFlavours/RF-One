<#
    RF-One dev AWS access check/login.

    Verifies AWS CLI access for the RF-One dev environment (profile, region,
    account below) and only starts an interactive "aws login" when the
    current credentials are actually missing/expired. See README.md in this
    folder for the full operational reference (command, expected values,
    verified URLs).

    Usage (from a PowerShell prompt, any working directory):
        & "<repo>\03 Software\Infrastructure\aws-dev-access.ps1"           # default: local-browser login if renewal is needed
        & "<repo>\03 Software\Infrastructure\aws-dev-access.ps1" -Remote   # device-code login if renewal is needed

    -Remote runs "aws login --remote": it disables the local callback
    browser flow and instead prints a URL plus an authorization code to
    paste back into this terminal. Use it explicitly when the default
    local-browser flow is not viable (e.g. remote/SSH session).
#>

[CmdletBinding()]
param(
    [switch]$Remote
)

$ErrorActionPreference = 'Stop'

# Fixed dev-environment values for this repository. Do not parameterize on
# the command line - edit this file if the dev environment changes.
$AwsExe          = 'C:\Program Files\Amazon\AWSCLIV2\aws.exe'
$AwsProfile      = 'rfone-dev-login'
$AwsRegion       = 'us-east-1'
$ExpectedAccount = '418674484214'

function Invoke-CallerIdentity {
    $errFile = [System.IO.Path]::GetTempFileName()
    try {
        $stdout = & $AwsExe sts get-caller-identity --profile $AwsProfile --region $AwsRegion --output json 2>$errFile
        $exitCode = $LASTEXITCODE
        $stderrText = (Get-Content -Path $errFile -Raw -ErrorAction SilentlyContinue)
    }
    finally {
        Remove-Item -Path $errFile -Force -ErrorAction SilentlyContinue
    }

    $account = $null
    $arn = $null
    if ($exitCode -eq 0) {
        try {
            $parsed = ($stdout -join "`n") | ConvertFrom-Json
            $account = $parsed.Account
            $arn = $parsed.Arn
        }
        catch {
            $exitCode = 1
            $stderrText = "Impossibile interpretare l'output di sts get-caller-identity: $($_.Exception.Message)"
        }
    }

    [pscustomobject]@{
        ExitCode = $exitCode
        Account  = $account
        Arn      = $arn
        StdErr   = ($stderrText -join "`n")
    }
}

function Test-AnyPattern($text, [string[]]$patterns) {
    foreach ($p in $patterns) {
        if ($text -match $p) { return $true }
    }
    return $false
}

Write-Host "RF-One - verifica accesso AWS" -ForegroundColor Cyan
Write-Host "Profilo: $AwsProfile | Regione: $AwsRegion | Account atteso: $ExpectedAccount"
Write-Host ""

$result = Invoke-CallerIdentity

if ($result.ExitCode -eq 0 -and $result.Account -eq $ExpectedAccount) {
    Write-Host "AWS pronto: account $($result.Account) confermato ($($result.Arn)). Nessun login necessario." -ForegroundColor Green
    exit 0
}

if ($result.ExitCode -eq 0 -and $result.Account) {
    Write-Host "ERRORE: account AWS inatteso." -ForegroundColor Red
    Write-Host "  Atteso : $ExpectedAccount"
    Write-Host "  Trovato: $($result.Account) ($($result.Arn))"
    Write-Host "Login NON avviato: verificare profilo/configurazione prima di procedere." -ForegroundColor Yellow
    exit 2
}

# get-caller-identity failed outright: classify before deciding whether a
# renewal login is appropriate, per the "no unnecessary login cycles" rule.
$err = $result.StdErr

$networkPatterns    = @('Could not connect', 'Connection refused', 'timed out', 'Name or service not known', 'getaddrinfo', 'EndpointConnectionError', 'Could not connect to the endpoint')
$configPatterns     = @('could not be found', 'Unknown options', 'is not recognized', 'The config profile', 'command not found')
$permissionPatterns = @('AccessDenied', 'is not authorized to perform')
$credentialPatterns = @('Expired', 'InvalidClientTokenId', 'security token included in the request is invalid', 'Unable to locate credentials', 'could not be refreshed', 'RefreshFailed', 'No cached credentials', 'not logged in')

if (Test-AnyPattern $err $networkPatterns) {
    Write-Host "ERRORE di rete durante la verifica AWS. Login NON avviato." -ForegroundColor Red
    Write-Host $err
    exit 3
}
if (Test-AnyPattern $err $configPatterns) {
    Write-Host "ERRORE di configurazione (profilo/regione/eseguibile AWS CLI). Login NON avviato." -ForegroundColor Red
    Write-Host $err
    exit 3
}
if (Test-AnyPattern $err $permissionPatterns) {
    Write-Host "ERRORE di permessi. Login NON avviato: non e' un problema risolvibile con un nuovo login." -ForegroundColor Red
    Write-Host $err
    exit 3
}
if (-not (Test-AnyPattern $err $credentialPatterns)) {
    Write-Host "ERRORE non riconosciuto durante la verifica AWS. Login NON avviato per prudenza." -ForegroundColor Red
    Write-Host $err
    exit 3
}

# Credentials missing/expired: this is the one case where starting a login is appropriate.
Write-Host "Credenziali AWS assenti o scadute per il profilo '$AwsProfile'. Avvio il login..." -ForegroundColor Yellow
Write-Host ""

if ($Remote) {
    Write-Host "ISTRUZIONI (login --remote, tramite codice):" -ForegroundColor Cyan
    Write-Host "  1) Apri nel browser l'URL che sta per essere mostrato e accedi alla AWS Management Console."
    Write-Host "  2) Torna qui SOLO per incollare il codice di autorizzazione quando richiesto (nessuna password va incollata qui)."
    Write-Host ""
    & $AwsExe login --profile $AwsProfile --remote
}
else {
    Write-Host "ISTRUZIONI (login con browser locale):" -ForegroundColor Cyan
    Write-Host "  1) Si aprira' automaticamente il browser: accedi alla AWS Management Console."
    Write-Host "  2) Non incollare nulla nel terminale: al termine del login nel browser questo comando prosegue da solo."
    Write-Host "     Se il browser non si apre (es. sessione remota), interrompi e rilancia con: -Remote"
    Write-Host ""
    & $AwsExe login --profile $AwsProfile
}
$loginExitCode = $LASTEXITCODE

Write-Host ""
Write-Host "Login terminato (codice $loginExitCode). Verifico di nuovo identita' e account..." -ForegroundColor Cyan

$result2 = Invoke-CallerIdentity

if ($result2.ExitCode -eq 0 -and $result2.Account -eq $ExpectedAccount) {
    Write-Host "AWS pronto: account $($result2.Account) confermato ($($result2.Arn))." -ForegroundColor Green
    exit 0
}
elseif ($result2.ExitCode -eq 0 -and $result2.Account) {
    Write-Host "ERRORE: dopo il login l'account risulta $($result2.Account), atteso $ExpectedAccount." -ForegroundColor Red
    exit 2
}
else {
    Write-Host "ERRORE: la verifica di identita' AWS fallisce ancora dopo il login." -ForegroundColor Red
    Write-Host $result2.StdErr
    exit 1
}
