import json
import os
import shutil
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask
from starlette.responses import Response

import auth
import calculation_engine
import cartola_parser
import config
import pdf_engine
import utils


app = FastAPI(title="SITFA Liquidaciones Web")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _log_timing(scope, stage, started_at, **details):
    elapsed = time.perf_counter() - started_at
    detail_text = " ".join(f"{key}={value}" for key, value in details.items())
    print(f"[{scope}] {stage} elapsed={elapsed:.3f}s {detail_text}".rstrip(), file=sys.stderr, flush=True)


def _is_secure_request(request: Request):
    return request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"


@app.middleware("http")
async def require_login(request: Request, call_next):
    path = request.url.path
    if path in ("/login", "/logout", "/login-bg.png"):
        return await call_next(request)
    if auth.validate_session(request.cookies.get(auth.COOKIE_NAME)):
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "No autenticado"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


class LiquidationPayload(BaseModel):
    tribunal: str = ""
    rit: str = ""
    lav: str = ""
    beneficiario: str = ""
    alimentante: str = ""
    fecha_pago: str = ""
    pension: str = "$0"
    reajuste_tipo: str = "IPC (Semestral)"
    mes_desde: str
    ano_desde: str
    mes_hasta: str
    ano_hasta: str
    descuento_meses: int = 0
    tiene_arrastre: bool = False
    monto_arrastre: str = "$0"
    referencia_arrastre: str = ""
    arrastre_mes_desde: str = ""
    arrastre_ano_desde: str = ""
    arrastre_mes_hasta: str = ""
    arrastre_ano_hasta: str = ""
    pension_final_arrastre: str = "$0"
    iniciales: str = ""
    cese_alimentos: bool = False
    observaciones: str = ""
    historial_pensiones: List[Dict[str, Any]] = Field(default_factory=list)
    ajustes_manuales: List[Dict[str, Any]] = Field(default_factory=list)
    cartolas: List[Dict[str, Any]] = Field(default_factory=list)


def payload_to_dict(payload: LiquidationPayload):
    if hasattr(payload, "model_dump"):
        return payload.model_dump()
    return payload.dict()


