import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from http.cookies import SimpleCookie


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "auth_config.json")
COOKIE_NAME = "sitfa_session"
SESSION_SECONDS = 8 * 60 * 60
HASH_ITERATIONS = 260000


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    raw_hash = hashlib.pbkdf2_hmac("sha256", (password or "").encode("utf-8"), salt.encode("utf-8"), HASH_ITERATIONS)
    return f"pbkdf2_sha256${HASH_ITERATIONS}${salt}${raw_hash.hex()}"


def verify_password(password, password_hash):
    try:
        algorithm, iterations, salt, stored_hash = (password_hash or "").split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        raw_hash = hashlib.pbkdf2_hmac(
            "sha256",
            (password or "").encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return hmac.compare_digest(raw_hash.hex(), stored_hash)
    except Exception:
        return False


def _read_config():
    config = {}
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as file:
            config = json.load(file)
    users = config.get("users")
    if not users:
        users = [
            {
                "username": os.environ.get("SITFA_USERNAME") or config.get("username") or "admin",
                "password": os.environ.get("SITFA_PASSWORD") or config.get("password") or "liquidaciones2026",
                "role": "admin",


            }

        ]
    return {
        "users": users,
        "secret_key": os.environ.get("SITFA_SECRET_KEY") or config.get("secret_key") or "change-this-secret-key",
    }


def find_user(username):
    config = _read_config()
    for user in config["users"]:
        if secrets.compare_digest(username or "", user.get("username", "")):
            return user
    return None


def check_credentials(username, password):
    user = find_user(username)
    if not user:
        return False
    if user.get("password_hash"):
        return verify_password(password, user["password_hash"])
    return secrets.compare_digest(password or "", user.get("password", ""))


def _signature(payload, secret_key):
    return hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def create_session(username):
    config = _read_config()
    expires = str(int(time.time()) + SESSION_SECONDS)
    payload = f"{username}:{expires}"
    token = f"{payload}:{_signature(payload, config['secret_key'])}"
    return base64.urlsafe_b64encode(token.encode("utf-8")).decode("ascii")


def validate_session(token):
    if not token:
        return False
    try:
        config = _read_config()
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        username, expires, signature = decoded.rsplit(":", 2)
        payload = f"{username}:{expires}"
        if not hmac.compare_digest(signature, _signature(payload, config["secret_key"])):
            return False
        if int(expires) < int(time.time()):
            return False
        return find_user(username) is not None
    except Exception:
        return False


def cookie_header(username, secure=False, path="/"):
    cookie = SimpleCookie()
    cookie[COOKIE_NAME] = create_session(username)
    cookie[COOKIE_NAME]["path"] = path
    cookie[COOKIE_NAME]["httponly"] = True
    cookie[COOKIE_NAME]["samesite"] = "Lax"
    cookie[COOKIE_NAME]["max-age"] = str(SESSION_SECONDS)
    if secure:
        cookie[COOKIE_NAME]["secure"] = True
    return cookie.output(header="").strip()


def clear_cookie_header(path="/"):
    cookie = SimpleCookie()
    cookie[COOKIE_NAME] = ""
    cookie[COOKIE_NAME]["path"] = path
    cookie[COOKIE_NAME]["httponly"] = True
    cookie[COOKIE_NAME]["samesite"] = "Lax"
    cookie[COOKIE_NAME]["max-age"] = "0"
    return cookie.output(header="").strip()


def token_from_cookie_header(cookie_header):
    cookie = SimpleCookie()
    cookie.load(cookie_header or "")
    morsel = cookie.get(COOKIE_NAME)
    return morsel.value if morsel else ""


def login_html(error="", base_path=""):
    error_html = f'<div class="error">{error}</div>' if error else ""
    action = f"{base_path}/login" if base_path else "/login"
    background_url = f"{base_path}/login-bg.png" if base_path else "/login-bg.png"
    return f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ingreso SITFA Liquidaciones</title>
  <style>
    :root {{
      --ink: #20242c;
      --muted: #667085;
      --line: #d8dde8;
      --accent: #b43d30;
      --blue: #245f9f;
      --gold: #c7b37b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      background:
        linear-gradient(90deg, rgba(17, 24, 39, .80), rgba(17, 24, 39, .24)),
        url("{background_url}") center / cover no-repeat;
    }}
    .login {{
      width: min(420px, 100%);
      padding: 26px;
      background: rgba(255, 255, 255, .94);
      border: 1px solid var(--line);
      border-top: 5px solid var(--gold);
      border-radius: 8px;
      box-shadow: 0 18px 50px rgba(0, 0, 0, .22);
    }}
    h1 {{ margin: 0 0 8px; font-size: 21px; }}
    p {{ margin: 0 0 22px; color: var(--muted); font-size: 14px; }}
    label {{ display: grid; gap: 6px; margin-bottom: 14px; color: var(--muted); font-size: 13px; }}
    input {{
      width: 100%;
      min-height: 40px;
      border: 1px solid #c5ccd8;
      border-radius: 5px;
      padding: 9px 10px;
      font: inherit;
    }}
    button {{
      width: 100%;
      min-height: 42px;
      border: 0;
      border-radius: 5px;
      color: white;
      background: var(--blue);
      font-weight: 700;
      cursor: pointer;
    }}
    .error {{
      margin-bottom: 14px;
      padding: 10px 12px;
      border: 1px solid #f0b7b0;
      border-radius: 5px;
      color: #8f1d12;
      background: #fff1f0;
      font-size: 13px;
    }}
  </style>
</head>
<body>
  <form class="login" method="post" action="{action}">
    <h1>Acceso</h1>
    <p>Unidad de Liquidaciones Especializadas de Concepcion</p>
    {error_html}
    <label>Usuario<input name="username" autocomplete="username" required autofocus></label>
    <label>Clave<input name="password" type="password" autocomplete="current-password" required></label>
    <button type="submit">Ingresar</button>
  </form>
</body>
</html>"""
