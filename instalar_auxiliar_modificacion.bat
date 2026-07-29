@echo off
setlocal
set "INSTALL_DIR=%LOCALAPPDATA%\LiquidacionWeb"
if not exist "%INSTALL_DIR%" mkdir "%INSTALL_DIR%"
copy /Y "%~dp0modificacion_helper.ps1" "%INSTALL_DIR%\modificacion_helper.ps1" >nul
reg add "HKCU\Software\Classes\liquidacion" /ve /d "URL:Liquidacion Web" /f >nul
reg add "HKCU\Software\Classes\liquidacion" /v "URL Protocol" /d "" /f >nul
reg add "HKCU\Software\Classes\liquidacion\shell\open\command" /ve /d "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ^"%INSTALL_DIR%\modificacion_helper.ps1^" ^"%%1^"" /f >nul
echo.
echo Auxiliar instalado correctamente.
echo Ya puede cerrar esta ventana.
pause
