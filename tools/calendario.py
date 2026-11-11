"""Herramientas de calendario para los agentes: feriados y días hábiles.

Leen la base local (datos/feriados.db). Si la base está vacía o no cubre el año próximo,
la recargan solas desde la librería holidays (no hace falta internet).
"""
from datetime import date, timedelta

from ingesta import feriados as ingesta_feriados
from storage import feriados as db

DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def _preparar():
    """Carga los feriados si la base está vacía o si cambió el año y falta el año próximo."""
    rango = db.rango_cargado()
    if not rango or rango[1] < date.today().year + 1:
        ingesta_feriados.cargar()


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
        "Sin fechas, muestra los próximos 60 días. Hay datos desde 2016 hasta el año próximo."
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
# Registro
# ---------------------------------------------------------------------------
HERRAMIENTAS = [
    (CONSULTAR_FERIADOS, consultar_feriados),
    (CALCULAR_DIA_HABIL, calcular_dia_habil),
]
