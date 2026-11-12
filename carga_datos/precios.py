"""Carga de precios diarios en datos/precios.db, desde PPI.

Cómo funciona:
- La primera vez que se consulta un activo, se registra como "seguido" y se baja todo
  el histórico que tenga la fuente (desde PRECIOS_DESDE).
- Después, solo se piden los días que faltan (desde el último guardado hasta ayer).
- `python actualizar.py` trae los cierres nuevos de todos los activos seguidos.

Solo se guardan cierres de días terminados: el precio de hoy se guarda recién después del
cierre del mercado (HORA_CIERRE), porque antes es un precio parcial.
"""
from datetime import date, datetime, timedelta

import config
from admin_datos import precios as db
from conexiones import ppi

FUENTE = "ppi"
PRECIOS_DESDE = "2000-01-01"   # se pide desde acá; la fuente devuelve desde donde tenga
HORA_CIERRE = 18               # a partir de esta hora (local) el cierre del día se considera definitivo


def registrar(ticker: str) -> dict:
    """Busca el activo en la fuente y lo agrega a los seguidos (si ya estaba, devuelve sus datos)."""
    existente = db.instrumento(ticker)
    if existente:
        return existente
    encontrados = ppi.buscar_instrumento(ticker)
    exactos = [i for i in encontrados if str(i.get("ticker", "")).upper() == ticker.upper()]
    if not exactos:
        raise ValueError(f"PPI no encontró el ticker '{ticker}'.")
    i = next((x for x in exactos if str(x.get("market", "")).upper() == "BYMA"), exactos[0])
    db.registrar({"ticker": i["ticker"], "tipo": i["type"], "moneda": i.get("currency"),
                  "descripcion": i.get("description"), "isin": i.get("isin"), "mercado": i.get("market")}, FUENTE)
    return db.instrumento(ticker)


def ultimo_dia_cerrado(ahora: datetime | None = None) -> date:
    """Hoy si el mercado ya cerró; si no, ayer."""
    ahora = ahora or datetime.now()
    return ahora.date() if ahora.hour >= HORA_CIERRE else ahora.date() - timedelta(days=1)


def actualizar(ticker: str, plazo: str | None = None) -> int:
    """Trae los días que faltan de un activo (todo el histórico si es nuevo). Devuelve cuántos guardó."""
    plazo = plazo or config.PPI_PLAZO
    datos = registrar(ticker)
    hasta = ultimo_dia_cerrado()
    rango = db.rango(ticker, plazo)
    desde = (date.fromisoformat(rango[1]) + timedelta(days=1)) if rango else date.fromisoformat(PRECIOS_DESDE)
    if desde > hasta:
        return 0                                    # ya está al día
    crudos = ppi.historico(ticker, datos["tipo"], desde.isoformat(), hasta.isoformat(), plazo)
    filas = [_fila(c) for c in crudos]
    filas = [f for f in filas if f and f["fecha"] <= hasta.isoformat()]
    return db.guardar(ticker, plazo, filas, FUENTE)


def actualizar_todos() -> dict:
    """Actualiza todos los activos seguidos. Devuelve {ticker: precios nuevos o mensaje de error}."""
    resultado = {}
    for i in db.seguidos():
        try:
            resultado[i["ticker"]] = actualizar(i["ticker"])
        except Exception as e:                      # un activo con problemas no frena a los demás
            resultado[i["ticker"]] = f"error: {e}"
    return resultado


def _fila(c: dict) -> dict | None:
    """Convierte un precio de PPI al formato de la base. Descarta los que no tienen cierre."""
    if not isinstance(c.get("price"), (int, float)) or not c.get("date"):
        return None
    return {"fecha": str(c["date"])[:10], "apertura": c.get("openingPrice"), "maximo": c.get("max"),
            "minimo": c.get("min"), "cierre": c["price"], "volumen": c.get("volume")}