def get_project_version():
    version_path = os.path.join(BASE_DIR, "version.json")
    try:
        with open(version_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return f"{data.get('major', 0)}.{data.get('minor', 0)}.{data.get('build', 0)}"
    except Exception:
        return "sin versión"


@app.on_event("startup")
def load_indicators():
    utils.cargar_ipc_json_historico()
    utils.cargar_utm_historico()
    utils.cargar_imr_historico()


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(INDEX_HTML.replace("{{APP_VERSION}}", get_project_version()))


@app.get("/login", response_class=HTMLResponse)
def login_page():
    return HTMLResponse(auth.login_html())


@app.get("/login-bg.png")
def login_background():
    image_path = os.path.join(BASE_DIR, "login_bg.png")
    if not os.path.exists(image_path):
        return Response(status_code=404)
    return FileResponse(image_path, media_type="image/png")


@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not auth.check_credentials(username, password):
        return HTMLResponse(auth.login_html("Usuario o clave incorrectos"), status_code=401)
    response = RedirectResponse("/", status_code=303)
    response.headers.append("Set-Cookie", auth.cookie_header(username, secure=_is_secure_request(request)))
    return response


@app.get("/logout")
def logout():
    response = RedirectResponse("/login", status_code=303)
    response.headers.append("Set-Cookie", auth.clear_cookie_header())
    return response


@app.get("/api/options")
def options():
    return {
        "tribunales": config.TRIBUNALES,
        "meses": config.MESES,
        "anos": config.ANOS,
        "reajustes": config.REAJUSTES,
        "fecha_pago": ["primer día"]
        + [f"{i} primeros días" for i in range(2, 26)]
        + [f"{i} últimos días" for i in range(10, 1, -1)]
        + ["Último día"],
    }


@app.get("/api/ping")
def ping():
    return {"ok": True, "pid": os.getpid(), "time": time.strftime("%Y-%m-%d %H:%M:%S")}


@app.get("/api/indicators/ipc")
def get_ipc_values():
    utils.cargar_ipc_json_historico()
    return {
        "title": "Valores IPC cargados",
        "headers": ["Periodo", "Valor"],
        "rows": [[key, value] for key, value in sorted(utils.BD_IPC_VALORES.items(), reverse=True)],
    }


@app.get("/api/indicators/imr")
def get_imr_values():
    utils.cargar_imr_historico()
    rows = []
    for tramo in utils.BD_IMR_VALORES:
        rows.append(
            [
                tramo.get("Desde", ""),
                tramo.get("Hasta", ""),
                tramo.get("IMRM", tramo.get("IMR", "")),
            ]
        )
    return {
        "title": "Valores IMR cargados",
        "headers": ["Desde", "Hasta", "Valor"],
        "rows": rows,
    }


@app.post("/api/calculate")
def calculate(payload: LiquidationPayload):
    try:
        return calculation_engine.calculate_liquidation(payload_to_dict(payload))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/cartolas")
def upload_cartolas(files: List[UploadFile] = File(...)):
    overall_started_at = time.perf_counter()
    parsed = []
    temp_paths = []
    try:
        for index, file in enumerate(files, start=1):
            file_started_at = time.perf_counter()
            suffix = os.path.splitext(file.filename or "")[1]
            write_started_at = time.perf_counter()
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                shutil.copyfileobj(file.file, tmp)
                size_bytes = tmp.tell()
                temp_paths.append(tmp.name)
            _log_timing(
                "api_cartolas",
                "write_temp_file",
                write_started_at,
                index=index,
                ext=(suffix or "none").lower(),
                bytes=size_bytes,
            )
            parse_started_at = time.perf_counter()
            parsed.append(cartola_parser.parse_cartola(temp_paths[-1]))
            _log_timing("api_cartolas", "parse_file", parse_started_at, index=index, ext=(suffix or "none").lower())
            _log_timing("api_cartolas", "file_total", file_started_at, index=index, ext=(suffix or "none").lower())
        _log_timing("api_cartolas", "request_total", overall_started_at, files=len(files))
        return {"cartolas": parsed}
    except Exception as exc:
        _log_timing("api_cartolas", "request_failed", overall_started_at, files=len(files))
        raise HTTPException(status_code=400, detail=f"No se pudo procesar la cartola: {exc}") from exc
    finally:
        for path in temp_paths:
            if os.path.exists(path):
                os.remove(path)


@app.post("/api/pdf")
def generate_pdf(
    payload: str = Form(...),
    external_pdf: Optional[UploadFile] = File(None),
):
    workdir = tempfile.mkdtemp(prefix="sitfa_pdf_")
    external_path = None
    try:
        data = payload_to_dict(LiquidationPayload(**json.loads(payload)))
        result = calculation_engine.calculate_liquidation(data)

        if external_pdf and external_pdf.filename:
            external_path = os.path.join(workdir, external_pdf.filename)
            with open(external_path, "wb") as target:
                shutil.copyfileobj(external_pdf.file, target)

        pdf_args = calculation_engine.build_pdf_args(
            data,
            result,
            external_pdf_path=external_path,
            output_dir=workdir,
        )
        pdf_path = pdf_engine.generar_pdf(**pdf_args)
        filename = os.path.basename(pdf_path)
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=filename,
            background=BackgroundTask(shutil.rmtree, workdir, ignore_errors=True),
        )
    except Exception as exc:
        shutil.rmtree(workdir, ignore_errors=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


INDEX_HTML = r"""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SITFA Liquidaciones</title>
  <style>
    :root {
      --ink: #20242c;
      --muted: #667085;
      --line: #d8dde8;
      --panel: #ffffff;
      --band: #eef2f7;
      --accent: #b43d30;
      --accent-2: #246b61;
      --blue: #245f9f;
      --warn: #9b5d18;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      background: #f7f8fb;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      min-height: 64px;
      padding: 12px 22px;
      background: #1f2937;
      color: white;
      border-bottom: 4px solid #c7b37b;
    }
    h1 { margin: 0; font-size: 20px; font-weight: 700; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(360px, 520px) 1fr;
      min-height: calc(100vh - 100px);
    }
    .left {
      overflow: auto;
      padding: 16px;
      border-right: 1px solid var(--line);
      background: var(--band);
    }
    .right {
      min-width: 0;
      padding: 16px;
      background: #f7f8fb;
    }
    section {
      padding: 14px;
      margin-bottom: 12px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 6px;
    }
    h2 {
      margin: 0 0 12px;
      font-size: 15px;
      line-height: 1.25;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }
    .grid-3 {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 10px;
    }
    label {
      display: grid;
      gap: 5px;
      font-size: 12px;
      color: var(--muted);
      min-width: 0;
    }
    input, select, textarea {
      width: 100%;
      min-height: 34px;
      border: 1px solid #c5ccd8;
      border-radius: 4px;
      padding: 7px 9px;
      color: var(--ink);
      background: white;
      font: inherit;
      font-size: 14px;
    }
    input.field-error, select.field-error, textarea.field-error {
      border-color: #c1121f;
      box-shadow: 0 0 0 2px rgba(193, 18, 31, .14);
    }
    textarea { min-height: 82px; resize: vertical; }
    .check-row {
      display: flex;
      align-items: center;
      gap: 16px;
      flex-wrap: wrap;
      margin-top: 10px;
    }
    .check-row label {
      display: flex;
      align-items: center;
      gap: 7px;
      color: var(--ink);
    }
    .check-row input { width: auto; min-height: auto; }
    .actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
    button {
      min-height: 34px;
      border: 0;
      border-radius: 4px;
      padding: 8px 12px;
      color: white;
      background: var(--blue);
      font-weight: 700;
      cursor: pointer;
    }
    button.secondary { background: var(--accent-2); }
    button.danger { background: var(--accent); }
    button.neutral { background: #4b5563; }
    .logout-link {
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      border-radius: 4px;
      padding: 8px 12px;
      color: white;
      background: #374151;
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
    }
    button.small {
      min-height: 28px;
      padding: 5px 8px;
      font-size: 12px;
    }
    button.icon-button {
      width: 30px;
      min-height: 28px;
      padding: 4px;
      line-height: 1;
    }
    button:disabled { opacity: .6; cursor: default; }
    .mini-table {
      width: 100%;
      border-collapse: collapse;
      margin-top: 10px;
      font-size: 13px;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px;
      text-align: left;
      vertical-align: top;
    }
    th {
      color: #374151;
      background: #edf1f6;
      font-size: 12px;
      text-transform: uppercase;
    }
    .result-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }
    .total {
      min-width: 220px;
      padding: 12px 14px;
      background: white;
      border: 1px solid var(--line);
      border-radius: 6px;
      text-align: right;
    }
    .total span { display: block; color: var(--muted); font-size: 12px; }
    .total strong { display: block; margin-top: 4px; font-size: 22px; }
    .table-wrap {
      overflow: auto;
      background: white;
      border: 1px solid var(--line);
      border-radius: 6px;
    }
    .summary-wrap {
      margin-top: 12px;
      overflow: auto;
      background: white;
      border: 1px solid var(--line);
      border-radius: 6px;
    }
    .summary-wrap h2 {
      margin: 0;
      padding: 11px 12px;
      border-bottom: 1px solid var(--line);
      background: #edf1f6;
    }
    .summary-table {
      width: 100%;
      min-width: 620px;
      border-collapse: collapse;
    }
    .summary-table .amount {
      text-align: right;
      white-space: nowrap;
      font-weight: 700;
    }
    .amount.negative {
      color: #b42318;
    }
    .summary-table .total-row td {
      background: #f3f6fa;
      font-size: 15px;
      font-weight: 700;
    }
    .calc-table {
      width: 100%;
      min-width: 780px;
      border-collapse: collapse;
    }
    .status {
      min-height: 22px;
      color: var(--warn);
      font-size: 13px;
      margin-top: 8px;
    }
    .detail-panel {
      margin-top: 12px;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #f9fafc;
    }
    .detail-title {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
    }
    .detail-title strong {
      font-size: 14px;
    }
    .scroll-table {
      max-height: 260px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: white;
    }
    .scroll-table .mini-table {
      margin-top: 0;
    }
    .hidden { display: none !important; }
    .file-input-hidden {
      position: absolute;
      width: 1px;
      height: 1px;
      opacity: 0;
      pointer-events: none;
    }
    .modal-backdrop {
      position: fixed;
      inset: 0;
      z-index: 20;
      display: grid;
      place-items: center;
      padding: 18px;
      background: rgba(17, 24, 39, .48);
    }
    .modal {
      width: min(760px, 100%);
      max-height: min(720px, 92vh);
      overflow: hidden;
      background: white;
      border: 1px solid var(--line);
      border-radius: 6px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, .25);
    }
    .modal-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: #f3f6fa;
    }
    .modal-head h2 {
      margin: 0;
    }
    .modal-body {
      max-height: calc(min(720px, 92vh) - 58px);
      overflow: auto;
      padding: 12px;
    }
    footer {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      min-height: 36px;
      padding: 8px 18px;
      color: #667085;
      background: #eef2f7;
      border-top: 1px solid var(--line);
      font-size: 12px;
    }
    @media (max-width: 980px) {
      main { grid-template-columns: 1fr; }
      .left { border-right: 0; border-bottom: 1px solid var(--line); }
      .result-head { align-items: stretch; flex-direction: column; }
      .total { text-align: left; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Unidad de Liquidaciones Especializadas de Concepción</h1>
    <div class="actions">
      <button id="ipcBtn" class="neutral" type="button">Ver IPC</button>
      <button id="imrBtn" class="neutral" type="button">Ver IMR</button>
      <button id="pdfBtn" class="danger" type="button">Generar PDF</button>
      <a id="logoutLink" class="logout-link" href="/logout">Salir</a>
    </div>
  </header>

  <main>
    <div class="left">
      <section>
        <h2>1. Datos de la causa</h2>
        <div class="grid">
          <label>Tribunal<select id="tribunal"></select></label>
          <label>RIT<input id="rit" placeholder="Z-1234-2026"></label>
          <label>Cuenta LAV<input id="lav"></label>
          <label>Fecha de Pago<select id="fecha_pago"></select></label>
          <label>Beneficiario<input id="beneficiario"></label>
          <label>Alimentante<input id="alimentante"></label>
          <label>Iniciales<input id="iniciales" maxlength="6"></label>
        </div>
        <div class="actions" style="margin-top:10px">
          <button class="neutral" type="button" onclick="pasteSitfaData()">Pegar datos SITFA</button>
        </div>
      </section>

      <section>
        <h2>2. Periodo y pensión</h2>
        <div class="grid">
          <label>Desde mes<select id="mes_desde"></select></label>
          <label>Desde año<select id="ano_desde"></select></label>
          <label>Hasta mes<select id="mes_hasta"></select></label>
          <label>Hasta año<select id="ano_hasta"></select></label>
          <label>Pensión mensual<input id="pension" value="$0"></label>
          <label>Reajuste<select id="reajuste_tipo"></select></label>
          <label>Meses a descontar<input id="descuento_meses" type="number" min="0" value="0"></label>
        </div>
        <div class="check-row">
          <label><input id="tiene_arrastre" type="checkbox">Existe deuda de arrastre</label>
          <label><input id="cese_alimentos" type="checkbox">Cese de alimentos</label>
        </div>
      </section>

      <section id="arrastreBox" class="hidden">
        <h2>3. Deuda anterior</h2>
        <div class="grid">
          <label>Monto adeudado<input id="monto_arrastre" value="$0"></label>
          <label>Referencia<input id="referencia_arrastre"></label>
          <label>Desde mes<select id="arrastre_mes_desde"></select></label>
          <label>Desde año<select id="arrastre_ano_desde"></select></label>
          <label>Hasta mes<select id="arrastre_mes_hasta"></select></label>
          <label>Hasta año<select id="arrastre_ano_hasta"></select></label>
          <label>Pensión final arrastre<input id="pension_final_arrastre" value="$0"></label>
        </div>
      </section>

      <section>
        <h2>4. Cambios de monto</h2>
        <div class="grid-3">
          <label>Mes<select id="hist_mes"></select></label>
          <label>Año<select id="hist_ano"></select></label>
          <label>Monto<input id="hist_monto" value="$0"></label>
        </div>
        <div class="actions" style="margin-top:10px">
          <button class="secondary" type="button" onclick="addHistory()">Agregar cambio</button>
          <button class="neutral" type="button" onclick="clearHistory()">Limpiar</button>
        </div>
        <table class="mini-table" id="historyTable"></table>
      </section>

      <section>
        <h2>5. Cartolas</h2>
        <input id="cartolaFiles" class="file-input-hidden" type="file" multiple accept=".xls,.xlsx,.csv" tabindex="-1">
        <div class="actions" style="margin-top:10px">
          <button class="secondary" type="button" onclick="document.getElementById('cartolaFiles').click()">Agregar cartola</button>
          <button class="neutral" type="button" onclick="clearCartolas()">Limpiar cartolas</button>
        </div>
        <table class="mini-table" id="cartolaTable"></table>
        <div id="cartolaDetail" class="detail-panel hidden"></div>
      </section>

      <section>
        <h2>6. Ajustes manuales</h2>
        <div class="grid">
          <label>Fecha<input id="adj_fecha" type="date"></label>
          <label>Tipo<select id="adj_tipo"><option>Abono</option><option>Cargo</option></select></label>
          <label>Descripción<input id="adj_desc"></label>
          <label>Monto<input id="adj_monto" value="$0"></label>
        </div>
        <div class="actions" style="margin-top:10px">
          <button class="secondary" type="button" onclick="addAdjustment()">Agregar ajuste</button>
          <button class="neutral" type="button" onclick="clearAdjustments()">Limpiar</button>
        </div>
        <table class="mini-table" id="adjustmentTable"></table>
      </section>

      <section>
        <h2>7. Observaciones y anexo</h2>
        <label>Observaciones<textarea id="observaciones"></textarea></label>
        <label style="margin-top:10px">PDF externo<input id="externalPdf" type="file" accept=".pdf"></label>
      </section>
    </div>

    <div class="right">
      <div class="result-head">
        <div>
          <h2>Detalle de cálculo</h2>
          <div id="status" class="status"></div>
        </div>
        <div class="total">
          <span>Saldo final</span>
          <strong id="saldo">$0</strong>
        </div>
      </div>
      <div class="table-wrap" id="periodTableWrap">
        <table class="calc-table" id="resultTable">
          <thead>
            <tr><th>Desde</th><th>Hasta</th><th>Meses</th><th>Reajuste</th><th>Pensión reajustada</th><th>Total</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="summary-wrap">
        <h2>Resumen de deuda</h2>
        <table class="summary-table" id="summaryTable">
          <tbody></tbody>
        </table>
      </div>
    </div>
  </main>
  <footer>Versión {{APP_VERSION}}</footer>
  <div id="indicatorModal" class="modal-backdrop hidden"></div>

  <script src="https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js"></script>
  <script>
    let optionsData = {};
    let historialPensiones = [];
    let ajustesManuales = [];
    let cartolas = [];
    let lastPayload = null;
    let calculateTimer = null;
    let isBooting = true;

    function apiPath(path) {
      const base = window.location.pathname.startsWith("/liquidaciones") ? "/liquidaciones" : "";
      return `${base}${path}`;
    }

    function appPath(path) {
      return apiPath(path);
    }

    function fillSelect(id, values, defaultValue) {
      const el = document.getElementById(id);
      el.innerHTML = values.map(v => `<option value="${String(v)}">${String(v)}</option>`).join("");
      if (defaultValue) el.value = defaultValue;
    }

    function todayDefaults() {
      const now = new Date();
      const monthName = optionsData.meses[now.getMonth()] || optionsData.meses[0];
      const year = String(now.getFullYear());
      ["mes_desde", "mes_hasta", "hist_mes", "arrastre_mes_desde", "arrastre_mes_hasta"].forEach(id => fillSelect(id, optionsData.meses, monthName));
      ["ano_desde", "ano_hasta", "hist_ano", "arrastre_ano_desde", "arrastre_ano_hasta"].forEach(id => fillSelect(id, optionsData.anos, year));
    }

    async function boot() {
      const res = await fetch(apiPath("/api/options"));
      optionsData = await res.json();
      fillSelect("tribunal", ["", ...optionsData.tribunales]);
      fillSelect("fecha_pago", ["", ...optionsData.fecha_pago]);
      fillSelect("reajuste_tipo", optionsData.reajustes, "IPC (Semestral)");
      todayDefaults();
      document.getElementById("adj_fecha").value = todayIsoDate();
      renderHistory();
      renderAdjustments();
      renderCartolas();
      bindAutoCalculate();
      bindCauseRequiredFields();
      isBooting = false;
      scheduleCalculate();
    }

    function value(id) { return document.getElementById(id).value; }
    function checked(id) { return document.getElementById(id).checked; }

    const causeRequiredFields = [
      {id: "tribunal", label: "Tribunal"},
      {id: "rit", label: "RIT"},
      {id: "lav", label: "Cuenta LAV"},
      {id: "fecha_pago", label: "Fecha de Pago"},
      {id: "beneficiario", label: "Beneficiario"},
      {id: "alimentante", label: "Alimentante"},
      {id: "iniciales", label: "Iniciales"},
    ];

    function todayIsoDate() {
      const now = new Date();
      const offset = now.getTimezoneOffset() * 60000;
      return new Date(now.getTime() - offset).toISOString().slice(0, 10);
    }

    function formatDateForDisplay(isoDate) {
      const [year, month, day] = String(isoDate || "").split("-");
      return year && month && day ? `${day}/${month}/${year}` : "";
    }

    function collectPayload() {
      return {
        tribunal: value("tribunal"),
        rit: value("rit"),
        lav: value("lav"),
        beneficiario: value("beneficiario"),
        alimentante: value("alimentante"),
        fecha_pago: value("fecha_pago"),
        pension: value("pension"),
        reajuste_tipo: value("reajuste_tipo"),
        mes_desde: value("mes_desde"),
        ano_desde: value("ano_desde"),
        mes_hasta: value("mes_hasta"),
        ano_hasta: value("ano_hasta"),
        descuento_meses: Number(value("descuento_meses") || 0),
        tiene_arrastre: checked("tiene_arrastre"),
        monto_arrastre: value("monto_arrastre"),
        referencia_arrastre: value("referencia_arrastre"),
        arrastre_mes_desde: value("arrastre_mes_desde"),
        arrastre_ano_desde: value("arrastre_ano_desde"),
        arrastre_mes_hasta: value("arrastre_mes_hasta"),
        arrastre_ano_hasta: value("arrastre_ano_hasta"),
        pension_final_arrastre: value("pension_final_arrastre"),
        iniciales: value("iniciales"),
        cese_alimentos: checked("cese_alimentos"),
        observaciones: value("observaciones"),
        historial_pensiones: historialPensiones,
        ajustes_manuales: ajustesManuales,
        cartolas: cartolas
      };
    }

    function renderRows(rows) {
      const body = document.querySelector("#resultTable tbody");
      body.innerHTML = rows.map(row => `<tr>${row.map(cell => `<td>${cell}</td>`).join("")}</tr>`).join("");
    }

    function renderSummary(data) {
      const resumen = data.resumen;
      const rows = [];
      if (!checked("cese_alimentos")) {
        rows.push(["Cargo", "Subtotal devengado periodo actual", resumen.cargo_actual]);
      }
      if (resumen.deuda_anterior !== 0) {
        const ref = value("referencia_arrastre");
        rows.push(["Cargo", `Monto liquidación anterior${ref ? " " + ref : ""}`, resumen.deuda_anterior]);
      }
      cartolas.forEach((cartola, index) => {
        const lav = cartola.lav_number || "N/A";
        const period = cartola.period && cartola.period !== "No detectado" ? ` (${cartola.period})` : "";
        rows.push(["Abono", `Cartola ${index + 1} - LAV N° ${lav}${period}`, -Number(cartola.total_abonos || 0)]);
      });
      resumen.ajustes_manuales.forEach(ajuste => {
        const sign = ajuste.tipo === "Cargo" ? 1 : -1;
        rows.push([ajuste.tipo, `${ajuste.desc || "Ajuste manual"}${ajuste.fecha ? " (" + ajuste.fecha + ")" : ""}`, sign * Number(ajuste.monto || 0)]);
      });
      rows.push(["Total", "Saldo final", resumen.total_final]);

      document.querySelector("#summaryTable tbody").innerHTML = rows.map(row => {
        const isTotal = row[0] === "Total";
        const amountClass = Number(row[2] || 0) < 0 ? "amount negative" : "amount";
        return `<tr class="${isTotal ? "total-row" : ""}"><td>${escapeHtml(row[0])}</td><td>${escapeHtml(row[1])}</td><td class="${amountClass}">${formatMoney(row[2])}</td></tr>`;
      }).join("");
    }

    function updatePeriodTableVisibility() {
      document.getElementById("periodTableWrap").classList.toggle("hidden", checked("cese_alimentos"));
    }

    async function calculate() {
      setStatus("");
      const payload = collectPayload();
      const res = await fetch(apiPath("/api/calculate"), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      if (!res.ok) {
        setStatus((await res.json()).detail || "No se pudo calcular.");
        return null;
      }
      const data = await res.json();
      alignSummaryWithVisibleTotals(data);
      lastPayload = payload;
      renderRows(data.rows_with_total);
      renderSummary(data);
      updatePeriodTableVisibility();
      document.getElementById("saldo").textContent = data.resumen.total_final_formateado;
      return data;
    }

    function parseMoneyValue(value) {
      const normalized = String(value ?? "")
        .replaceAll("$", "")
        .replaceAll(" ", "")
        .replaceAll("\u00a0", "")
        .split(",")[0]
        .replaceAll(".", "")
        .replace(/[^\d-]/g, "");
      const amount = parseInt(normalized, 10);
      return Number.isFinite(amount) ? amount : 0;
    }

    function alignSummaryWithVisibleTotals(data) {
      if (!data || !data.resumen || !Array.isArray(data.rows_with_total)) return;
      const totalRow = data.rows_with_total.find(row => Array.isArray(row) && row[0] === "TOTALES");
      if (!totalRow) return;

      const visibleCargo = checked("cese_alimentos") ? 0 : parseMoneyValue(totalRow[5]);
      const resumen = data.resumen;
      const deudaAnterior = Number(resumen.deuda_anterior || 0);
      const totalAbonos = Number(resumen.total_abonos || 0);
      const ajustes = Array.isArray(resumen.ajustes_manuales) ? resumen.ajustes_manuales : [];
      const totalAjusteCargos = ajustes
        .filter(ajuste => ajuste.tipo === "Cargo")
        .reduce((sum, ajuste) => sum + Number(ajuste.monto || 0), 0);
      const totalAjusteAbonos = ajustes
        .filter(ajuste => ajuste.tipo === "Abono")
        .reduce((sum, ajuste) => sum + Number(ajuste.monto || 0), 0);

      resumen.cargo_actual = visibleCargo;
      resumen.subtotal_general = visibleCargo + deudaAnterior + totalAjusteCargos;
      resumen.total_final = resumen.subtotal_general - totalAbonos - totalAjusteAbonos;
      resumen.total_final_formateado = formatMoney(resumen.total_final);
    }

    function scheduleCalculate() {
      if (isBooting) return;
      window.clearTimeout(calculateTimer);
      calculateTimer = window.setTimeout(calculate, 350);
    }

    function bindAutoCalculate() {
      const ignored = new Set(["cartolaFiles", "externalPdf"]);
      document.querySelectorAll("input, select, textarea").forEach(el => {
        if (ignored.has(el.id)) return;
        const eventName = el.tagName === "SELECT" || el.type === "checkbox" ? "change" : "input";
        el.addEventListener(eventName, scheduleCalculate);
      });
    }

    async function showIndicator(kind) {
      setStatus("");
      const res = await fetch(apiPath(`/api/indicators/${kind}`));
      if (!res.ok) {
        setStatus(`No se pudieron cargar los valores ${kind.toUpperCase()}.`);
        return;
      }
      const data = await res.json();
      const headerRow = data.headers.map(h => `<th>${escapeHtml(h)}</th>`).join("");
      const bodyRows = data.rows.map(row => {
        return `<tr>${row.map(cell => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`;
      }).join("");
      const modal = document.getElementById("indicatorModal");
      modal.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true">
          <div class="modal-head">
            <h2>${escapeHtml(data.title)}</h2>
            <button class="neutral small" type="button" onclick="closeIndicatorModal()">Cerrar</button>
          </div>
          <div class="modal-body">
            <table class="mini-table">
              <tr>${headerRow}</tr>
              ${bodyRows || '<tr><td colspan="3">No hay valores cargados.</td></tr>'}
            </table>
          </div>
        </div>
      `;
      modal.classList.remove("hidden");
    }

    function closeIndicatorModal() {
      const modal = document.getElementById("indicatorModal");
      modal.classList.add("hidden");
      modal.innerHTML = "";
    }

    async function pasteSitfaData() {
      setStatus("");
      try {
        const text = await readClipboardText();
        const data = parseSitfaClipboard(text);
        if (data.rit !== undefined) document.getElementById("rit").value = data.rit || "";
        if (data.tribunal) document.getElementById("tribunal").value = data.tribunal;
        if (data.beneficiario !== undefined) document.getElementById("beneficiario").value = data.beneficiario || "";
        if (data.alimentante !== undefined) document.getElementById("alimentante").value = data.alimentante || "";
        scheduleCalculate();
        setStatus("Datos SITFA pegados correctamente.");
      } catch (error) {
        setStatus("No se pudieron reconocer DTE/DDO en el texto copiado desde SITFA.");
      }
    }

    async function readClipboardText() {
      if (navigator.clipboard && window.isSecureContext) {
        return await navigator.clipboard.readText();
      }
      const text = window.prompt("Pegue aquí los datos copiados desde SITFA:");
      if (!text) throw new Error("Sin datos");
      return text;
    }

    function parseSitfaClipboard(text) {
      const trimmed = String(text || "").trim();
      if (!trimmed) throw new Error("Sin datos");

      if (trimmed.startsWith("{")) {
        return JSON.parse(trimmed);
      }

      const dte = parseSitfaSubject(trimmed, ["DTE", "Solicitante"]);
      const ddo = parseSitfaSubject(trimmed, ["DDO", "Solicitado"]);
      if (!dte && !ddo) throw new Error("No se encontraron DTE/DDO");

      return {
        beneficiario: dte ? `${dte.rut} ${dte.nombre}` : "",
        alimentante: ddo ? `${ddo.rut} ${ddo.nombre}` : "",
      };
    }

    function parseSitfaSubject(text, roles) {
      const normalized = text.replace(/\r/g, "\n").replace(/\u00a0/g, " ");
      const roleList = Array.isArray(roles) ? roles : [roles];
      const rutPattern = "([\\d.]{7,12}-[\\dkK])";

      let match = null;
      for (const role of roleList) {
        const rolePattern = role.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const pattern = new RegExp(
          `(?:^|\\n)\\s*Confirmado\\s+${rolePattern}\\.?\\s+${rutPattern}\\s+\\S+\\s+([\\s\\S]*?)(?=\\s+No\\s+\\S+\\s+No\\b)`,
          "i"
        );
        match = normalized.match(pattern);
        if (match) break;
      }
      if (!match) return null;

      return {
        rut: match[1].replace(/\./g, "").trim(),
        nombre: match[2].replace(/\s+/g, " ").trim(),
      };
    }

    function validateCauseRequiredFields() {
      const missing = [];
      let firstMissing = null;

      causeRequiredFields.forEach(field => {
        const el = document.getElementById(field.id);
        const isMissing = !String(el.value || "").trim();
        el.classList.toggle("field-error", isMissing);
        if (isMissing) {
          missing.push(field.label);
          if (!firstMissing) firstMissing = el;
        }
      });

      if (missing.length) {
        alert(`Faltan datos obligatorios en Datos de la causa:\n\n${missing.map(name => "- " + name).join("\n")}`);
        if (firstMissing) firstMissing.focus();
        return false;
      }
      return true;
    }

    function bindCauseRequiredFields() {
      causeRequiredFields.forEach(field => {
        const el = document.getElementById(field.id);
        ["input", "change"].forEach(eventName => {
          el.addEventListener(eventName, () => {
            if (String(el.value || "").trim()) el.classList.remove("field-error");
          });
        });
      });
    }

    async function generatePdf() {
      if (!validateCauseRequiredFields()) return;
      const calculated = await calculate();
      if (!calculated) return;
      const form = new FormData();
      form.append("payload", JSON.stringify(lastPayload));
      const external = document.getElementById("externalPdf").files[0];
      if (external) form.append("external_pdf", external);
      const res = await fetch(apiPath("/api/pdf"), { method: "POST", body: form });
      if (!res.ok) {
        setStatus((await res.json()).detail || "No se pudo generar el PDF.");
        return;
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Liquidacion_${value("rit") || "SITFA"}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    }

    function addHistory() {
      historialPensiones.push({mes: value("hist_mes"), ano: value("hist_ano"), monto: value("hist_monto")});
      renderHistory();
      scheduleCalculate();
    }

    function clearHistory() {
      historialPensiones = [];
      renderHistory();
      scheduleCalculate();
    }

    function removeHistory(index) {
      historialPensiones.splice(index, 1);
      renderHistory();
      scheduleCalculate();
    }

    function renderHistory() {
      document.getElementById("historyTable").innerHTML =
        "<tr><th>Mes</th><th>Año</th><th>Monto</th><th>Eliminar</th></tr>" +
        historialPensiones.map((h, index) => `<tr><td>${escapeHtml(h.mes)}</td><td>${escapeHtml(h.ano)}</td><td>${escapeHtml(h.monto)}</td><td><button class="danger small icon-button" type="button" title="Eliminar cambio" aria-label="Eliminar cambio" onclick="removeHistory(${index})">&#128465;</button></td></tr>`).join("");
    }

    function addAdjustment() {
      ajustesManuales.push({
        fecha: formatDateForDisplay(value("adj_fecha")),
        desc: value("adj_desc"),
        tipo: value("adj_tipo"),
        monto: value("adj_monto")
      });
      renderAdjustments();
      scheduleCalculate();
    }

    function clearAdjustments() {
      ajustesManuales = [];
      renderAdjustments();
      scheduleCalculate();
    }

    function removeAdjustment(index) {
      ajustesManuales.splice(index, 1);
      renderAdjustments();
      scheduleCalculate();
    }

    function renderAdjustments() {
      document.getElementById("adjustmentTable").innerHTML =
        "<tr><th>Fecha</th><th>Tipo</th><th>Descripción</th><th>Monto</th><th>Eliminar</th></tr>" +
        ajustesManuales.map((a, index) => `<tr><td>${escapeHtml(a.fecha)}</td><td>${escapeHtml(a.tipo)}</td><td>${escapeHtml(a.desc)}</td><td>${escapeHtml(a.monto)}</td><td><button class="danger small icon-button" type="button" title="Eliminar ajuste" aria-label="Eliminar ajuste" onclick="removeAdjustment(${index})">&#128465;</button></td></tr>`).join("");
    }

    function renderCartolas() {
      document.getElementById("cartolaTable").innerHTML =
        "<tr><th>LAV</th><th>Periodo</th><th>Abonos</th><th>Mov.</th><th>Detalle</th><th>Eliminar</th></tr>" +
        cartolas.map((c, index) => `<tr><td>${escapeHtml(c.lav_number)}</td><td>${escapeHtml(c.period)}</td><td>${formatMoney(c.total_abonos)}</td><td>${c.movimientos.length}</td><td><button class="neutral small" type="button" onclick="showCartolaMovements(${index})">Ver abonos</button></td><td><button class="danger small icon-button" type="button" title="Eliminar cartola" aria-label="Eliminar cartola" onclick="removeCartola(${index})">&#128465;</button></td></tr>`).join("");
      if (!cartolas.length) closeCartolaMovements();
    }

    function removeCartola(index) {
      cartolas.splice(index, 1);
      renderCartolas();
      closeCartolaMovements();
      scheduleCalculate();
    }

    function formatMoney(value) {
      const number = Number(value || 0);
      const sign = number < 0 ? "-" : "";
      return `$${sign}${Math.abs(Math.trunc(number)).toLocaleString("es-CL")}`;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function showCartolaMovements(index) {
      const cartola = cartolas[index];
      if (!cartola) return;
      const detail = document.getElementById("cartolaDetail");
      const rows = cartola.movimientos.length
        ? cartola.movimientos.map(mov => {
            const fecha = Array.isArray(mov) ? mov[0] : mov.fecha;
            const desc = Array.isArray(mov) ? mov[1] : mov.desc;
            const monto = Array.isArray(mov) ? mov[2] : mov.monto;
            return `<tr><td>${escapeHtml(fecha)}</td><td>${escapeHtml(desc)}</td><td>${formatMoney(monto)}</td></tr>`;
          }).join("")
        : `<tr><td colspan="3">No se encontraron abonos en esta cartola.</td></tr>`;

      detail.innerHTML = `
        <div class="detail-title">
          <strong>Abonos de cartola ${index + 1} - LAV ${escapeHtml(cartola.lav_number)}</strong>
          <button class="neutral small" type="button" onclick="closeCartolaMovements()">Cerrar</button>
        </div>
        <div class="scroll-table">
          <table class="mini-table">
            <tr><th>Fecha</th><th>Descripción</th><th>Monto</th></tr>
            ${rows}
          </table>
        </div>
      `;
      detail.classList.remove("hidden");
    }

    function closeCartolaMovements() {
      const detail = document.getElementById("cartolaDetail");
      detail.classList.add("hidden");
      detail.innerHTML = "";
    }

    function cleanCartolaAmount(value) {
      if (value === null || value === undefined) return 0;
      const text = String(value).trim();
      if (!text || text.toLowerCase() === "nan") return 0;
      const normalized = text
        .replaceAll("$", "")
        .replaceAll(" ", "")
        .replaceAll("\u00a0", "")
        .split(",")[0]
        .replaceAll(".", "")
        .replace(/[^\d-]/g, "");
      const amount = parseInt(normalized, 10);
      return Number.isFinite(amount) ? amount : 0;
    }

    function cellText(value) {
      return String(value ?? "").trim();
    }

    function detectLavFromRows(rows) {
      const rowsToCheck = Math.min(rows.length, 5);
      for (let rowIndex = 0; rowIndex < rowsToCheck; rowIndex += 1) {
        const row = rows[rowIndex] || [];
        for (const cell of row) {
          const match = cellText(cell).match(/^LAV:\s*["']?(\d+)["']?/i);
          if (match) return match[1];
        }
      }
      return "No detectada";
    }

    function detectRutFromRows(rows) {
      const text = rows.map(row => row.map(cellText).join(" ")).join("\n");
      const withDots = text.match(/\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b/);
      if (withDots) return withDots[0];
      const withDash = text.match(/\b\d{7,8}-[\dkK]\b/);
      if (withDash) return withDash[0];
      const compact = text.match(/RUT[:\s]+(\d{7,8}[\dkK])/i);
      if (compact) return `${compact[1].slice(0, -1)}-${compact[1].slice(-1)}`;
      return "No detectado";
    }

    function detectPeriodFromRows(rows) {
      if (rows.length < 4) return "No detectado";
      const rowText = (rows[3] || []).map(cellText).filter(Boolean).join(" ");
      const match = rowText.match(/Movimientos desde \d{2}\/\d{2}\/\d{4} hasta \d{2}\/\d{2}\/\d{4}/);
      return match ? match[0] : "No detectado";
    }

    function parseCartolaRows(rows, sourceName) {
      const normalizedRows = rows
        .map(row => Array.isArray(row) ? row : [])
        .filter(row => row.some(cell => cellText(cell) !== ""));
      const colCount = normalizedRows.reduce((max, row) => Math.max(max, row.length), 0);
      const lav = detectLavFromRows(normalizedRows);
      const rut = detectRutFromRows(normalizedRows);
      const period = detectPeriodFromRows(normalizedRows);
      const movimientos = [];
      let total = 0;

      if (colCount >= 3) {
        const amountIndex = colCount - 1;
        normalizedRows.forEach(row => {
          const amount = cleanCartolaAmount(row[amountIndex]);
          if (amount !== 0) {
            movimientos.push([cellText(row[0]).slice(0, 10), cellText(row[1]).slice(0, 50), amount]);
            total += amount;
          }
        });
      }

      if (!movimientos.length && colCount >= 2) {
        normalizedRows.forEach(row => {
          const amount = cleanCartolaAmount(row[row.length - 1]);
          if (amount > 0) {
            movimientos.push([cellText(row[0]).slice(0, 10), cellText(row[1]).slice(0, 50), amount]);
            total += amount;
          }
        });
      }

      return {
        source_name: sourceName,
        lav_number: lav,
        rut_dte: rut,
        period,
        total_abonos: total,
        movimientos,
      };
    }

    function readCartolaWorkbook(file) {
      return new Promise((resolve, reject) => {
        if (!window.XLSX) {
          reject(new Error("No se pudo cargar el lector de cartolas. Revise la conexión e intente nuevamente."));
          return;
        }
        const reader = new FileReader();
        reader.onload = event => {
          try {
            const data = new Uint8Array(event.target.result);
            const workbook = XLSX.read(data, {type: "array", cellDates: false});
            const firstSheetName = workbook.SheetNames[0];
            if (!firstSheetName) throw new Error("La cartola no tiene hojas.");
            const rows = XLSX.utils.sheet_to_json(workbook.Sheets[firstSheetName], {
              header: 1,
              raw: false,
              blankrows: false,
              defval: "",
            });
            resolve(parseCartolaRows(rows, file.name));
          } catch (error) {
            reject(error);
          }
        };
        reader.onerror = () => reject(new Error("No se pudo leer el archivo."));
        reader.readAsArrayBuffer(file);
      });
    }

    async function loadCartolasLocally() {
      const input = document.getElementById("cartolaFiles");
      if (!input.files.length) return;
      setStatus("Leyendo cartolas en el navegador...");
      try {
        const parsed = [];
        for (const file of input.files) {
          parsed.push(await readCartolaWorkbook(file));
        }
        cartolas = cartolas.concat(parsed);
        if (cartolas[0] && !value("lav")) document.getElementById("lav").value = cartolas[0].lav_number;
        input.value = "";
        renderCartolas();
        setStatus("");
        scheduleCalculate();
      } catch (error) {
        setStatus(error.message || "No se pudieron leer las cartolas en el navegador.");
      }
    }

    function clearCartolas() {
      cartolas = [];
      document.getElementById("cartolaFiles").value = "";
      renderCartolas();
      closeCartolaMovements();
      scheduleCalculate();
    }

    function setStatus(text) {
      document.getElementById("status").textContent = text;
    }

    document.getElementById("pdfBtn").addEventListener("click", generatePdf);
    document.getElementById("ipcBtn").addEventListener("click", () => showIndicator("ipc"));
    document.getElementById("imrBtn").addEventListener("click", () => showIndicator("imr"));
    document.getElementById("logoutLink").href = appPath("/logout");
    document.getElementById("cartolaFiles").addEventListener("change", loadCartolasLocally);
    document.getElementById("tiene_arrastre").addEventListener("change", event => {
      document.getElementById("arrastreBox").classList.toggle("hidden", !event.target.checked);
      scheduleCalculate();
    });
    document.getElementById("cese_alimentos").addEventListener("change", updatePeriodTableVisibility);

    boot();
  </script>
</body>
</html>
"""
