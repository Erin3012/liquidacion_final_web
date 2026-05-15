# SITFA Web

Aplicación web FastAPI para generar liquidaciones.

## Instalación

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Ejecución

```powershell
.\.venv\Scripts\python.exe -m uvicorn web_app:app --reload --host 127.0.0.1 --port 8000
```

Luego abrir:

```text
http://127.0.0.1:8000
```

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

Para instalarlo en otro equipo como servidor, vea `README_SERVIDOR.md` y ejecute:

```powershell
.\setup_server.ps1
```

## Alcance inicial

- Datos de causa ingresados manualmente.
- Cálculo IPC, IMRM y UTM usando los JSON existentes.
- Carga de cartolas CSV/XLS/XLSX.
- Cambios de monto durante el periodo.
- Ajustes manuales por cargo o abono.
- Generación y descarga de PDF.
- Anexo opcional de PDF externo.
- Pegado de datos DTE/DDO desde el texto copiado nativamente en SITFA.

El botón `Pegar datos SITFA` lee el portapapeles y extrae DTE/DDO desde el texto copiado en SITFA.

## Archivos principales

- `web_app.py`: aplicación FastAPI e interfaz web.
- `calculation_engine.py`: motor de cálculo.
- `cartola_parser.py`: lectura de cartolas.
- `pdf_engine.py`: generación de PDF.
