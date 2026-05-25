import calendar
import re
from datetime import date
from itertools import groupby

import config
import utils


def _period_value(mes, ano):
    return int(ano) * 12 + config.MESES.index(mes)


def payment_due_day(fecha_pago, year=None, month=None):
    text = str(fecha_pago or "").strip().lower()
    if not text:
        return None

    if year is None or month is None:
        today = date.today()
        year = today.year
        month = today.month

    days_in_month = calendar.monthrange(int(year), int(month))[1]
    if text in {"primer dia", "primer día"}:
        return 1
    if text in {"ultimo dia", "último día"}:
        return days_in_month

    match = re.search(r"(\d+)", text)
    if not match:
        return None

    count = int(match.group(1))
    if "ultimo" in text or "último" in text:
        return max(1, days_in_month - count + 1)
    return min(days_in_month, count)


def max_liquidation_period(fecha_pago, today=None):
    today = today or date.today()
    due_day = payment_due_day(fecha_pago, today.year, today.month)
    year = today.year
    month = today.month

    if due_day and today.day < due_day:
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    return config.MESES[month - 1], str(year)


def validate_liquidation_until_period(data, today=None):
    fecha_pago = data.get("fecha_pago")
    if not fecha_pago:
        return

    max_month, max_year = max_liquidation_period(fecha_pago, today)
    selected_value = _period_value(data["mes_hasta"], data["ano_hasta"])
    max_value = _period_value(max_month, max_year)
    if selected_value > max_value:
        raise ValueError(
            f"Segun la Fecha de Pago seleccionada, solo puede liquidar hasta {max_month} {max_year}."
        )


def previous_period(month, year):
    month_index = config.MESES.index(month)
    year_value = int(year)
    month_index -= 1
    if month_index < 0:
        month_index = 11
        year_value -= 1
    return config.MESES[month_index], str(year_value)


def validate_arrastre(data):
    if not data.get("tiene_arrastre"):
        return

    required = [
        ("monto_arrastre", "Monto adeudado"),
        ("arrastre_mes_desde", "Desde mes"),
        ("arrastre_ano_desde", "Desde año"),
        ("arrastre_mes_hasta", "Hasta mes"),
        ("arrastre_ano_hasta", "Hasta año"),
        ("pension_final_arrastre", "Pensión final arrastre"),
    ]
    missing = []
    for key, label in required:
        value = str(data.get(key, "")).strip()
        if not value:
            missing.append(label)

    if utils.limpiar_monto(data.get("monto_arrastre", 0)) <= 0:
        missing.append("Monto adeudado mayor a $0")
    if utils.limpiar_monto(data.get("pension_final_arrastre", 0)) <= 0:
        missing.append("Pensión final arrastre mayor a $0")

    if missing:
        raise ValueError("Faltan datos obligatorios en Deuda anterior: " + ", ".join(missing))

    expected_month, expected_year = previous_period(data["mes_desde"], data["ano_desde"])
    if data.get("arrastre_mes_hasta") != expected_month or str(data.get("arrastre_ano_hasta")) != expected_year:
        raise ValueError(
            f"El periodo Hasta de Deuda anterior debe ser {expected_month} {expected_year}."
        )

    arrastre_start = _period_value(data["arrastre_mes_desde"], data["arrastre_ano_desde"])
    arrastre_end = _period_value(data["arrastre_mes_hasta"], data["arrastre_ano_hasta"])
    if arrastre_start > arrastre_end:
        raise ValueError("El periodo Desde de Deuda anterior no puede ser posterior al periodo Hasta.")


def _normalize_history(historial_pensiones):
    history = []
    for item in historial_pensiones or []:
        mes = item.get("mes", "")
        ano = str(item.get("ano", ""))
        if mes not in config.MESES or not ano.isdigit():
            continue
        monto = utils.limpiar_monto(item.get("monto", 0), admitir_decimales=True)
        history.append(
            {
                "mes": mes,
                "ano": ano,
                "monto": monto,
                "mes_idx": config.MESES.index(mes),
                "ano_val": int(ano),
            }
        )
    return sorted(history, key=lambda x: (x["ano_val"], x["mes_idx"]))


