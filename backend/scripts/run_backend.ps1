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

Set-StrictMode -Version Latest
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
    Write-Warning "Virtualenv non trovato in $BackendDir\.venv — uso il Python di sistema."
}

# Legge host e porta direttamente dalle Settings (instance.yaml + env)
$ReadConfig = @"
import sys
sys.path.insert(0, r'$ProjectRoot')
from backend.app.core.config import get_settings
s = get_settings()
print(s.api_host, s.api_port)
"@

$HostPort = python -c $ReadConfig
if ($LASTEXITCODE -ne 0) {
    Write-Error "Impossibile leggere la configurazione. Controlla backend/app/core/config.py e configs/instance.yaml."
    exit 1
}
$Parts   = $HostPort.Trim().Split(' ')
$ApiHost = $Parts[0]
$ApiPort = $Parts[1]

Write-Host "Avvio backend su $ApiHost`:$ApiPort$(if ($Dev) { ' [DEV — reload attivo]' })"

# Costruisce gli argomenti e avvia Uvicorn
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
