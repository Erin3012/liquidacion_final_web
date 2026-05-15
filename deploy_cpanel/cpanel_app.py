import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass
from urllib.parse import parse_qs


MODULE_IMPORT_STARTED_AT = time.perf_counter()
REQUEST_COUNT = 0
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def _log_timing(scope, stage, started_at, **details):
    elapsed = time.perf_counter() - started_at
    detail_text = " ".join(f"{key}={value}" for key, value in details.items())
    print(f"[{scope}] {stage} elapsed={elapsed:.3f}s {detail_text}".rstrip(), file=sys.stderr, flush=True)


import auth  # noqa: E402
import calculation_engine  # noqa: E402
import cartola_parser  # noqa: E402
import config  # noqa: E402
import pdf_engine  # noqa: E402
import utils  # noqa: E402
from multipart import parse_form  # noqa: E402
from web_app import INDEX_HTML, LiquidationPayload, get_project_version, payload_to_dict  # noqa: E402


utils.cargar_ipc_json_historico()
utils.cargar_utm_historico()
utils.cargar_imr_historico()

_log_timing("cpanel_app", "module_import_total", MODULE_IMPORT_STARTED_AT, pid=os.getpid())


def _timed_start_response(start_response, request_started_at, request_id):
    response_started = False

    def wrapper(status, headers, exc_info=None):
        nonlocal response_started
        if not response_started:
            response_started = True
            elapsed_ms = int((time.perf_counter() - request_started_at) * 1000)
            headers = list(headers)
            headers.append(("X-App-Elapsed-Ms", str(elapsed_ms)))
            headers.append(("X-App-Request-Id", str(request_id)))
            _log_timing("cpanel_request", "response_start", request_started_at, id=request_id, status=status)
        return start_response(status, headers, exc_info)

    return wrapper


def _path(environ):
    path = environ.get("PATH_INFO") or "/"
    if path.startswith("/liquidaciones/"):
        path = path[len("/liquidaciones"):]
    elif path == "/liquidaciones":
        path = "/"
    return path or "/"


def _base_path(environ):
    script_name = environ.get("SCRIPT_NAME") or ""
    if script_name:
        return script_name.rstrip("/")
    path = environ.get("PATH_INFO") or ""
    return "/liquidaciones" if path.startswith("/liquidaciones") else ""


def _is_secure(environ):
    return environ.get("wsgi.url_scheme") == "https" or environ.get("HTTP_X_FORWARDED_PROTO") == "https"


def _response(start_response, status, body, content_type="text/plain; charset=utf-8", headers=None):
    if isinstance(body, str):
        body = body.encode("utf-8")
    response_headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    if headers:
        response_headers.extend(headers)
    start_response(status, response_headers)
    return [body]


def _redirect(start_response, location, headers=None):
    response_headers = [("Location", location)]
    if headers:
        response_headers.extend(headers)
    return _response(start_response, "303 See Other", "", "text/plain; charset=utf-8", response_headers)


def _json(start_response, data, status="200 OK"):
    return _response(start_response, status, json.dumps(data, ensure_ascii=False), "application/json; charset=utf-8")


def _file_response(start_response, path, content_type):
    if not os.path.exists(path):
        return _response(start_response, "404 Not Found", "No encontrado")
    with open(path, "rb") as file:
        body = file.read()
    return _response(start_response, "200 OK", body, content_type)


def _read_json(environ):
    length = int(environ.get("CONTENT_LENGTH") or 0)
    body = environ["wsgi.input"].read(length) if length else b"{}"
    return json.loads(body.decode("utf-8"))


@dataclass
class UploadedFile:
    filename: str
    file: object


