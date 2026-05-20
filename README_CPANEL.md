# Despliegue en cPanel

Esta guia es solo para probar la aplicacion como **Python App** en cPanel. No usa WordPress.

## 1. Crear la aplicacion

En cPanel abrir **Setup Python App** y completar:

```text
Python version: 3.11.15
Application root: liquidacion-web
Application URL: qlc.cl/liquidaciones
Application startup file: cpanel_app.py
Application Entry point: application
```

Si no quieres usar `/liquidaciones`, puedes dejar el campo de ruta vacio y usar solo el dominio principal.

## 2. Archivos que se deben subir

Subir estos archivos al directorio configurado como `Application root`:

```text
calculation_engine.py
cartola_parser.py
config.py
auth.py
auth_config.json
emolumentos_parser.py
excel_engine.py
make_password_hash.py
imr.json
ipc.json
cpanel_app.py
login_bg.png
pdf_engine.py
pj.png
requirements.txt
utils.py
utm.json
version.json
web_app.py
```

No subir:

```text
.venv
__pycache__
.idea
*.ps1
README_*.md
```

## 3. Instalar dependencias

Despues de crear la aplicacion, cPanel deberia mostrar comandos para activar el entorno virtual. Desde **Terminal**, entrar al entorno de la aplicacion e instalar:

```bash
pip install -r requirements.txt
```

Si cPanel entrega un boton como **Run Pip Install**, usarlo con:

```text
requirements.txt
```

## 4. Reiniciar

En **Setup Python App**, usar **Restart** para reiniciar la aplicacion.

La aplicacion deberia abrir en:

```text
https://qlc.cl/liquidaciones
```

## Login y usuarios

La aplicacion queda protegida con login.

Credenciales iniciales:

```text
Usuario: admin
Clave: liquidaciones2026
```

Los usuarios se configuran en `auth_config.json`. Las claves se guardan como hash, no como texto plano.

Para crear el bloque de un nuevo usuario, ejecutar en Terminal:

```bash
source /home/qlccl/virtualenv/liquidacion-web/3.11/bin/activate
cd /home/qlccl/liquidacion-web
python make_password_hash.py
```

Copiar el JSON generado dentro de la lista `users` de `auth_config.json`.

Ejemplo:

```json
{
  "users": [
    {
      "username": "admin",
      "password_hash": "...",
      "role": "admin"
    },
    {
      "username": "usuario1",
      "password_hash": "...",
      "role": "user"
    }
  ],
  "secret_key": "..."
}
```

Para modificar una clave, generar un nuevo hash y reemplazar el `password_hash` del usuario. Para eliminar un usuario, borrar su bloque de la lista `users`.

Despues de editar `auth_config.json`, reiniciar:

```bash
cd /home/qlccl/liquidacion-web
touch tmp/restart.txt
```

Tambien se pueden definir variables de entorno en cPanel para instalaciones simples de un solo usuario:

```text
SITFA_USERNAME
SITFA_PASSWORD
SITFA_SECRET_KEY
```

## Notas

- Esta aplicacion maneja datos personales; para uso real en internet debe agregarse autenticacion.
- Para uso interno de oficina, sigue siendo mas simple y controlado ejecutarla en un equipo servidor dentro de la red.
