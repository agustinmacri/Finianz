"""Carga de series diarias oficiales en datos/series.db: el CER y la TAMAR del BCRA.

Cómo funciona:
- La primera vez se baja toda la historia de la serie (el CER desde el 2/2/2002; la TAMAR desde donde
  la tenga el BCRA: los años sin datos se saltean), de a un año
  por consulta porque el BCRA limita la cantidad de datos que devuelve cada vez.
- Después, solo se piden los días posteriores al último guardado. El CER se publica por
  adelantado (hasta el día 6 del mes siguiente), así que se pide hasta DIAS_ADELANTE días después de hoy.
- `python actualizar.py` la mantiene al día; las calculadoras también la actualizan solas si
  les falta una fecha.
La base se puede regenerar en cualquier momento desde el BCRA.
"""
from datetime import date, timedelta

from admin_datos import series as db
from conexiones import bcra
from conexiones.http import ErrorAPI

FUENTE = "bcra"
SERIES = {                      # nombre en la base -> (id de la variable en el BCRA, primera fecha)
    "CER": (bcra.ID_CER, date(2002, 2, 2)),         # índice, todos los días
    "TAMAR": (bcra.ID_TAMAR, date(2010, 1, 1)),     # % TNA tal como se publica (24.4375 = 24,4375%), días hábiles
}
DIAS_ADELANTE = 60


def actualizar(variable: str = "CER") -> int:
    """Trae los días que faltan de una serie (toda la historia si está vacía). Devuelve cuántos guardó."""
    if variable not in SERIES:
        raise ValueError(f"Serie '{variable}' desconocida. Opciones: {', '.join(SERIES)}.")
    id_bcra, inicio = SERIES[variable]
    rango = db.rango(variable)
    desde = date.fromisoformat(rango[1]) + timedelta(days=1) if rango else inicio
    hasta = date.today() + timedelta(days=DIAS_ADELANTE)
    filas = []
    while desde <= hasta:
        fin = min(desde + timedelta(days=364), hasta)
        try:
            filas += bcra.obtener_serie(id_bcra, desde.isoformat(), fin.isoformat())
        except ErrorAPI as e:
            if "no devolvió datos" not in str(e):   # un tramo sin datos (ej.: fechas aún no publicadas) no es error
                raise
        desde = fin + timedelta(days=1)
    return db.guardar(variable, filas, FUENTE) if filas else 0


def actualizar_todas() -> dict:
    """Actualiza todas las series. Devuelve {serie: valores nuevos o mensaje de error}."""
    resultado = {}
    for variable in SERIES:
        try:
            resultado[variable] = actualizar(variable)
        except Exception as e:                      # una serie con problemas no frena a las demás
            resultado[variable] = f"error: {e}"
    return resultado
