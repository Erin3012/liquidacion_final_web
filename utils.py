import os
import pandas as pd
import re
import sys
import json
import config
from datetime import datetime

# --- DefiniciÃ³n de Rutas Absolutas ---
if getattr(sys, 'frozen', False):
    BASE_PATH = os.path.dirname(sys.executable)
else:
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

UTM_JSON_PATH = os.path.join(BASE_PATH, "utm.json")
IPC_JSON_PATH = os.path.join(BASE_PATH, "ipc.json")
IMR_JSON_PATH = os.path.join(BASE_PATH, "imr.json")

# --- Diccionarios Globales ---
BD_IPC_VALORES = {}
BD_UTM_VALORES = {}
BD_IMR_VALORES = {}
RUTA_CARPETA_INDICADORES = ""


def obtener_ruta_recurso(relative_path):
    """Obtiene la ruta absoluta de un recurso local."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def cargar_ipc_json_historico():
    """ Carga los datos de 'ipc.json' usando la ruta absoluta. """
    global BD_IPC_VALORES
    if os.path.exists(IPC_JSON_PATH):
        try:
            with open(IPC_JSON_PATH, "r", encoding="utf-8") as f:
                BD_IPC_VALORES = json.load(f)
        except Exception as e:
            print(f"âš ï¸ No se pudo procesar el archivo de IPC JSON: {e}")
    else:
        print(f"â„¹ï¸ Archivo '{IPC_JSON_PATH}' no encontrado.")

def cargar_imr_historico():
    """ Carga los datos de 'imr.json' usando la ruta absoluta. """
    global BD_IMR_VALORES
    if os.path.exists(IMR_JSON_PATH):
        try:
            with open(IMR_JSON_PATH, "r", encoding="utf-8-sig") as f:
                datos = json.load(f)
            for tramo in datos:
                if "IMRM" not in tramo and "IMR" in tramo:
                    tramo["IMRM"] = tramo["IMR"]
            BD_IMR_VALORES = datos
        except Exception as e:
            print(f"âš ï¸ No se pudo procesar el archivo de IMRM: {e}")
    else:
        print(f"â„¹ï¸ Archivo '{IMR_JSON_PATH}' no encontrado.")

def cargar_utm_historico():
    """ Carga los datos de 'utm.json' usando la ruta absoluta. """
    global BD_UTM_VALORES
    if os.path.exists(UTM_JSON_PATH):
        try:
            with open(UTM_JSON_PATH, "r", encoding="utf-8") as f:
                BD_UTM_VALORES = json.load(f)
        except Exception as e:
            print(f"âš ï¸ No se pudo procesar el archivo de UTM: {e}")
    else:
        print(f"â„¹ï¸ Archivo '{UTM_JSON_PATH}' no encontrado.")


def _write_json_atomic(path, data):
    directory = os.path.dirname(path)
    temp_path = os.path.join(directory, f".{os.path.basename(path)}.tmp")
    with open(temp_path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=4)
        file.write("\n")
    os.replace(temp_path, path)


def guardar_ipc_rows(rows):
    valores = {}
    for row in rows or []:
        if len(row) < 2:
            raise ValueError("Cada fila IPC debe tener periodo y valor.")
        periodo = str(row[0]).strip()
        if not re.fullmatch(r"\d{4}-\d{2}", periodo):
            raise ValueError(f"Periodo IPC invalido: {periodo}. Use formato YYYY-MM.")
        mes = int(periodo[5:7])
        if mes < 1 or mes > 12:
            raise ValueError(f"Mes IPC invalido: {periodo}.")
        if periodo in valores:
            raise ValueError(f"Periodo IPC duplicado: {periodo}.")
        try:
            valor = float(str(row[1]).strip().replace(",", "."))
        except ValueError as exc:
            raise ValueError(f"Valor IPC invalido para {periodo}.") from exc
        valores[periodo] = valor

    if not valores:
        raise ValueError("Debe existir al menos un valor IPC.")

    ordenado = {key: valores[key] for key in sorted(valores)}
    _write_json_atomic(IPC_JSON_PATH, ordenado)
    cargar_ipc_json_historico()
    return ordenado


def guardar_imr_rows(rows):
    valores = []
    seen = set()
    for row in rows or []:
        if len(row) < 3:
            raise ValueError("Cada fila IMRM debe tener Desde, Hasta y Valor.")
        desde = str(row[0]).strip()
        hasta = str(row[1]).strip()
        try:
            datetime.strptime(desde, "%d/%m/%Y")
            datetime.strptime(hasta, "%d/%m/%Y")
        except ValueError as exc:
            raise ValueError("Las fechas IMRM deben usar formato DD/MM/YYYY.") from exc
        key = (desde, hasta)
        if key in seen:
            raise ValueError(f"Tramo IMRM duplicado: {desde} - {hasta}.")
        seen.add(key)
        try:
            valor = int(float(str(row[2]).strip().replace(".", "").replace(",", ".")))
        except ValueError as exc:
            raise ValueError(f"Valor IMRM invalido para {desde} - {hasta}.") from exc
        valores.append({"Desde": desde, "Hasta": hasta, "IMRM": valor})

    if not valores:
        raise ValueError("Debe existir al menos un tramo IMRM.")

    valores.sort(key=lambda item: datetime.strptime(item["Desde"], "%d/%m/%Y"), reverse=True)
    _write_json_atomic(IMR_JSON_PATH, valores)
    cargar_imr_historico()
    return valores

def obtener_valor_utm(mes, ano, meses_nombres):
    """ Busca el valor de la UTM para un mes y aÃ±o especÃ­ficos. """
    global BD_UTM_VALORES
    try:
        mes_num = meses_nombres.index(mes) + 1
        clave = f"{ano}-{mes_num:02d}"
        return BD_UTM_VALORES.get(clave)
    except ValueError:
        pass
    print(f"âš ï¸ No hay datos de UTM para {mes}-{ano}.")
    return None

def obtener_valor_imr(mes, ano, meses_nombres):
    """ Busca el valor del IMRM para un mes y aÃ±o especÃ­ficos. """
    global BD_IMR_VALORES
    try:
        fecha_busqueda = datetime.strptime(f"01/{meses_nombres.index(mes)+1}/{ano}", "%d/%m/%Y")
        for tramo in BD_IMR_VALORES:
            desde = datetime.strptime(tramo["Desde"], "%d/%m/%Y")
            hasta = datetime.strptime(tramo["Hasta"], "%d/%m/%Y")
            if desde <= fecha_busqueda <= hasta:
                return tramo.get("IMRM")
    except (ValueError, KeyError):
        pass
    print(f"âš ï¸ No hay datos de IMRM para {mes}-{ano}.")
    return None

def obtener_puntos_ipc(mes, ano):
    """ Busca el valor IPC en el diccionario global usando la clave 'YYYY-MM'. """
    global BD_IPC_VALORES
    try:
        mes_num = config.MESES.index(mes.strip().capitalize()) + 1
        clave = f"{ano}-{mes_num:02d}"
        valor = BD_IPC_VALORES.get(clave)
        if valor:
            # print(f"ðŸ“Š IPC Recuperado: {clave} -> {valor}")
            pass
        else:
            print(f"âš ï¸ No hay datos de IPC para {clave} en la base cargada.")
        return valor
    except (ValueError, AttributeError):
        print(f"âš ï¸ Error al buscar IPC para {mes}-{ano}.")
        return None

def calcular_proximo_periodo(mes, ano, meses_a_sumar, lista_meses):
    idx = lista_meses.index(mes)
    total_meses = idx + meses_a_sumar
    nuevo_ano = int(ano) + (total_meses // 12)
    nuevo_mes = lista_meses[total_meses % 12]
    return nuevo_mes, str(nuevo_ano)

def limpiar_monto(texto, admitir_decimales=False):
    if not texto or str(texto).lower() == 'nan': return 0
    
    num_str = str(texto).replace("$", "").replace(" ", "")
    
    if admitir_decimales:
        num_str = num_str.replace(".", "").replace(",", ".")
        try: return float(num_str)
        except ValueError: return 0.0
    else:
        # Para enteros, se elimina todo lo que no sea nÃºmero (y el signo)
        # Se maneja la coma decimal por si el usuario la ingresa
        num_str = num_str.split(',')[0].replace(".", "")
        try: return int(num_str)
        except ValueError: return 0

def formato_moneda(valor, decimales=0):
    try:
        prefijo = "-" if valor < 0 else ""
        valor_abs = abs(valor)
        
        if decimales > 0:
            return f"${prefijo}{valor_abs:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            return f"${prefijo}{int(valor_abs):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "$0"

def buscar_lav_en_df(df):
    """
    Busca el nÃºmero de la Cuenta LAV en el DataFrame.
    Se busca una celda que comience con 'LAV:' y se extrae el nÃºmero que le sigue.
    La bÃºsqueda se limita a las primeras 5 filas para eficiencia.
    """
    if df.empty:
        return "No detectada"

    # Limitar la bÃºsqueda a las primeras 5 filas, ya que la informaciÃ³n de cabecera suele estar ahÃ­.
    rows_to_check = min(len(df), 5)

    for r_idx in range(rows_to_check):
        for c_idx in range(len(df.columns)):
            cell_value = df.iloc[r_idx, c_idx]
            if pd.notna(cell_value):
                cell_str = str(cell_value).strip()
                # Buscar el patrÃ³n 'LAV: NUMERO' donde NUMERO es uno o mÃ¡s dÃ­gitos.
                # El '^' asegura que "LAV:" estÃ© al inicio del contenido de la celda.
                # Se hace insensible a mayÃºsculas/minÃºsculas para "LAV".
                # Se permite cualquier espacio en blanco despuÃ©s de "LAV:" y comillas opcionales.
                match = re.search(r'^LAV:\s*["\']?(\d+)["\']?', cell_str, re.IGNORECASE)
                if match:
                    return match.group(1)
    
    return "No detectada"

def buscar_rut_en_df(df):
    texto_completo = df.to_string()
    p1 = re.search(r'\b\d{1,2}\.\d{3}\.\d{3}-[\dkK]\b', texto_completo)
    if p1: return p1.group(0)
    
    p2 = re.search(r'\b\d{7,8}-[\dkK]\b', texto_completo)
    if p2: return p2.group(0)
    
    p3 = re.search(r'RUT[:\s]+(\d{7,8}[\dkK])', texto_completo, re.IGNORECASE)
    if p3:
        rut_raw = p3.group(1)
        return f"{rut_raw[:-1]}-{rut_raw[-1]}"
    return "No detectado"

def calcular_fin_periodo(mes, ano, meses_a_sumar, lista_meses):
    idx = lista_meses.index(mes)
    total_meses = idx + meses_a_sumar
    nuevo_ano = int(ano) + (total_meses // 12)
    nuevo_mes = lista_meses[total_meses % 12]
    return nuevo_mes, str(nuevo_ano)

def generar_tramos_segun_reajuste(mes_ini, ano_ini, mes_fin, ano_fin, tipo, meses_descuento=0):
    from config import MESES
    
    total_meses_periodo = (int(ano_fin) - int(ano_ini)) * 12 + (MESES.index(mes_fin) - MESES.index(mes_ini)) + 1
    
    paso = 1
    if "Semestral" in tipo: paso = 6
    elif "Anual" in tipo: paso = 12
    
    tramos = []
    mes_actual = mes_ini
    ano_actual = ano_ini
    meses_restantes = total_meses_periodo
    es_primer_tramo = True
    
    while meses_restantes > 0:
        cant = paso
        if es_primer_tramo:
            descuento_efectivo = meses_descuento % paso
            cant = paso - descuento_efectivo
            es_primer_tramo = False
        
        if cant > meses_restantes: cant = meses_restantes
            
        m_fin, a_fin = calcular_fin_periodo(mes_actual, ano_actual, cant - 1, MESES)
        
        tramos.append({
            'inicio_mes': mes_actual, 'inicio_ano': ano_actual,
            'fin_mes': m_fin, 'fin_ano': a_fin,
            'cantidad_meses': cant
        })
        
        meses_restantes -= cant
        
        if meses_restantes > 0:
            mes_actual, ano_actual = calcular_fin_periodo(m_fin, a_fin, 1, MESES)
            
    return tramos

