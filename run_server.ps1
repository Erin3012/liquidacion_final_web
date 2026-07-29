$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Error "No existe .venv. Ejecute primero: .\setup_server.ps1"
}

$certFile = Join-Path $ProjectDir "certs\liquidacion-local.pem"
$keyFile = Join-Path $ProjectDir "certs\liquidacion-local-key.pem"
if ((Test-Path -LiteralPath $certFile) -and (Test-Path -LiteralPath $keyFile)) {
    .\.venv\Scripts\python.exe -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --ssl-certfile $certFile --ssl-keyfile $keyFile
} else {
    .\.venv\Scripts\python.exe -m uvicorn web_app:app --host 0.0.0.0 --port 8000
}
