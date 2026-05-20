import os
import re
from collections import defaultdict

from pypdf import PdfReader

import config
import utils


PERIODO_RE = re.compile(r"^\s*(\d{6})\s+([A-Z/]+)(?:\s+([0-9.$]+))?")


def _period_to_month_year(periodo):
    year = periodo[:4]
    month_num = int(periodo[4:6])
    if month_num < 1 or month_num > 12:
        raise ValueError(f"Periodo invalido: {periodo}")
    return config.MESES[month_num - 1], year


def parse_emolumentos_pdf(path):
    if not os.path.exists(path):
        raise FileNotFoundError(path)

    reader = PdfReader(path)
    totals = defaultdict(lambda: {"estado": "", "renta_imponible": 0, "fuentes": 0})

    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            match = PERIODO_RE.match(line.replace("\xa0", " ").strip())
            if not match:
                continue

            periodo, estado, renta_raw = match.groups()
            mes, ano = _period_to_month_year(periodo)
            renta = utils.limpiar_monto(renta_raw or 0)
            current = totals[periodo]
            current["periodo"] = periodo
            current["mes"] = mes
            current["ano"] = ano
            current["estado"] = current["estado"] or estado
            current["renta_imponible"] += renta
            current["fuentes"] += 1

    rows = [totals[key] for key in sorted(totals.keys(), reverse=True)]
    return {
        "emolumentos": rows,
        "total_renta_imponible": sum(row["renta_imponible"] for row in rows),
    }
