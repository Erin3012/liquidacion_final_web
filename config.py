# config.py

# Colores y Estilo
COLOR_PJUD = (209, 195, 150)  # Beige Institucional

# Listados para Interfaz
TRIBUNALES = [
    "Juzgado de Familia Concepción",
    "Juzgado de Familia Talcahuano",
    "Juzgado de Familia Coronel",
    "Juzgado de Familia Lota",
    "Juzgado de Familia Tomé",
    "Juzgado de Familia Yumbel",
    "Juzgado de Familia Los Angeles",
    "Jgdo. L. de Arauco",
    "Jgdo. Letras de Cañete",
    "Jgdo. L. y G. de Lebu",
    "Jgdo. L. y G. de Curanilahue",
    "Jgdo. L. y G. de Florida",
    "Jgdo. L. y G. de Cabrero",
    "Jgdo. L. y G. de Laja",
    "Jgdo. L. y G. de Mulchen",
    "Jgdo. L. y G. de Santa Barbara",
    "Jgdo. L. y G. de Santa Juana",
    "Jgdo. L. y G. de Nacimiento"
]

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", 
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

ANOS = [str(a) for a in range(1979, 2027)]

REAJUSTES = ["IPC (Mensual)", "IPC (Semestral)", "IPC (Anual)", "IMRM", "EMOLUMENTOS"] #, "UTM"

# Patrón de limpieza para win32com
BASURA_PJUD = [
    "Personal", "Cédula", "Carta", "eMail", "Telefono", "Fax", 
    "Art. 23", "Art. 44", "Carabineros", "Investigaciones", 
    "Receptor", "Particular", "Tribunal", "Centro de Notificaciones",
    "[SIS]", "@", "Seleccionar"
]
