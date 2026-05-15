$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Error "No existe .venv. Ejecute primero: .\setup_server.ps1"
}

Get-CimInstance Win32_Process |
Where-Object { $_.CommandLine -like '*uvicorn web_app:app*' -and $_.Name -like 'python*' } |
ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Start-Process -WindowStyle Hidden `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","web_app:app","--host","0.0.0.0","--port","8000" `
    -WorkingDirectory $ProjectDir

Start-Sleep -Seconds 3

try {
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 10
    Write-Host "Servidor reiniciado correctamente. Estado: $($response.StatusCode)"
    Write-Host "URL local: http://127.0.0.1:8000/"
} catch {
    Write-Error "El servidor se inició, pero no respondió en http://127.0.0.1:8000/. Revise firewall, puerto o errores de Uvicorn."
}
