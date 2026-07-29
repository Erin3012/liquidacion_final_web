$ErrorActionPreference = "Stop"
function Get-Text($value) { if ($null -eq $value) { return "" }; return ([string]$value).Trim() }
$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object { $_.FullName -and ([System.IO.Path]::GetFileName($_.FullName) -ieq "iexplore.exe") })
if ($windows.Count -eq 0) { throw "No se encontró una ventana de Internet Explorer abierta." }
$candidates = @($windows | Where-Object { (Get-Text $_.LocationName) -match "MODIFICACION" -or (Get-Text $_.LocationURL) -match "MODIFICACION" })
$window = if ($candidates.Count -gt 0) { $candidates[0] } elseif ($windows.Count -eq 1) { $windows[0] } else { throw "Hay varias ventanas de Internet Explorer y no se identificó una llamada MODIFICACION." }
$body = $window.Document.body
if ($null -eq $body) { throw "La ventana encontrada todavía no tiene contenido disponible." }
$text = Get-Text $body.innerText
if ([string]::IsNullOrWhiteSpace($text)) { throw "La ventana MODIFICACION no contiene texto para copiar." }
Set-Clipboard -Value $text
Write-Host "Datos de MODIFICACION copiados al portapapeles."
Write-Host "Ahora vuelve a la aplicación web y pulsa 'Pegar datos SITFA'."
