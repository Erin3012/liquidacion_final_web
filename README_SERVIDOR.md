# Instalación en equipo servidor

Copie esta carpeta al equipo que ejecutará la aplicación, por ejemplo:

```text
C:\sitfa-web
```

No es necesario copiar `.venv`, `.idea` ni `__pycache__`.

## Primer arranque

Abra PowerShell en la carpeta del proyecto y ejecute:

```powershell
.\setup_server.ps1
```

El script:

- crea `.venv` si no existe;
- instala dependencias desde `requirements.txt`;
- verifica sintaxis;
- inicia FastAPI en `0.0.0.0:8000`.

## Uso diario

Para reiniciar el servidor:

```powershell
.\restart_server.ps1
```

Para ejecutarlo en primer plano y ver logs:

```powershell
.\run_server.ps1
```

Para detenerlo:

```powershell
.\stop_server.ps1
```

## Acceso desde la red

Desde el mismo equipo:

```text
http://127.0.0.1:8000/
```

Desde otros equipos:

```text
http://NOMBRE-DEL-SERVIDOR:8000/
```

o:

```text
http://IP-DEL-SERVIDOR:8000/
```

Puede ser necesario permitir Python/Uvicorn o el puerto `8000` en Firewall de Windows.

## Login

La aplicaciÃ³n queda protegida con login.

Credenciales iniciales:

```text
Usuario: admin
Clave: liquidaciones2026
```

Los usuarios se configuran en `auth_config.json`. Las claves se guardan como hash.

Para generar un hash de clave:

```powershell
.\.venv\Scripts\python.exe make_password_hash.py
```

Copie el bloque generado dentro de la lista `users` de `auth_config.json`. Para cambiar una clave, genere un nuevo hash y reemplace `password_hash`. Para eliminar un usuario, borre su bloque.

Tambien puede usar estas variables de entorno para instalaciones simples de un solo usuario:

```text
SITFA_USERNAME
SITFA_PASSWORD
SITFA_SECRET_KEY
```

## Sobre copiar `.venv`

No se recomienda copiar `.venv` desde otro computador. Puede fallar si cambia la ruta, versión de Python, arquitectura, permisos o librerías compiladas. Lo más seguro es copiar el proyecto sin `.venv` y ejecutar `setup_server.ps1` en el servidor.
