@echo off
setlocal

set "REPO_URL=https://github.com/Erin3012/liquidacion_final_web.git"
set "ZIP_URL=https://github.com/Erin3012/liquidacion_final_web/archive/refs/heads/main.zip"
set "BRANCH=main"

cd /d "%~dp0"

echo.
echo ==========================================
echo Actualizador Liquidacion Final Web
echo ==========================================
echo Carpeta: %CD%
echo.

if exist ".git\" goto update_with_git
goto update_with_zip

:update_with_git
where git >nul 2>nul
if errorlevel 1 (
    echo ERROR: Esta carpeta tiene .git, pero Git no esta instalado o no esta en PATH.
    echo Instale Git for Windows o use una carpeta sin .git para actualizar por ZIP.
    pause
    exit /b 1
)

echo Actualizando desde GitHub con git pull...
git fetch origin %BRANCH%
if errorlevel 1 goto error

git pull --ff-only origin %BRANCH%
if errorlevel 1 (
    echo.
    echo ERROR: No se pudo aplicar git pull automaticamente.
    echo Puede haber cambios locales sin subir en este PC.
    pause
    exit /b 1
)
goto install_deps

:update_with_zip
echo Esta carpeta no tiene .git. Se descargara un ZIP desde GitHub.
echo.

set "TMP_DIR=%TEMP%\liquidacion_final_web_update"
set "ZIP_FILE=%TMP_DIR%\repo.zip"
set "EXTRACT_DIR=%TMP_DIR%\extraido"
set "AUTH_BACKUP=%TMP_DIR%\auth_config.local.json"

powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%TMP_DIR%' -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Path '%TMP_DIR%' | Out-Null; New-Item -ItemType Directory -Path '%EXTRACT_DIR%' | Out-Null"
if errorlevel 1 goto error

if exist "auth_config.json" copy /Y "auth_config.json" "%AUTH_BACKUP%" >nul

echo Descargando archivos actualizados...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-WebRequest -Uri '%ZIP_URL%' -OutFile '%ZIP_FILE%'"
if errorlevel 1 goto error

echo Descomprimiendo...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -LiteralPath '%ZIP_FILE%' -DestinationPath '%EXTRACT_DIR%' -Force"
if errorlevel 1 goto error

for /d %%D in ("%EXTRACT_DIR%\*") do set "SRC_DIR=%%D"
if not defined SRC_DIR (
    echo ERROR: No se encontro la carpeta descomprimida.
    pause
    exit /b 1
)

echo Copiando archivos al servidor local...
robocopy "%SRC_DIR%" "%CD%" /E /XD ".git" ".venv" ".idea" "__pycache__" "dist" /XF "%~nx0" "server.err.log" "server.out.log" >nul
if errorlevel 8 goto error

if exist "%AUTH_BACKUP%" copy /Y "%AUTH_BACKUP%" "auth_config.json" >nul

powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%TMP_DIR%' -Recurse -Force -ErrorAction SilentlyContinue"
goto install_deps

:install_deps
echo.
echo Instalando o actualizando dependencias...

where python >nul 2>nul
if errorlevel 1 (
    echo ERROR: No se encontro Python en PATH. Instale Python 3.11+.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual...
    python -m venv .venv
    if errorlevel 1 goto error
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error

echo.
echo Actualizacion completada.
echo.

if exist "restart_server.ps1" (
    choice /C SN /M "Desea reiniciar el servidor ahora"
    if errorlevel 2 goto done
    powershell -NoProfile -ExecutionPolicy Bypass -File ".\restart_server.ps1"
    if errorlevel 1 goto error
)

:done
echo.
echo Listo.
echo URL local: http://127.0.0.1:8000/
echo URL red:   http://IP-DE-ESTE-PC:8000/
pause
exit /b 0

:error
echo.
echo ERROR: La actualizacion no se completo.
pause
exit /b 1
