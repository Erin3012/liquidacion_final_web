$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "No se encontró Python en PATH. Instale Python 3.11+ y vuelva a ejecutar este script."
}

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Host "Creando entorno virtual..."
    python -m venv .venv
}

Write-Host "Instalando dependencias..."
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Verificando sintaxis..."
.\.venv\Scripts\python.exe -m py_compile calculation_engine.py cartola_parser.py config.py pdf_engine.py utils.py web_app.py

Write-Host "Iniciando servidor..."
.\restart_server.ps1

Write-Host ""
Write-Host "Servidor iniciado en:"
Write-Host "http://localhost:8000/"
Write-Host ""
Write-Host "Para otros equipos de la red use:"
Write-Host "http://NOMBRE-O-IP-DE-ESTE-EQUIPO:8000/"
