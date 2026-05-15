import os
import re
import sys
import time

import pandas as pd

import utils


def _log_timing(stage, started_at, **details):
    elapsed = time.perf_counter() - started_at
    detail_text = " ".join(f"{key}={value}" for key, value in details.items())
    print(f"[cartola_parser] {stage} elapsed={elapsed:.3f}s {detail_text}".rstrip(), file=sys.stderr, flush=True)


def read_cartola_dataframe(path):
    started_at = time.perf_counter()
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".csv":
            df = pd.read_csv(path, encoding="latin1", sep=None, engine="python")
        else:
            df = pd.read_excel(path, header=None)
    except Exception:
        _log_timing("read_dataframe_failed", started_at, ext=ext or "none")
        raise
    _log_timing("read_dataframe", started_at, ext=ext or "none", rows=len(df), cols=len(df.columns))
    return df


def parse_cartola(path):
    overall_started_at = time.perf_counter()
    ext = os.path.splitext(path)[1].lower() or "none"

    df = read_cartola_dataframe(path)

    started_at = time.perf_counter()
    lav_detectada = utils.buscar_lav_en_df(df)
    _log_timing("detect_lav", started_at, rows_checked=min(len(df), 5), cols=len(df.columns))

    started_at = time.perf_counter()
    rut_dte_detectado = utils.buscar_rut_en_df(df)
    _log_timing("detect_rut", started_at, rows=len(df), cols=len(df.columns))

    started_at = time.perf_counter()
    fecha_rango_detectada = "No detectado"
    if len(df) >= 4:
        combined_row_4_text = " ".join(df.iloc[3].dropna().astype(str).str.strip().tolist())
        match = re.search(
            r"Movimientos desde \d{2}/\d{2}/\d{4} hasta \d{2}/\d{2}/\d{4}",
            combined_row_4_text,
        )
        if match:
            fecha_rango_detectada = match.group(0)
    _log_timing("detect_period", started_at, rows=len(df), cols=len(df.columns))

    started_at = time.perf_counter()
    movimientos = []
    total = 0
    used_fallback = False

    if len(df.columns) >= 3:
        fecha_col_idx = 0
        desc_col_idx = 1
        monto_col_idx = len(df.columns) - 1

        for _, row in df.iterrows():
            monto = utils.limpiar_monto(row.iloc[monto_col_idx])
            if monto != 0:
                fecha = str(row.iloc[fecha_col_idx])[:10]
                desc = str(row.iloc[desc_col_idx])[:50]
                movimientos.append((fecha, desc, monto))
                total += monto

    if not movimientos and len(df.columns) >= 2:
        used_fallback = True
        for _, row in df.iterrows():
            monto = utils.limpiar_monto(row.iloc[-1])
            if monto > 0:
                fecha = str(row.iloc[0])[:10]
                desc = str(row.iloc[1])[:50]
                movimientos.append((fecha, desc, monto))
                total += monto
    _log_timing(
        "build_movements",
        started_at,
        rows=len(df),
        cols=len(df.columns),
        movements=len(movimientos),
        fallback=used_fallback,
    )

    _log_timing(
        "parse_total",
        overall_started_at,
        ext=ext,
        rows=len(df),
        cols=len(df.columns),
        movements=len(movimientos),
    )

    return {
        "path": path,
        "lav_number": lav_detectada,
        "rut_dte": rut_dte_detectado,
        "period": fecha_rango_detectada,
        "total_abonos": total,
        "movimientos": movimientos,
    }