def _normalize_adjustments(ajustes):
    normalized = []
    for item in ajustes or []:
        tipo = item.get("tipo", "Abono")
        if tipo not in ("Abono", "Cargo"):
            tipo = "Abono"
        normalized.append(
            {
                "fecha": str(item.get("fecha", "")),
                "desc": str(item.get("desc", "")),
                "tipo": tipo,
                "monto": utils.limpiar_monto(item.get("monto", 0)),
            }
        )
    return normalized


def _normalize_cartolas(cartolas):
    normalized = []
    for cartola in cartolas or []:
        movimientos = []
        for mov in cartola.get("movimientos", []):
            if isinstance(mov, dict):
                fecha = mov.get("fecha", "")
                desc = mov.get("desc", "")
                monto = mov.get("monto", 0)
            else:
                fecha = mov[0] if len(mov) > 0 else ""
                desc = mov[1] if len(mov) > 1 else ""
                monto = mov[2] if len(mov) > 2 else 0
            movimientos.append((str(fecha), str(desc), utils.limpiar_monto(monto)))

        total_abonos = cartola.get("total_abonos")
        if total_abonos is None:
            total_abonos = sum(mov[2] for mov in movimientos)

        normalized.append(
            {
                "path": cartola.get("path", ""),
                "lav_number": str(cartola.get("lav_number", "N/A")),
                "rut_dte": str(cartola.get("rut_dte", "No detectado")),
                "period": str(cartola.get("period", "No detectado")),
                "total_abonos": utils.limpiar_monto(total_abonos),
                "movimientos": movimientos,
            }
        )
    return normalized


def _normalize_emolumentos(emolumentos):
    periodos = {}
    for item in emolumentos or []:
        mes = item.get("mes", "")
        ano = str(item.get("ano", ""))
        if mes not in config.MESES or not ano.isdigit():
            periodo = str(item.get("periodo", ""))
            if len(periodo) == 6 and periodo.isdigit():
                mes_num = int(periodo[4:6])
                if mes_num < 1 or mes_num > 12:
                    continue
                mes = config.MESES[mes_num - 1]
                ano = periodo[:4]
            else:
                continue

        key = (mes, ano)
        current = periodos.setdefault(
            key,
            {
                "mes": mes,
                "ano": ano,
                "periodo": f"{ano}{config.MESES.index(mes) + 1:02d}",
                "estado": str(item.get("estado", "")),
                "renta_imponible": 0,
            },
        )
        current["renta_imponible"] += utils.limpiar_monto(item.get("renta_imponible", 0))

    return sorted(
        periodos.values(),
        key=lambda x: (int(x["ano"]), config.MESES.index(x["mes"])),
    )


