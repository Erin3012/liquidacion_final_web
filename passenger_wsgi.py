import os
import sys

from a2wsgi import ASGIMiddleware


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from web_app import app, load_indicators  # noqa: E402


# Passenger/cPanel sirve aplicaciones Python como WSGI. FastAPI es ASGI, por eso
# se envuelve con a2wsgi. Cargamos los indicadores aqui por si el hosting no
# ejecuta el evento startup de FastAPI.
load_indicators()

application = ASGIMiddleware(app)
