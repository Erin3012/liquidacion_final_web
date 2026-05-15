from fpdf import FPDF
from datetime import datetime
from config import COLOR_PJUD
from pypdf import PdfWriter, PdfReader # Importar pypdf
import utils
from utils import formato_moneda
import os
class PDF(FPDF):
    def __init__(self, iniciales="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.iniciales = iniciales # Guardamos las iniciales para usarlas en el footer

    def header(self):
        ruta_logo = utils.obtener_ruta_recurso("pj.png")
        if os.path.exists(ruta_logo):
            self.image(ruta_logo, 150, 10, 45)
        self.ln(30) 

    def footer(self):
        # Nos posicionamos a 1.5 cm del final de la p?gina
        self.set_y(-15)
        
        # 1. QUITAR CURSIVA: Cambiamos la 'I' (Italic) por unas comillas vac?as '' (Normal)
        self.set_font('Arial', 'B', 10)
        
        #if self.iniciales:
            # 2. AGREGAR COLOR MARR?N: Usamos RGB (Red, Green, Blue)
            # El c?digo 139, 69, 19 corresponde a un tono marr?n cl?sico (SaddleBrown)
        self.set_text_color(0, 0, 0)

            # Imprimimos la palabra fija y las iniciales
        self.cell(0, 15, f"{self.iniciales}  ", 0, 0, 'L')

            # BUENA PR?CTICA: Restaurar el color del texto a negro (0, 0, 0) 
            # para que no afecte a otras p?ginas u otros elementos por accidente
        self.set_text_color(0, 0, 0)


    

    

def fecha_en_palabras(fecha=None):
    if fecha is None:
        fecha = datetime.now()
    
    dias = {
        1: "uno", 2: "dos", 3: "tres", 4: "cuatro", 5: "cinco", 6: "seis", 7: "siete", 
        8: "ocho", 9: "nueve", 10: "diez", 11: "once", 12: "doce", 13: "trece", 
        14: "catorce", 15: "quince", 16: "dieciséis", 17: "diecisiete", 18: "dieciocho", 
        19: "diecinueve", 20: "veinte", 21: "veintiuno", 22: "veintidós", 23: "veintitrés", 
        24: "veinticuatro", 25: "veinticinco", 26: "veintiséis", 27: "veintisiete", 
        28: "veintiocho", 29: "veintinueve", 30: "treinta", 31: "treinta y uno"
    }
    meses = {
        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
    }
    
    dia_letras = dias[fecha.day].capitalize()
    mes_letras = meses[fecha.month]
    anios = {2024: "dos mil veinticuatro", 2025: "dos mil veinticinco", 2026: "dos mil veintiséis"}
    anio_letras = anios.get(fecha.year, str(fecha.year))
    
    return f"{dia_letras} de {mes_letras} de {anio_letras}"

def generar_pdf(datos_causa, items_tabla, resumen, ciudad, reajuste_tipo, cartolas_data=[], referencia_deuda_anterior="", observaciones_finales="", external_pdf_path=None, cese_alimentos=False, output_dir=None):
    
    # 1. Buscamos las iniciales dentro de la lista de datos
    iniciales_para_footer = ""
    for etiqueta, valor in datos_causa:
        if str(etiqueta).lower() == "iniciales": 
            iniciales_para_footer = str(valor).strip()
            break
            
    # --- EXTRACCI?N DE VARIABLES ---
    rit_causa = datos_causa[1][1] if len(datos_causa) > 1 else "N/A"
    numero_lav = "N/A"
    periodo_cartola_principal = "No detectado"
    
    for label, value in datos_causa:
        if label == "Cuenta N° LAV":
            numero_lav = value
        if label == "Periodo Cartola":
            periodo_cartola_principal = value
    nombre_tribunal = f"{datos_causa[0][1]}" 

    # 2. CREAR EL OBJETO PDF UNA SOLA VEZ CON LAS INICIALES
    pdf = PDF(iniciales=iniciales_para_footer) 
    pdf.set_auto_page_break(auto=True, margin=33)
    pdf.add_page()
    
    # --- P?GINA 1: LIQUIDACI?N ---
    pdf.set_font("Arial", '', 9)
    texto_fecha = f"{nombre_tribunal}, {fecha_en_palabras()}."
    pdf.cell(0, 5, texto_fecha, ln=True, align='L') 
    
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "LIQUIDACIÓN", ln=True, align='C')
    pdf.ln(2)
    
    # --- TABLA IDENTIFICACI?N (AQU? APLICAMOS EL FILTRO REAL) ---
    pdf.set_fill_color(*COLOR_PJUD)
    for label, value in datos_causa:
        
        # --- FILTRO CLAVE: SALTAR INICIALES ---
        if str(label).lower() == "iniciales":
            continue
        # --------------------------------------
        
        display_value = str(value)
        # Aplicar formato de moneda si la etiqueta es "Pensi?n Final Arrastre"
        if label == "Pensión Final Arrastre":
            numeric_value = utils.limpiar_monto(value)
            display_value = utils.formato_moneda(numeric_value)
        
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(65, 6, f" {label}", border=1, fill=True)
        pdf.set_font("Arial", '', 8) # Reset font to normal for the value
        pdf.cell(125, 6, f" {display_value}", border=1, ln=True)
    
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(65, 6, " Tipo de Reajustabilidad", border=1, fill=True)
    pdf.set_font("Arial", 'I', 8)
    pdf.cell(125, 6, f" {reajuste_tipo}", border=1, ln=True)
    pdf.ln(5)

    # --- TABLA PRINCIPAL DE C?LCULOS ---
    if reajuste_tipo == "UTM":
        w = [32, 32, 13, 30, 40, 43]
        headers = ["Desde", "Hasta", "Meses", "Monto UTM", "Valor UTM", "Total Pesos"]
    else:
        w = [32, 32, 13, 23, 40, 50]
        headers = ["Desde", "Hasta", "Meses", "Reajuste", "Pensión reajustada", "Total"]

    if not cese_alimentos:
        pdf.set_font("Arial", 'B', 10)
        pdf.set_fill_color(*COLOR_PJUD)
        for i, h in enumerate(headers):
            pdf.cell(w[i], 7, h, border=1, fill=True, align='LEFT')
        pdf.ln()

        pdf.set_font("Arial", '', 8)
        for row in items_tabla:
            # --- AGREGAR ESTA VALIDACI?N ---
            if str(row[0]) == "TOTALES":
                continue # Salta esta fila y no la dibuja
            # -------------------------------
            
            for i in range(6):
                align = 'C' if i < 3 else 'R'
                pdf.cell(w[i], 6, str(row[i]), border=1, align='LEFT')
            pdf.ln()

    # --- SECCI?N TOTALES ---
    ancho_lbl = sum(w[:5]) 
    pdf.set_font("Arial", 'B', 10)

    # 1. Subtotal Periodo Actual
    if not cese_alimentos:
        pdf.cell(ancho_lbl, 7, " Subtotal devengado periodo actual", border=1)
        pdf.cell(w[5], 7, utils.formato_moneda(resumen['cargo_actual']), border=1, ln=True, align='L')
    
    # 2. Deuda de Arrastre
    if resumen['deuda_anterior'] != 0:
        text_label = "Monto liquidación anterior"
        if referencia_deuda_anterior:
            text_label += f" {referencia_deuda_anterior}"
        pdf.cell(ancho_lbl, 7, text_label, border=1)
        pdf.cell(w[5], 7, utils.formato_moneda(resumen['deuda_anterior']), border=1, ln=True, align='L')


    if 'ajustes_manuales' in resumen:
        # --- BLOQUE 1: CARGOS (Aumentan la deuda) ---
        for ajuste in resumen['ajustes_manuales']:
            if ajuste['tipo'] == "Cargo":
                texto = f"(+) {ajuste['desc']} ({ajuste['fecha']})"
                pdf.set_font("Arial", '', 8)
                
                # Dividir el texto en m?ltiples l?neas si es muy largo
                words = texto.split()
                lines = []
                current_line = ""
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if pdf.get_string_width(" " + test_line) < ancho_lbl - 2:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = word
                if current_line: lines.append(current_line)
                
                line_h = 7 if len(lines) == 1 else 5
                total_h = line_h * len(lines)
                
                if pdf.get_y() + total_h > 260:
                    pdf.add_page()
                
                x, y = pdf.get_x(), pdf.get_y()
                
                # Dibujar bordes
                pdf.rect(x, y, ancho_lbl, total_h)
                pdf.rect(x + ancho_lbl, y, w[5], total_h)
                
                # Dibujar texto
                pdf.set_xy(x, y)
                for line in lines:
                    pdf.cell(ancho_lbl, line_h, " " + line, border=0, ln=2)
                
                # Dibujar monto y pasar a la siguiente fila
                pdf.set_xy(x + ancho_lbl, y)
                pdf.cell(w[5], total_h, formato_moneda(ajuste['monto']), border=0, ln=1, align='L')

   

    # 3. Subtotal General
    pdf.set_fill_color(*COLOR_PJUD)

    # --- Agrega esta l?nea para cambiar el tama?o (B = Negrita, 12 = Tama?o) ---
    pdf.set_font("Arial", 'B', 12) 

    # Ajustamos la altura de la celda de 7 a 9 para que el texto de 12 puntos no quede apretado
    if not cese_alimentos:
        pdf.cell(ancho_lbl, 7, " Subtotal pensiones devengadas", border=1, fill=True)
        pdf.cell(w[5], 7, utils.formato_moneda(resumen['subtotal_general']), border=1, fill=True, ln=True, align='L')

    # --- IMPORTANTE: Si quieres que el resto del PDF vuelva a letra chica, 
    # debes resetearla despu?s de estas l?neas: ---
    pdf.set_font("Arial", '', 8)
    
    # 4. Abonos Cartola (CORREGIDO: Ahora numero_lav es datos_causa[2][1])
    # MODIFICADO PARA M?LTIPLES CARTOLAS
    pdf.set_font("Arial", 'B', 10)
    if cartolas_data:
        for i, cartola in enumerate(cartolas_data):
            lav_num = cartola.get('lav_number', "N/A")
            period = cartola.get('period', "No detectado")
            abonos = cartola.get('total_abonos', 0)
            
            texto_abonos = f" (-) LAV N° {lav_num}"
            if period and period != "No detectado":
                texto_abonos += f" ({period})"
            pdf.cell(ancho_lbl, 7, texto_abonos, border=1)
            pdf.cell(w[5], 7, formato_moneda(abonos), border=1, ln=True, align='L')
    else:
        pdf.cell(ancho_lbl, 7, " (-) Abonos Cartola", border=1)
        pdf.cell(w[5], 7, formato_moneda(0), border=1, ln=True, align='L')

    # 5. AJUSTES MANUALES
    if 'ajustes_manuales' in resumen:
    

        # --- BLOQUE 2: ABONOS MANUALES (Disminuyen la deuda) ---
        for ajuste in resumen['ajustes_manuales']:
            if ajuste['tipo'] == "Abono":
                texto = f"(-) {ajuste['desc']} ({ajuste['fecha']})"
                pdf.set_font("Arial", '', 8)
                
                # Dividir el texto en m?ltiples l?neas si es muy largo
                words = texto.split()
                lines = []
                current_line = ""
                for word in words:
                    test_line = current_line + " " + word if current_line else word
                    if pdf.get_string_width(" " + test_line) < ancho_lbl - 2:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = word
                if current_line: lines.append(current_line)
                
                line_h = 7 if len(lines) == 1 else 5
                total_h = line_h * len(lines)
                
                if pdf.get_y() + total_h > 260:
                    pdf.add_page()
                
                x, y = pdf.get_x(), pdf.get_y()
                
                # Dibujar bordes
                pdf.rect(x, y, ancho_lbl, total_h)
                pdf.rect(x + ancho_lbl, y, w[5], total_h)
                
                # Dibujar texto
                pdf.set_xy(x, y)
                for line in lines:
                    pdf.cell(ancho_lbl, line_h, " " + line, border=0, ln=2)
                
                # Dibujar monto y pasar a la siguiente fila
                pdf.set_xy(x + ancho_lbl, y)
                # Mostramos el monto con formato, pero se entiende que resta por el prefijo (-)
                pdf.cell(w[5], total_h, formato_moneda(ajuste['monto']), border=0, ln=1, align='L')

    # 6. Resultado Final
    final = resumen['total_final']
    texto_final = " TOTAL SALDO A FAVOR" if final < 0 else " TOTAL LIQUIDACIÓN DE DEUDA"
    
    pdf.set_font("Arial", 'B', 12)
    pdf.set_fill_color(*COLOR_PJUD) 
    pdf.cell(ancho_lbl, 7, texto_final, border=1, fill=True)
    pdf.cell(w[5], 7, formato_moneda(final), border=1, fill=True, ln=True, align='L')

    # --- NUEVO: Observaciones Adicionales ---
    if observaciones_finales:
        pdf.ln(10) # A?adir un poco de espacio
        pdf.set_font("Arial", 'B', 10)
        pdf.cell(0, 7, "Observaciones:", ln=True)
        pdf.set_font("Arial", '', 8)
        pdf.multi_cell(0, 5, observaciones_finales)

    # --- P?GINA 2: DETALLE DE CARTOLA ---
    # MODIFICADO PARA M?LTIPLES CARTOLAS
    if cartolas_data:
        for i, cartola in enumerate(cartolas_data):
            pdf.add_page()
            pdf.set_font("Arial", 'B', 12)
            if len(cartolas_data) == 1:
                pdf.cell(0, 10, "Informe de búsqueda de pensiones", ln=True, align='L')
            else:
                pdf.cell(0, 10, f"Informe de búsqueda de pensiones - Cartola {i+1}", ln=True, align='L')
            pdf.ln(2)
            
            pdf.set_fill_color(*COLOR_PJUD)
            pdf.set_font("Arial", 'B', 10)
            
            # Use data from the current cartola
            current_rut_dte = cartola.get('rut_dte', "No detectado")
            current_lav_num = cartola.get('lav_number', "N/A")
            current_movimientos = cartola.get('movimientos', [])

            rows_cartola = [("RUT Titular", current_rut_dte), ("Tribunal", nombre_tribunal), ("Cuenta LAV", current_lav_num)]
            for label, val in rows_cartola:
                pdf.set_font("Arial", 'B', 10); pdf.cell(40, 6, label, border=1, fill=True)
                pdf.set_font("Arial", '', 8); pdf.cell(150, 6, f" {val}", border=1, ln=True)
            
            pdf.ln(5)
            
            pdf.set_font("Arial", 'B', 10); pdf.set_fill_color(*COLOR_PJUD)
            col_w_mov = [40, 100, 50]
            pdf.cell(col_w_mov[0], 7, "Fecha Mvto.", border=1, fill=True, align='L')
            pdf.cell(col_w_mov[1], 7, "Movimiento", border=1, fill=True, align='L')
            pdf.cell(col_w_mov[2], 7, "Monto", border=1, fill=True, align='L')
            pdf.ln()
            
            pdf.set_font("Arial", '', 8)
            if not current_movimientos:
                pdf.cell(sum(col_w_mov), 6, "No se encontraron movimientos para esta cartola.", border=1, ln=True)
            else:
                for mov in current_movimientos:
                    if pdf.get_y() > 270: pdf.add_page() 
                    pdf.cell(col_w_mov[0], 6, str(mov[0]), border=1)
                    pdf.cell(col_w_mov[1], 6, str(mov[1])[:60], border=1)
                    pdf.cell(col_w_mov[2], 6, formato_moneda(mov[2]), border=1)
                    pdf.ln()

    # Define the base output filename
    rit_limpio = rit_causa.replace("/", "-").replace(" ", "")
    base_nombre = f"Liquidacion_{rit_limpio}.pdf"
    output_base_dir = output_dir or os.getcwd()
    os.makedirs(output_base_dir, exist_ok=True)
    final_output_path = os.path.join(output_base_dir, base_nombre)

    # --- Anexar PDF externo si se proporciona ---
    if external_pdf_path and os.path.exists(external_pdf_path):
        # Save the fpdf2 content to a temporary file first
        temp_fpdf_path = os.path.join(output_base_dir, f"temp_liquidacion_{rit_limpio}.pdf")
        pdf.output(temp_fpdf_path)

        try:
            # Merge with pypdf
            writer = PdfWriter()

            # Add pages from the fpdf2-generated PDF
            reader_fpdf = PdfReader(temp_fpdf_path)
            for page in reader_fpdf.pages:
                writer.add_page(page)

            # Add pages from the external PDF
            reader_external = PdfReader(external_pdf_path)
            for page in reader_external.pages:
                writer.add_page(page)

            # Write the merged PDF to the final output path
            with open(final_output_path, "wb") as output_pdf:
                writer.write(output_pdf)

            print(f"PDF generado y anexado en: {final_output_path}")

        except Exception as e:
            print(f"ERROR: No se pudo anexar el PDF externo con pypdf: {e}")
            # Fallback: If merging fails, save only the fpdf2 content
            pdf.output(final_output_path)
            print(f"Se gener? solo el PDF de liquidaci?n debido a un error al anexar el PDF externo.")

        finally:
            # Clean up the temporary fpdf2 file
            if os.path.exists(temp_fpdf_path):
                os.remove(temp_fpdf_path)
    else:
        # If no external PDF, just save the fpdf2 content directly
        pdf.output(final_output_path)

    return final_output_path

