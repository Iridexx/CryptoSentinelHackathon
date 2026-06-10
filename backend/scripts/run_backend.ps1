<#
.SYNOPSIS
    Avvia il backend CryptoSentinel con Uvicorn.

.PARAMETER Dev
    Abilita --reload di Uvicorn (solo sviluppo locale, non usare in produzione).

.EXAMPLE
    .\backend\scripts\run_backend.ps1
    .\backend\scripts\run_backend.ps1 -Dev
#>
param(
    [switch]$Dev
)

$ErrorActionPreference = "Stop"

# Radice del progetto = due livelli sopra backend/scripts/
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Split-Path -Parent $ScriptDir
$ProjectRoot = Split-Path -Parent $BackendDir

# Attiva il virtualenv se presente
$VenvActivate = Join-Path $BackendDir ".venv\Scripts\Activate.ps1"
if (Test-Path $VenvActivate) {
    . $VenvActivate
} else {
    Write-Warning "Virtualenv non trovato in $BackendDir\.venv -- uso il Python di sistema."
}

# Imposta PYTHONPATH cosi' Python trova il package backend
$env:PYTHONPATH = $ProjectRoot

# Legge host e porta dalle Settings (instance.yaml + env) senza duplicare valori
$HostPort = python -c "from backend.app.core.config import get_settings; s=get_settings(); print(s.api_host, s.api_port)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "Impossibile leggere la configurazione."
    exit 1
}
$Parts   = $HostPort.Trim().Split(' ')
$ApiHost = $Parts[0]
$ApiPort = $Parts[1]

$DevLabel = if ($Dev) { ' [DEV - reload attivo]' } else { '' }
Write-Host "Avvio backend su $ApiHost`:$ApiPort$DevLabel"

$UvicornArgs = @(
    "-m", "uvicorn",
    "backend.app.main:app",
    "--host", $ApiHost,
    "--port", $ApiPort
)
if ($Dev) {
    $UvicornArgs += "--reload"
}

Set-Location $ProjectRoot
& python @UvicornArgs
