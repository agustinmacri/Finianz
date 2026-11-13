"""Carga de series diarias oficiales en datos/series.db: el CER, la TAMAR y el A3500 del BCRA.

Cómo funciona:
- Se piden solo fechas dentro del rango que el BCRA informa para cada variable (primera y última
  fecha de su listado oficial): si se le pide un período sin datos, responde con error 400.
- La primera vez se baja toda la historia de la serie, de a un año por consulta porque el BCRA
  limita la cantidad de datos que devuelve cada vez.
- Después, solo se piden los días posteriores al último guardado, hasta la última fecha publicada
  (el CER se publica por adelantado, hasta el día 6 del mes siguiente).
- `python actualizar.py` la mantiene al día; las calculadoras también la actualizan solas si
  les falta una fecha.
La base se puede regenerar en cualquier momento desde el BCRA.
"""
from datetime import date, timedelta

from admin_datos import series as db
from conexiones import bcra
from conexiones.http import ErrorAPI

FUENTE = "bcra"
SERIES = {                      # nombre en la base -> id de la variable en el BCRA
    "CER": bcra.ID_CER,         # índice, todos los días
    "TAMAR": bcra.ID_TAMAR,     # % TNA tal como se publica (24.4375 = 24,4375%), días hábiles
    "A3500": bcra.ID_A3500,     # $ por US$, días hábiles (se publica alrededor de las 15 h)
}
DIAS_ADELANTE = 60              # tope por las dudas: nunca se piden fechas más allá de hoy + 60 días


def actualizar(variable: str = "CER") -> int:
    """Trae los días que faltan de una serie (toda la historia si está vacía). Devuelve cuántos guardó."""
    if variable not in SERIES:
        raise ValueError(f"Serie '{variable}' desconocida. Opciones: {', '.join(SERIES)}.")
    id_bcra = SERIES[variable]
    primera, ultima = _rango_publicado(id_bcra)
    rango = db.rango(variable)
    desde = date.fromisoformat(rango[1]) + timedelta(days=1) if rango else primera
    hasta = min(ultima, date.today() + timedelta(days=DIAS_ADELANTE))
    filas = []
    while desde <= hasta:                       # si ya está al día, desde > hasta y no se pide nada
        fin = min(desde + timedelta(days=364), hasta)
        try:
            filas += bcra.obtener_serie(id_bcra, desde.isoformat(), fin.isoformat())
        except ErrorAPI as e:
            if "no devolvió datos" not in str(e):   # un tramo sin datos no es error
                raise
        desde = fin + timedelta(days=1)
    return db.guardar(variable, filas, FUENTE) if filas else 0


def _rango_publicado(id_bcra: int) -> tuple[date, date]:
    """Primera y última fecha que el BCRA informa para la variable, según su listado oficial."""
    for v in bcra.listar_variables():
        if v["id"] == id_bcra:
            if not v.get("primera_fecha") or not v.get("ultima_fecha"):
                raise ErrorAPI(f"El BCRA no informa el rango de fechas de la variable {id_bcra}.")
            return date.fromisoformat(v["primera_fecha"][:10]), date.fromisoformat(v["ultima_fecha"][:10])
    raise ErrorAPI(f"La variable {id_bcra} no figura en el listado del BCRA.")


def actualizar_todas() -> dict:
    """Actualiza todas las series. Devuelve {serie: valores nuevos o mensaje de error}."""
    resultado = {}
    for variable in SERIES:
        try:
            resultado[variable] = actualizar(variable)
        except Exception as e:                      # una serie con problemas no frena a las demás
            resultado[variable] = f"error: {e}"
    return resultado
