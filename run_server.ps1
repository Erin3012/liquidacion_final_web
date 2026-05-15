$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Error "No existe .venv. Ejecute primero: .\setup_server.ps1"
}

.\.venv\Scripts\python.exe -m uvicorn web_app:app --host 0.0.0.0 --port 8000