def _text(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _parse_form(environ):
    started_at = time.perf_counter()
    fields = defaultdict(list)
    files = defaultdict(list)
    content_type = environ.get("CONTENT_TYPE") or ""
    length = int(environ.get("CONTENT_LENGTH") or 0)

    if content_type.startswith("application/x-www-form-urlencoded"):
        body = environ["wsgi.input"].read(length).decode("utf-8") if length else ""
        for key, values in parse_qs(body, keep_blank_values=True).items():
            fields[key].extend(values)
        _log_timing("cpanel_form", "parse_urlencoded", started_at, bytes=length, fields=sum(len(v) for v in fields.values()))
        return fields, files

    def on_field(field):
        fields[_text(field.field_name)].append(_text(field.value))

    def on_file(file):
        file.file_object.seek(0)
        files[_text(file.field_name)].append(UploadedFile(_text(file.file_name or ""), file.file_object))

    headers = {
        "Content-Type": (environ.get("CONTENT_TYPE") or "").encode("latin-1"),
        "Content-Length": (environ.get("CONTENT_LENGTH") or "0").encode("latin-1"),
    }
    parse_form(headers, environ["wsgi.input"], on_field, on_file)
    _log_timing(
        "cpanel_form",
        "parse_multipart",
        started_at,
        bytes=length,
        fields=sum(len(v) for v in fields.values()),
        files=sum(len(v) for v in files.values()),
    )
    return fields, files


def _upload_cartolas(environ, start_response):
    overall_started_at = time.perf_counter()
    form_started_at = time.perf_counter()
    _fields, files = _parse_form(environ)
    _log_timing("api_cartolas", "parse_form", form_started_at, files=sum(len(v) for v in files.values()))
    parsed = []
    temp_paths = []
    try:
        uploaded_files = files.get("files", [])
        for index, item in enumerate(uploaded_files, start=1):
            file_started_at = time.perf_counter()
            suffix = os.path.splitext(item.filename or "")[1]
            write_started_at = time.perf_counter()
            content = item.file.read()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(content)
                temp_paths.append(tmp.name)
            _log_timing(
                "api_cartolas",
                "write_temp_file",
                write_started_at,
                index=index,
                ext=(suffix or "none").lower(),
                bytes=len(content),
            )
            parse_started_at = time.perf_counter()
            parsed.append(cartola_parser.parse_cartola(temp_paths[-1]))
            _log_timing("api_cartolas", "parse_file", parse_started_at, index=index, ext=(suffix or "none").lower())
            _log_timing("api_cartolas", "file_total", file_started_at, index=index, ext=(suffix or "none").lower())
        _log_timing("api_cartolas", "request_total", overall_started_at, files=len(uploaded_files))
        return _json(start_response, {"cartolas": parsed})
    except Exception:
        _log_timing("api_cartolas", "request_failed", overall_started_at, files=len(files.get("files", [])))
        raise
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)


