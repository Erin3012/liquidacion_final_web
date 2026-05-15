$ErrorActionPreference = "Stop"

Get-CimInstance Win32_Process |
Where-Object { $_.CommandLine -like '*uvicorn web_app:app*' -and $_.Name -like 'python*' } |
ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

Write-Host "Servidor detenido."
