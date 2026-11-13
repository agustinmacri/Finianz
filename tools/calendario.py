"""Herramientas de calendario para los agentes: feriados, días hábiles y publicaciones.

Leen las bases locales (datos/feriados.db y datos/publicaciones.db). Si están vacías,
las cargan solas: los feriados desde la librería holidays, las publicaciones del INDEC
desde los PDF de calendarios/indec/ y las que siguen una regla de días hábiles (no hace falta internet). Las de EE. UU. (FRED)
se cargan con `python actualizar.py`.
"""
from datetime import date, timedelta

from admin_datos import feriados as db
from admin_datos import publicaciones as db_pub
from carga_datos import catalogo
from carga_datos import feriados as carga_feriados
from carga_datos import publicaciones_indec as carga_indec
from carga_datos import publicaciones_regla as carga_regla

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _preparar():
    """Carga los feriados si la base está vacía o si cambió el año y falta el año próximo."""
    rango = db.rango_cargado()
    if not rango or rango[1] < date.today().year + 1:
        carga_feriados.cargar()


def _fecha(texto: str | None, por_defecto: date) -> date:
    if not texto:
        return por_defecto
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise ValueError(f"La fecha '{texto}' no tiene formato AAAA-MM-DD.") from None


def _con_dia(d: date) -> str:
    return f"{d.isoformat()} ({DIAS_SEMANA[d.weekday()]})"


# ---------------------------------------------------------------------------
# 1. Feriados entre dos fechas
# ---------------------------------------------------------------------------
def consultar_feriados(desde: str | None = None, hasta: str | None = None, calendario: str = "todos") -> str:
    try:
        _preparar()
        inicio = _fecha(desde, date.today())
        fin = _fecha(hasta, inicio + timedelta(days=60))
        calendarios = None if calendario == "todos" else [db.MERCADOS.get(calendario, calendario)]
        filas = db.feriados_entre(inicio, fin, calendarios)
    except (ValueError, db.FueraDeRango) as e:
        return f"Error: {e}"
    if not filas:
        return f"No hay feriados entre {inicio} y {fin} en el calendario '{calendario}'."

    # Un renglón por fecha y nombre, con los calendarios que lo tienen (ej.: Argentina, Bancos AR, BYMA)
    agrupado: dict[tuple, list[str]] = {}
    for f in filas:
        marca = "*" if f["fuente"] == "aproximado" else ""
        agrupado.setdefault((f["fecha"], f["nombre"]), []).append(db.NOMBRES_CALENDARIO[f["calendario"]] + marca)
    lineas = [f"- {_con_dia(date.fromisoformat(fecha))} | {nombre} | {', '.join(cals)}"
              for (fecha, nombre), cals in agrupado.items()]
    texto = f"Feriados entre {inicio} y {fin} (fecha | motivo | calendarios donde aplica):\n" + "\n".join(lineas)
    if any(f["fuente"] == "aproximado" for f in filas):
        texto += ("\n* BYMA aproximado con el calendario nacional (no hay calendario bursátil exacto antes de 2026): "
                  "puede diferir en días puntuales.")
    return texto


CONSULTAR_FERIADOS = {
    "name": "consultar_feriados",
    "description": (
        "Lista los feriados entre dos fechas, de Argentina y de Estados Unidos, indicando en qué "
        "calendarios aplica cada uno: Argentina (nacional), Bancos AR, BYMA (mercado local), "
        "EE. UU. (federal), NYSE (bolsa) y Bonos EE. UU. (Treasuries). "
        "Sin fechas, muestra los próximos 60 días. Hay datos desde 2016 hasta 20 años adelante."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (por defecto, hoy)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (por defecto, 60 días después de 'desde')"},
            "calendario": {
                "type": "string",
                "enum": ["todos", *db.MERCADOS],
                "description": "Filtrar por un calendario (por defecto, todos)",
            },
        },
    },
}


# ---------------------------------------------------------------------------
# 2. Días hábiles
# ---------------------------------------------------------------------------
def calcular_dia_habil(fecha: str | None = None, mercado: str = "BYMA", sumar_dias: int = 0) -> str:
    try:
        _preparar()
        d = _fecha(fecha, date.today())
        habil = db.es_dia_habil(d, mercado)
        lineas = [f"{_con_dia(d)} {'ES' if habil else 'NO es'} día hábil para {mercado}."]
        if not habil:
            motivo = db.feriados_entre(d, d, [db.MERCADOS[mercado]])
            aproximado = " (calendario bursátil aproximado con el nacional)" if motivo and motivo[0]["fuente"] == "aproximado" else ""
            lineas.append(f"Motivo: {motivo[0]['nombre'] if motivo else 'fin de semana'}{aproximado}.")
            lineas.append(f"Próximo día hábil: {_con_dia(db.proximo_dia_habil(d, mercado))}.")
        if int(sumar_dias):
            resultado = db.sumar_dias_habiles(d, int(sumar_dias), mercado)
            lineas.append(f"{_con_dia(d)} {int(sumar_dias):+d} días hábiles ({mercado}) = {_con_dia(resultado)}.")
    except (ValueError, KeyError, db.FueraDeRango) as e:
        return f"Error: {e}"
    return "\n".join(lineas)


CALCULAR_DIA_HABIL = {
    "name": "calcular_dia_habil",
    "description": (
        "Indica si una fecha es día hábil para un mercado y, si no lo es, el motivo y el próximo día hábil. "
        "Con sumar_dias suma o resta días hábiles (ej.: liquidación T+2 desde una fecha de operación). "
        "Mercados: BYMA (por defecto), BANCOS, AR, NYSE, US_BONOS, US."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fecha": {"type": "string", "description": "Fecha AAAA-MM-DD (por defecto, hoy)"},
            "mercado": {"type": "string", "enum": list(db.MERCADOS), "description": "Mercado (por defecto, BYMA)"},
            "sumar_dias": {"type": "integer", "description": "Días hábiles a sumar (negativo para restar). Por defecto 0"},
        },
    },
}