def _generate_pdf(environ, start_response):
    fields, files = _parse_form(environ)
    workdir = tempfile.mkdtemp(prefix="sitfa_pdf_")
    external_path = None
    try:
        payload_text = fields["payload"][0]
        data = payload_to_dict(LiquidationPayload(**json.loads(payload_text)))
        result = calculation_engine.calculate_liquidation(data)

        external_items = files.get("external_pdf", [])
        if external_items and external_items[0].filename:
            external_path = os.path.join(workdir, os.path.basename(external_items[0].filename))
            with open(external_path, "wb") as target:
                target.write(external_items[0].file.read())

        pdf_args = calculation_engine.build_pdf_args(
            data,
            result,
            external_pdf_path=external_path,
            output_dir=workdir,
        )
        pdf_path = pdf_engine.generar_pdf(**pdf_args)
        filename = os.path.basename(pdf_path)
        with open(pdf_path, "rb") as file:
            body = file.read()
        return _response(
            start_response,
            "200 OK",
            body,
            "application/pdf",
            [("Content-Disposition", f'attachment; filename="{filename}"')],
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def application(environ, start_response):
    global REQUEST_COUNT
    REQUEST_COUNT += 1
    request_id = REQUEST_COUNT
    request_started_at = time.perf_counter()
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = _path(environ)
    _log_timing("cpanel_request", "request_start", request_started_at, id=request_id, method=method, path=path, pid=os.getpid())
    start_response = _timed_start_response(start_response, request_started_at, request_id)
    try:
        base_path = _base_path(environ)
        login_path = f"{base_path}/login" if base_path else "/login"
        home_path = f"{base_path}/" if base_path else "/"
        cookie_path = base_path or "/"

        if method == "GET" and path == "/login-bg.png":
            return _file_response(start_response, os.path.join(BASE_DIR, "login_bg.png"), "image/png")

        if method == "GET" and path == "/login":
            if auth.validate_session(auth.token_from_cookie_header(environ.get("HTTP_COOKIE", ""))):
                return _redirect(start_response, home_path)
            return _response(start_response, "200 OK", auth.login_html(base_path=base_path), "text/html; charset=utf-8")

        if method == "POST" and path == "/login":
            fields, _files = _parse_form(environ)
            username = fields.get("username", [""])[0]
            password = fields.get("password", [""])[0]
            if auth.check_credentials(username, password):
                return _redirect(
                    start_response,
                    home_path,
                    [("Set-Cookie", auth.cookie_header(username, secure=_is_secure(environ), path=cookie_path))],
                )
            return _response(
                start_response,
                "401 Unauthorized",
                auth.login_html("Usuario o clave incorrectos", base_path=base_path),
                "text/html; charset=utf-8",
            )

        if method == "GET" and path == "/logout":
            return _redirect(start_response, login_path, [("Set-Cookie", auth.clear_cookie_header(path=cookie_path))])

        if not auth.validate_session(auth.token_from_cookie_header(environ.get("HTTP_COOKIE", ""))):
            if path.startswith("/api/"):
                return _json(start_response, {"detail": "No autenticado"}, "401 Unauthorized")
            return _redirect(start_response, login_path)

        if method == "GET" and path == "/api/ping":
            return _json(
                start_response,
                {
                    "ok": True,
                    "pid": os.getpid(),
                    "request_id": request_id,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
            )

        if method == "GET" and path in ("/", ""):
            html = INDEX_HTML.replace("{{APP_VERSION}}", get_project_version())
            return _response(start_response, "200 OK", html, "text/html; charset=utf-8")

        if method == "GET" and path == "/api/options":
            return _json(
                start_response,
                {
                    "tribunales": config.TRIBUNALES,
                    "meses": config.MESES,
                    "anos": config.ANOS,
                    "reajustes": config.REAJUSTES,
                    "fecha_pago": ["primer día"]
                    + [f"{i} primeros días" for i in range(2, 26)]
                    + [f"{i} últimos días" for i in range(10, 1, -1)]
                    + ["Último día"],
                },
            )

        if method == "GET" and path == "/api/indicators/ipc":
            utils.cargar_ipc_json_historico()
            return _json(
                start_response,
                {
                    "title": "Valores IPC cargados",
                    "headers": ["Periodo", "Valor"],
                    "rows": [[key, value] for key, value in sorted(utils.BD_IPC_VALORES.items(), reverse=True)],
                },
            )

        if method == "GET" and path == "/api/indicators/imr":
            utils.cargar_imr_historico()
            rows = []
            for tramo in utils.BD_IMR_VALORES:
                rows.append([tramo.get("Desde", ""), tramo.get("Hasta", ""), tramo.get("IMRM", tramo.get("IMR", ""))])
            return _json(start_response, {"title": "Valores IMR cargados", "headers": ["Desde", "Hasta", "Valor"], "rows": rows})

        if method == "POST" and path == "/api/calculate":
            data = payload_to_dict(LiquidationPayload(**_read_json(environ)))
            return _json(start_response, calculation_engine.calculate_liquidation(data))

        if method == "POST" and path == "/api/cartolas":
            return _upload_cartolas(environ, start_response)

        if method == "POST" and path == "/api/pdf":
            return _generate_pdf(environ, start_response)

        return _json(start_response, {"detail": "No encontrado"}, "404 Not Found")
    except Exception as exc:
        traceback.print_exc()
        return _json(start_response, {"detail": str(exc)}, "400 Bad Request")
    finally:
        _log_timing("cpanel_request", "request_finish", request_started_at, id=request_id, method=method, path=path, pid=os.getpid())
