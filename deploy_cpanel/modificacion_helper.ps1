$ErrorActionPreference = 'Stop'
try {
    $shell = New-Object -ComObject Shell.Application; $windows = @($shell.Windows()); $found = @()
    foreach ($window in $windows) {
        if (-not $window.FullName -or [System.IO.Path]::GetFileName($window.FullName) -ine 'iexplore.exe') { continue }
        try { $frames = $window.Document.getElementsByTagName('frame') } catch { continue }
        for ($i = 0; $i -lt $frames.length; $i++) { try { $frame = $frames.item($i); $text = [string]$frame.contentWindow.document.body.innerText; if ($text -match '(?i)RIT\s*:' -and $text -match '(?i)Litigantes') { $found += [pscustomobject]@{Text=$text; Frame=$i; URL=[string]$frame.contentWindow.location.href} } } catch {} }
    }
    if ($found.Count -eq 0) { throw 'No se encontro un marco de IE con RIT y Litigantes.' }
    $text=$found[0].Text; $url=$found[0].URL; $rit=''; $tribunal=''; $dte=''; $ddo=''
    if ($text -match '(?i)\bRIT\s*[:?]\s*([A-Z]?\s*-?\d+\s*-\d{4})') {$rit=$matches[1] -replace '\s',''}
    if (-not $rit -and $url -match '(?i)tipoCausa=([A-Z]).*?rol=(\d+).*?year=(\d{4})') {$rit='{0}-{1}-{2}' -f $matches[1],$matches[2],$matches[3]}
    if ($text -match '(?i)\bTribunal\s*[:?]\s*(.+?)(?=\s+Texto|\s+Litigantes|\s+Materias|$)') {$tribunal=$matches[1].Trim()}
    $m=[regex]::Matches($text,'(?is)(?:\bDTE\.|\bSolicitante)\s+(.+?)(?=\s+No existe correo|\s+Tribunal\s+(?:DTE\.|DDO\.)|\s+\[|\s+resoluci|\s+DDO\.|\s+Solicitado\b|\r?\n|$)'); if($m.Count -gt 0){$dte=$m[$m.Count-1].Groups[1].Value.Trim()}
    $m=[regex]::Matches($text,'(?is)(?:\bDDO\.|\bSolicitado)\s+(.+?)(?=\s+No existe correo|\s+Tribunal\s+(?:DTE\.|DDO\.)|\s+\[|\s+resoluci|\s+TERC\.|\s+Solicitante\b|\r?\n|$)'); if($m.Count -gt 0){$ddo=$m[$m.Count-1].Groups[1].Value.Trim()}
    $payload='RIT: '+$rit+[Environment]::NewLine+'Tribunal: '+$tribunal+[Environment]::NewLine+'DTE. '+$dte+[Environment]::NewLine+'DDO. '+$ddo; Set-Clipboard -Value $payload
} catch { Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show($_.Exception.Message,'Liquidación web - error') | Out-Null }
