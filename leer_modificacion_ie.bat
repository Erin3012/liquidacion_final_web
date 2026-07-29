@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $shell=New-Object -ComObject Shell.Application; $windows=@($shell.Windows()); $found=@(); foreach($w in $windows){if(-not $w.FullName -or [System.IO.Path]::GetFileName($w.FullName) -ine 'iexplore.exe'){continue}; try{$frames=$w.Document.getElementsByTagName('frame')}catch{continue}; for($i=0;$i -lt $frames.length;$i++){try{$frame=$frames.item($i); $text=[string]$frame.contentWindow.document.body.innerText; if($text -match '(?i)RIT\s*:' -and $text -match '(?i)Litigantes'){ $found += [pscustomobject]@{Text=$text; Frame=$i; URL=[string]$frame.contentWindow.location.href} }}catch{}}}; if($found.Count -eq 0){throw 'No se encontr? un marco de IE con RIT y Litigantes. Abra la causa y la secci?n Modificaci?n.'}; Set-Clipboard -Value $found[0].Text; Write-Host ('Datos copiados desde el marco '+$found[0].Frame+'.'); Write-Host 'Vuelva a la aplicaci?n web y pulse Pegar datos SITFA.'"
if errorlevel 1 (
  echo.
  echo No se pudieron copiar los datos desde Internet Explorer.
  pause
  exit /b 1
)
echo.
echo Datos de MODIFICACION copiados correctamente.
pause
