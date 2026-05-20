@echo off
setlocal EnableExtensions
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\WindowsPowerShell\v1.0;%PATH%"

if /I "%~1"=="--worker" goto worker

set "PROJECT_DIR=%~dp0"
set "WORKER_BAT=%TEMP%\actualizar_desde_github_worker_%RANDOM%_%RANDOM%.bat"

copy /Y "%~f0" "%WORKER_BAT%" >nul
if errorlevel 1 (
    echo ERROR: No se pudo crear una copia temporal del actualizador.
    pause
    exit /b 1
)

call "%WORKER_BAT%" --worker "%PROJECT_DIR%"
set "RESULT=%ERRORLEVEL%"

del "%WORKER_BAT%" >nul 2>nul

echo.
if "%RESULT%"=="0" (
    echo Proceso terminado correctamente.
) else (
    echo El proceso termino con errores.
)
echo Log: "%PROJECT_DIR%actualizar_desde_github.log"
echo.
pause
exit /b %RESULT%

:worker
setlocal EnableExtensions

set "ZIP_URL=https://github.com/Erin3012/liquidacion_final_web/archive/refs/heads/main.zip"
set "BRANCH=main"
set "PROJECT_DIR=%~2"

if "%PROJECT_DIR%"=="" set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"
if errorlevel 1 exit /b 1

set "LOG=%CD%\actualizar_desde_github.log"
set "TMP_DIR=%TEMP%\liquidacion_final_web_update_%RANDOM%_%RANDOM%"
set "ZIP_FILE=%TMP_DIR%\repo.zip"
set "EXTRACT_DIR=%TMP_DIR%\extraido"
set "AUTH_BACKUP=%TMP_DIR%\auth_config.local.json"

> "%LOG%" echo [%DATE% %TIME%] Inicio de actualizacion

call :log "=========================================="
call :log "Actualizador Liquidacion Final Web"
call :log "=========================================="
call :log "Carpeta: %CD%"

if exist "auth_config.json" (
    call :log "Se conservara auth_config.json local."
)

if exist ".git\" goto update_with_git
goto update_with_zip

:update_with_git
where git >> "%LOG%" 2>&1
if errorlevel 1 (
    call :log "ERROR: Esta carpeta tiene .git, pero Git no esta instalado o no esta en PATH."
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "New-Item -ItemType Directory -Path '%TMP_DIR%' -Force | Out-Null" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1

if exist "auth_config.json" copy /Y "auth_config.json" "%AUTH_BACKUP%" >> "%LOG%" 2>&1

call :log "Actualizando desde GitHub con git pull..."
git fetch origin %BRANCH% >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1

git pull --ff-only origin %BRANCH% >> "%LOG%" 2>&1
if errorlevel 1 (
    call :log "ERROR: No se pudo aplicar git pull automaticamente. Puede haber cambios locales en este PC."
    exit /b 1
)

if exist "%AUTH_BACKUP%" copy /Y "%AUTH_BACKUP%" "auth_config.json" >> "%LOG%" 2>&1
goto cleanup_and_install

:update_with_zip
call :log "Esta carpeta no tiene .git. Se descargara un ZIP desde GitHub."

powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%TMP_DIR%' -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Path '%TMP_DIR%' -Force | Out-Null; New-Item -ItemType Directory -Path '%EXTRACT_DIR%' -Force | Out-Null" >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1

if exist "auth_config.json" copy /Y "auth_config.json" "%AUTH_BACKUP%" >> "%LOG%" 2>&1

call :log "Descargando archivos actualizados..."
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_FILE%' -UseBasicParsing" >> "%LOG%" 2>&1
if errorlevel 1 (
    call :log "ERROR: No se pudo descargar el ZIP desde GitHub."
    call :log "Temporal conservado para revision: %TMP_DIR%"
    exit /b 1
)

call :log "Descomprimiendo..."
where tar >> "%LOG%" 2>&1
if not errorlevel 1 (
    tar -xf "%ZIP_FILE%" -C "%EXTRACT_DIR%" >> "%LOG%" 2>&1
) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; $ErrorActionPreference='Stop'; Expand-Archive -LiteralPath '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force" >> "%LOG%" 2>&1
)
if errorlevel 1 (
    call :log "ERROR: No se pudo descomprimir el ZIP descargado."
    call :log "Temporal conservado para revision: %TMP_DIR%"
    exit /b 1
)
call :log "Descompresion completada."

set "SRC_DIR="
for /d %%D in ("%EXTRACT_DIR%\*") do set "SRC_DIR=%%~fD"
if not defined SRC_DIR (
    call :log "ERROR: No se encontro la carpeta descomprimida."
    exit /b 1
)

call :log "Copiando archivos al servidor local..."
robocopy "%SRC_DIR%" "%CD%" /E /XD ".git" ".venv" ".idea" "__pycache__" "dist" /XF "actualizar_desde_github.bat" "server.err.log" "server.out.log" >> "%LOG%" 2>&1
if errorlevel 8 (
    call :log "ERROR: No se pudieron copiar los archivos actualizados."
    call :log "Temporal conservado para revision: %TMP_DIR%"
    exit /b 1
)

if exist "%AUTH_BACKUP%" copy /Y "%AUTH_BACKUP%" "auth_config.json" >> "%LOG%" 2>&1
goto cleanup_and_install

:cleanup_and_install
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%TMP_DIR%' -Recurse -Force -ErrorAction SilentlyContinue" >> "%LOG%" 2>&1

call :log "Instalando o actualizando dependencias..."
where python >> "%LOG%" 2>&1
if errorlevel 1 (
    call :log "ERROR: No se encontro Python en PATH. Instale Python 3.11+."
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    call :log "Creando entorno virtual..."
    python -m venv .venv >> "%LOG%" 2>&1
    if errorlevel 1 exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt >> "%LOG%" 2>&1
if errorlevel 1 exit /b 1

call :log "Actualizacion completada."

if exist "restart_server.ps1" (
    choice /C SN /M "Desea reiniciar el servidor ahora"
    if errorlevel 2 goto done
    powershell -NoProfile -ExecutionPolicy Bypass -File ".\restart_server.ps1" >> "%LOG%" 2>&1
    if errorlevel 1 exit /b 1
)

:done
call :log "Listo."
call :log "URL local: http://127.0.0.1:8000/"
call :log "URL red:   http://IP-DE-ESTE-PC:8000/"
exit /b 0

:log
echo %~1
>> "%LOG%" echo [%DATE% %TIME%] %~1
exit /b 0