def _ipc_rows(data, history):
    m1 = data["mes_desde"]
    a1 = str(data["ano_desde"])
    m2 = data["mes_hasta"]
    a2 = str(data["ano_hasta"])
    reajuste_tipo = data["reajuste_tipo"]

    p_corriente = utils.limpiar_monto(data["pension"], admitir_decimales=False)
    if data.get("tiene_arrastre"):
        p_corriente = utils.limpiar_monto(data.get("pension_final_arrastre", 0), admitir_decimales=False)

    salto = 1 if "Mensual" in reajuste_tipo else 6 if "Semestral" in reajuste_tipo else 12
    start_date_val = _period_value(m1, a1)
    end_date_val = _period_value(m2, a2)

    break_points_vals = [start_date_val]
    for h in history:
        h_val = h["ano_val"] * 12 + h["mes_idx"]
        if start_date_val < h_val <= end_date_val:
            break_points_vals.append(h_val)
    break_points_vals.append(end_date_val + 1)
    break_points_vals = sorted(set(break_points_vals))

    tramos = []
    is_first_sub_period = True
    descuento_meses = int(data.get("descuento_meses") or 0)

    for i in range(len(break_points_vals) - 1):
        period_start_val = break_points_vals[i]
        period_end_val = break_points_vals[i + 1] - 1
        if period_start_val > period_end_val:
            continue

        p_start_m = config.MESES[period_start_val % 12]
        p_start_a = str(period_start_val // 12)
        p_end_m = config.MESES[period_end_val % 12]
        p_end_a = str(period_end_val // 12)

        descuento = descuento_meses if is_first_sub_period else 0
        tramos.extend(
            utils.generar_tramos_segun_reajuste(
                p_start_m, p_start_a, p_end_m, p_end_a, reajuste_tipo, descuento
            )
        )
        is_first_sub_period = False

    rows = []
    total = 0
    for tramo in tramos:
        f_m, f_a = tramo["inicio_mes"], tramo["inicio_ano"]
        t_m, t_a = tramo["fin_mes"], tramo["fin_ano"]
        inc = tramo["cantidad_meses"]

        es_mes_de_cambio_manual = False
        for cambio in history:
            if cambio["mes"] == f_m and cambio["ano"] == f_a:
                p_corriente = cambio["monto"]
                es_mes_de_cambio_manual = True

        var_decimal = 0.0
        es_primer_tramo_global = f_m == m1 and f_a == a1
        debe_reajustar = False
        if not es_mes_de_cambio_manual:
            if not es_primer_tramo_global:
                debe_reajustar = True
            elif descuento_meses > 0 and descuento_meses % salto == 0:
                debe_reajustar = True

        if debe_reajustar:
            m_v_act, a_v_act = utils.calcular_proximo_periodo(f_m, f_a, -1, config.MESES)
            p_act = utils.obtener_puntos_ipc(m_v_act, a_v_act)
            m_v_base, a_v_base = utils.calcular_proximo_periodo(m_v_act, a_v_act, -salto, config.MESES)
            p_ant = utils.obtener_puntos_ipc(m_v_base, a_v_base)
            if p_act and p_ant:
                var_decimal = max(0, (p_act / p_ant) - 1)

        pension_reajustada = int(p_corriente * (1 + var_decimal))
        p_corriente = pension_reajustada
        subtotal = inc * pension_reajustada
        rows.append(
            [
                f"{f_m}-{f_a}",
                f"{t_m}-{t_a}",
                inc,
                f"{(var_decimal * 100):.2f}%",
                utils.formato_moneda(pension_reajustada),
                utils.formato_moneda(subtotal),
            ]
        )
        total += subtotal

    return rows, total


def _utm_rows(data, history):
    total_m = _total_months(data)
    monto_utm_actual = utils.limpiar_monto(data["pension"], admitir_decimales=True)
    rows = []
    total = 0

    for curr in range(total_m):
        f_m, f_a = utils.calcular_proximo_periodo(
            data["mes_desde"], str(data["ano_desde"]), curr, config.MESES
        )
        for cambio in history:
            if cambio["mes"] == f_m and cambio["ano"] == f_a:
                monto_utm_actual = cambio["monto"]

        valor_utm_mes = utils.obtener_valor_utm(f_m, f_a, config.MESES) or 0
        monto_en_pesos = int(monto_utm_actual * valor_utm_mes)
        rows.append(
            [
                f"{f_m}-{f_a}",
                f"{f_m}-{f_a}",
                1,
                f"{monto_utm_actual:,.5f}".replace(",", "X").replace(".", ",").replace("X", "."),
                utils.formato_moneda(valor_utm_mes),
                utils.formato_moneda(monto_en_pesos),
            ]
        )
        total += monto_en_pesos

    return rows, total


def _imr_rows(data, history):
    total_m = _total_months(data)
    porcentaje_actual = utils.limpiar_monto(
        str(data["pension"]).replace("%", ""), admitir_decimales=True
    ) / 100
    periodos = []

    for curr in range(total_m):
        f_m, f_a = utils.calcular_proximo_periodo(
            data["mes_desde"], str(data["ano_desde"]), curr, config.MESES
        )
        for cambio in history:
            if cambio["mes"] == f_m and cambio["ano"] == f_a:
                porcentaje_actual = cambio["monto"] / 100

        valor_imr_mes = utils.obtener_valor_imr(f_m, f_a, config.MESES) or 0
        monto_en_pesos = int(porcentaje_actual * valor_imr_mes)
        periodos.append(
            {
                "fecha_str": f"{f_m}-{f_a}",
                "porcentaje": porcentaje_actual,
                "valor_imr": valor_imr_mes,
                "pension_reajustada": monto_en_pesos,
                "total_pesos": monto_en_pesos,
            }
        )

    rows = []
    total = 0
    for clave, grupo in groupby(
        periodos, key=lambda x: (x["porcentaje"], x["valor_imr"], x["pension_reajustada"])
    ):
        lista_grupo = list(grupo)
        desde = lista_grupo[0]["fecha_str"]
        hasta = lista_grupo[-1]["fecha_str"]
        meses = len(lista_grupo)
        porcentaje, _valor_imr, pension_reajustada = clave
        total_tramo = meses * lista_grupo[0]["total_pesos"]
        rows.append(
            [
                desde,
                hasta,
                meses,
                f"{porcentaje:.2%}",
                utils.formato_moneda(pension_reajustada),
                utils.formato_moneda(total_tramo),
            ]
        )
        total += total_tramo

    return rows, total


def _emolumentos_rows(data, history):
    total_m = _total_months(data)
    porcentaje_actual = utils.limpiar_monto(
        str(data["pension"]).replace("%", ""), admitir_decimales=True
    ) / 100
    emolumentos = _normalize_emolumentos(data.get("emolumentos"))
    renta_por_periodo = {
        (item["mes"], item["ano"]): item["renta_imponible"]
        for item in emolumentos
    }

    rows = []
    total = 0
    for curr in range(total_m):
        f_m, f_a = utils.calcular_proximo_periodo(
            data["mes_desde"], str(data["ano_desde"]), curr, config.MESES
        )
        for cambio in history:
            if cambio["mes"] == f_m and cambio["ano"] == f_a:
                porcentaje_actual = cambio["monto"] / 100

        renta_imponible = renta_por_periodo.get((f_m, f_a), 0)
        descuentos_legales = int(renta_imponible * 0.20)
        base_calculo = renta_imponible - descuentos_legales
        monto_en_pesos = int(porcentaje_actual * base_calculo)
        rows.append(
            [
                f"{f_m}-{f_a}",
                f"{f_m}-{f_a}",
                utils.formato_moneda(renta_imponible),
                utils.formato_moneda(descuentos_legales),
                utils.formato_moneda(base_calculo),
                f"{porcentaje_actual:.2%}",
                utils.formato_moneda(monto_en_pesos),
            ]
        )
        total += monto_en_pesos

    return rows, total


def _total_months(data):
    total_m = (
        (int(data["ano_hasta"]) - int(data["ano_desde"])) * 12
        + (config.MESES.index(data["mes_hasta"]) - config.MESES.index(data["mes_desde"]))
        + 1
    )
    if total_m <= 0:
        raise ValueError("El periodo hasta debe ser igual o posterior al periodo desde.")
    return total_m


def calculate_liquidation(data):
    utils.cargar_ipc_json_historico()
    utils.cargar_utm_historico()
    utils.cargar_imr_historico()

    validate_liquidation_until_period(data)
    validate_arrastre(data)
    _total_months(data)
    history = _normalize_history(data.get("historial_pensiones"))
    ajustes = _normalize_adjustments(data.get("ajustes_manuales"))
    cartolas = _normalize_cartolas(data.get("cartolas"))
    reajuste_tipo = data["reajuste_tipo"]
    if reajuste_tipo == "EMOLUMNETOS":
        reajuste_tipo = "EMOLUMENTOS"

    if reajuste_tipo == "UTM":
        rows, cargo_actual = _utm_rows(data, history)
    elif reajuste_tipo == "IMRM":
        rows, cargo_actual = _imr_rows(data, history)
    elif reajuste_tipo == "EMOLUMENTOS":
        rows, cargo_actual = _emolumentos_rows(data, history)
    else:
        rows, cargo_actual = _ipc_rows(data, history)

    total_periodos_visible = sum(utils.limpiar_monto(row[-1]) for row in rows)
    cargo_actual = 0 if data.get("cese_alimentos") else total_periodos_visible

    monto_arrastre = (
        utils.limpiar_monto(data.get("monto_arrastre", 0)) if data.get("tiene_arrastre") else 0
    )
    abonos_cartola = sum(c["total_abonos"] for c in cartolas)
    total_aj_cargos = sum(a["monto"] for a in ajustes if a["tipo"] == "Cargo")
    total_aj_abonos = sum(a["monto"] for a in ajustes if a["tipo"] == "Abono")
    subtotal = cargo_actual + monto_arrastre + total_aj_cargos
    total_final = subtotal - (abonos_cartola + total_aj_abonos)

    column_count = len(rows[0]) if rows else 6
    rows_with_total = rows + [
        ["TOTALES"] + [""] * (column_count - 2) + [utils.formato_moneda(total_periodos_visible)]
    ]

    resumen = {
        "cargo_actual": int(cargo_actual),
        "deuda_anterior": int(monto_arrastre),
        "total_abonos": int(abonos_cartola),
        "ajustes_manuales": ajustes,
        "subtotal_general": int(subtotal),
        "total_final": int(total_final),
        "total_final_formateado": utils.formato_moneda(int(total_final)),
    }

    return {
        "rows": rows,
        "rows_with_total": rows_with_total,
        "resumen": resumen,
        "cartolas": cartolas,
        "historial_pensiones": history,
    }


def build_pdf_args(data, result, external_pdf_path=None, output_dir=None):
    history = result.get("historial_pensiones", [])
    cartolas = result.get("cartolas", [])
    reajuste_tipo = data["reajuste_tipo"]
    if reajuste_tipo == "EMOLUMNETOS":
        reajuste_tipo = "EMOLUMENTOS"

    monto_pension_base_str = str(data["pension"])
    if reajuste_tipo == "UTM":
        if history:
            monto_final_utm = history[-1]["monto"]
        else:
            monto_final_utm = utils.limpiar_monto(data["pension"], admitir_decimales=True)
        monto_pension_base_str = (
            f"{utils.formato_moneda(monto_final_utm, decimales=5).replace('$', '').strip()} UTM"
        )
    elif reajuste_tipo != "IMRM" and reajuste_tipo != "EMOLUMENTOS":
        monto_pension_base_str = utils.formato_moneda(utils.limpiar_monto(data["pension"]))

    first_periodo_cartola = cartolas[0]["period"] if cartolas else "No detectado"
    lav = data.get("lav") or (cartolas[0]["lav_number"] if cartolas else "N/A")
    datos_cabecera = [
        ("Tribunal", data.get("tribunal", "")),
        ("RIT", data.get("rit", "")),
        ("Fecha de Pago", data.get("fecha_pago", "")),
        ("Periodo Cartola", first_periodo_cartola),
        ("Monto Pensión Base", monto_pension_base_str),
        ("Beneficiario", data.get("beneficiario", "")),
        ("Alimentante", data.get("alimentante", "")),
        ("Liquida hasta", f"{data['mes_hasta']} {data['ano_hasta']}"),
        ("Cuenta N° LAV", lav),
        ("Iniciales", str(data.get("iniciales", "")).upper()),
    ]

    if data.get("tiene_arrastre"):
        periodo_arrastre = (
            f"Desde {data.get('arrastre_mes_desde', '')} {data.get('arrastre_ano_desde', '')} "
            f"hasta {data.get('arrastre_mes_hasta', '')} {data.get('arrastre_ano_hasta', '')}"
        )
        datos_cabecera.append(("Último periodo liquidado", periodo_arrastre))
        datos_cabecera.append(("Pensión Final Arrastre", data.get("pension_final_arrastre", "")))

    ciudad = data.get("tribunal", "").split()[-1] if data.get("tribunal") else "Concepcion"
    return {
        "datos_causa": datos_cabecera,
        "items_tabla": result["rows"],
        "resumen": result["resumen"],
        "ciudad": ciudad,
        "reajuste_tipo": reajuste_tipo,
        "cartolas_data": cartolas,
        "referencia_deuda_anterior": data.get("referencia_arrastre", ""),
        "observaciones_finales": data.get("observaciones", ""),
        "external_pdf_path": external_pdf_path,
        "cese_alimentos": bool(data.get("cese_alimentos")),
        "output_dir": output_dir,
    }
