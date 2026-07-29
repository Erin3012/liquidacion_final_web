@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $shell=New-Object -ComObject Shell.Application; $windows=@($shell.Windows()); $found=@(); foreach($w in $windows){if(-not $w.FullName -or [System.IO.Path]::GetFileName($w.FullName) -ine 'iexplore.exe'){continue}; try{$frames=$w.Document.getElementsByTagName('frame')}catch{continue}; for($i=0;$i -lt $frames.length;$i++){try{$frame=$frames.item($i); $text=[string]$frame.contentWindow.document.body.innerText; if($text -match '(?i)RIT\s*:' -and $text -match '(?i)Litigantes'){ $found += [pscustomobject]@{Text=$text; Frame=$i; URL=[string]$frame.contentWindow.location.href} }}catch{}}}; if($found.Count -eq 0){throw 'No se encontro un marco de IE con RIT y Litigantes.'}; $text=$found[0].Text; $url=$found[0].URL; $rit=''; $tribunal=''; $dte=''; $ddo=''; if($text -match '(?i)\bRIT\s*[:?]\s*([A-Z]?\s*-?\d+\s*-\d{4})'){$rit=$matches[1] -replace '\s',''}; if(-not $rit -and $url -match '(?i)tipoCausa=([A-Z]).*?rol=(\d+).*?year=(\d{4})'){$rit=('{0}-{1}-{2}' -f $matches[1],$matches[2],$matches[3])}; if($text -match '(?i)\bTribunal\s*[:?]\s*(.+?)(?=\s+Texto|\s+Litigantes|\s+Materias|$)'){$tribunal=$matches[1].Trim()}; $dteMatches=[regex]::Matches($text,'(?i)\bDTE\.\s+(.+?)(?=\s+\[|\s+resoluci|\s+DDO\.|$)'); if($dteMatches.Count -gt 0){$dte=$dteMatches[$dteMatches.Count-1].Groups[1].Value.Trim()}; $ddoMatches=[regex]::Matches($text,'(?i)\bDDO\.\s+(.+?)(?=\s+\[|\s+resoluci|\s+TERC\.|$)'); if($ddoMatches.Count -gt 0){$ddo=$ddoMatches[$ddoMatches.Count-1].Groups[1].Value.Trim()}; $payload=('RIT: '+$rit+[Environment]::NewLine+'Tribunal: '+$tribunal+[Environment]::NewLine+'DTE. '+$dte+[Environment]::NewLine+'DDO. '+$ddo); Set-Clipboard -Value $payload; Write-Host ('Datos extraidos desde el marco '+$found[0].Frame+'.'); Write-Host $payload; Write-Host 'Vuelva a la aplicacion web y pulse Pegar datos SITFA.'"
if errorlevel 1 (
  echo.
  echo No se pudieron extraer los datos desde Internet Explorer.
  pause
  exit /b 1
)
echo.
echo Datos de MODIFICACION copiados correctamente.
pause