# ---------------------------------------------------------------------------
# 3. Calendario de publicaciones
# ---------------------------------------------------------------------------
# Si el catálogo tiene un error, solo falla esta herramienta (con el mensaje), no todo el sistema
try:
    CATALOGO = {p["codigo"]: p for p in catalogo.leer()}
    ERROR_CATALOGO = None
except catalogo.ErrorCatalogo as e:
    CATALOGO, ERROR_CATALOGO = {}, str(e)


def consultar_publicaciones(desde: str | None = None, hasta: str | None = None, pais: str = "todos",
                            importancia: str = "media", buscar: str | None = None) -> str:
    if ERROR_CATALOGO:
        return f"Error en el catálogo de publicaciones: {ERROR_CATALOGO}"
    try:
        if not db_pub.hay_datos(carga_indec.FUENTE):
            carga_indec.cargar()
        if not db_pub.hay_datos(carga_regla.FUENTE):
            _preparar()                       # las reglas cuentan días hábiles: necesitan los feriados
            carga_regla.cargar()
        inicio = _fecha(desde, date.today())
        # Si se busca una publicación puntual ("¿cuándo sale el IPC?"), se mira medio año hacia adelante
        fin = _fecha(hasta, inicio + timedelta(days=180 if buscar else 14))
        filas = db_pub.entre(inicio, fin, None if pais == "todos" else pais, importancia, buscar)
    except (ValueError, KeyError) as e:
        return f"Error: {e}"

    if buscar and filas:
        filas = [f for f in filas if f["codigo"] == filas[0]["codigo"] or not f["codigo"]][:3]
    lineas = []
    for f in filas:
        nombre = CATALOGO[f["codigo"]]["nombre"] if f["codigo"] in CATALOGO else f["titulo"]
        periodo = f": {f['periodo']}" if f["periodo"] and f["codigo"] else ""
        hora = f" {f['hora']}" if f["hora"] else ""
        lineas.append(f"- {_con_dia(date.fromisoformat(f['fecha']))}{hora} | {f['pais']} | {f['organismo']} | "
                      f"{nombre}{periodo} [{f['importancia']}]")

    encabezado = f"Publicaciones entre {inicio} y {fin}" + (f" que coinciden con '{buscar}'" if buscar else "") + ":"
    texto = encabezado + "\n" + ("\n".join(lineas) if lineas else "(ninguna)")
    return texto + _avisos_cobertura(inicio, fin, pais, buscar)


def _avisos_cobertura(inicio: date, fin: date, pais: str, buscar: str | None) -> str:
    """Aclara qué fechas todavía no están cargadas, para no confundir 'no hay datos' con 'no hay publicación'."""
    avisos = []
    cargados = db_pub.codigos_con_fechas(inicio)
    pendientes = [c for c, p in CATALOGO.items()
                  if c not in cargados and (pais == "todos" or p["pais"] == pais)]
    if buscar:
        codigo = buscar.strip().upper().replace(" ", "_")
        if codigo in pendientes:
            avisos.append(f"Todavía NO hay fechas cargadas de {CATALOGO[codigo]['nombre']}: "
                          "que no aparezca no significa que no se publique.")
    elif pendientes:
        avisos.append(f"Todavía NO hay fechas cargadas de {len(pendientes)} publicaciones del catálogo "
                      f"({', '.join(pendientes)}): que no aparezcan no significa que no se publiquen.")
    rango = db_pub.rango_cargado("AR")
    if rango and fin.isoformat() > rango[1] and pais in ("todos", "AR"):
        avisos.append(f"El calendario del INDEC cargado llega hasta el {rango[1]}.")
    rango = db_pub.rango_cargado("US")
    if rango and fin.isoformat() > rango[1] and pais in ("todos", "US"):
        avisos.append(f"Las fechas de EE. UU. cargadas llegan hasta el {rango[1]}.")
    return ("\n\nAclaración: " + " ".join(avisos)) if avisos else ""


CONSULTAR_PUBLICACIONES = {
    "name": "consultar_publicaciones",
    "description": (
        "Calendario de publicaciones económicas oficiales: qué datos salen y cuándo. "
        "Sin parámetros, muestra las de importancia alta y media de los próximos 14 días. "
        "Las horas 'ET' son del este de EE. UU. "
        "Para saber cuándo sale un dato puntual, usá 'buscar' con su código: "
        + (", ".join(f"{c} ({p['nombre']})" for c, p in CATALOGO.items()) or "ver calendarios/publicaciones.toml") +
        ". También acepta palabras del título (ej.: 'construcción', 'supermercados')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (por defecto, hoy)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (por defecto, 14 días después; 180 si se usa 'buscar')"},
            "pais": {"type": "string", "enum": ["todos", "AR", "US"], "description": "Filtrar por país (por defecto, todos)"},
            "importancia": {"type": "string", "enum": ["alta", "media", "baja"],
                            "description": "Nivel mínimo: alta, media (alta y media, por defecto) o baja (todas)"},
            "buscar": {"type": "string", "description": "Código del catálogo (ej.: IPC) o palabras del título"},
        },
    },
}


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
HERRAMIENTAS = [
    (CONSULTAR_FERIADOS, consultar_feriados),
    (CALCULAR_DIA_HABIL, calcular_dia_habil),
    (CONSULTAR_PUBLICACIONES, consultar_publicaciones),
]
