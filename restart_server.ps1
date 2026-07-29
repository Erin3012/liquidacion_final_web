$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Test-Path -LiteralPath ".\.venv\Scripts\python.exe")) {
    Write-Error "No existe .venv. Ejecute primero: .\setup_server.ps1"
}

Get-CimInstance Win32_Process |
Where-Object { $_.CommandLine -like '*uvicorn web_app:app*' -and $_.Name -like 'python*' } |
ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

$certFile = Join-Path $ProjectDir "certs\liquidacion-local.pem"
$keyFile = Join-Path $ProjectDir "certs\liquidacion-local-key.pem"
$useHttps = (Test-Path -LiteralPath $certFile) -and (Test-Path -LiteralPath $keyFile)
$serverArgs = '-m uvicorn web_app:app --host 0.0.0.0 --port 8000'
if ($useHttps) { $serverArgs += " --ssl-certfile `"$certFile`" --ssl-keyfile `"$keyFile`"" }

Start-Process -WindowStyle Hidden `
    -FilePath ".\.venv\Scripts\python.exe" `
    -ArgumentList $serverArgs `
    -WorkingDirectory $ProjectDir

Start-Sleep -Seconds 3

$scheme = if ($useHttps) { "https" } else { "http" }
$url = "${scheme}://127.0.0.1:8000/"
try {
    if ($useHttps) { $response = & curl.exe -k -s -o NUL -w "%{http_code}" $url } else { $response = (Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 10).StatusCode }
    Write-Host "Servidor reiniciado correctamente. Estado: $response"
    Write-Host "URL local: $url"
} catch {
    Write-Error "El servidor se inició, pero no respondió en http://127.0.0.1:8000/. Revise firewall, puerto o errores de Uvicorn."
}
