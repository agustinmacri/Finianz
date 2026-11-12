"""Consultas de la base de precios (datos/precios.db).

La base guarda los precios de cierre diarios de cada activo consultado, para no depender
de las APIs: la carga y la actualización están en carga_datos/precios.py.
"""
from datetime import date

from admin_datos.db import conectar, ruta

BASE = "precios"


def instrumento(ticker: str) -> dict | None:
    """Datos del activo si ya se sigue (ticker, tipo, moneda, descripcion, isin, mercado...)."""
    if not ruta(BASE).exists():
        return None
    with conectar(BASE) as con:
        fila = con.execute("SELECT * FROM instrumentos WHERE ticker = ?", (ticker.upper(),)).fetchone()
    return dict(fila) if fila else None


def seguidos() -> list[dict]:
    """Todos los activos que se siguen (los que se consultaron alguna vez)."""
    if not ruta(BASE).exists():
        return []
    with conectar(BASE) as con:
        return [dict(f) for f in con.execute("SELECT * FROM instrumentos ORDER BY ticker")]


def registrar(datos: dict, fuente: str):
    """Agrega un activo a los seguidos (si ya estaba, actualiza su descripción)."""
    with conectar(BASE) as con:
        con.execute(
            "INSERT INTO instrumentos VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(ticker) DO UPDATE SET "
            "tipo = excluded.tipo, moneda = excluded.moneda, descripcion = excluded.descripcion, "
            "isin = excluded.isin, mercado = excluded.mercado",
            (datos["ticker"].upper(), datos["tipo"], datos.get("moneda"), datos.get("descripcion"), datos.get("isin"),
             datos.get("mercado"), fuente, date.today().isoformat()))


def guardar(ticker: str, plazo: str, filas: list[dict], fuente: str) -> int:
    """Guarda precios diarios [{'fecha', 'apertura', 'maximo', 'minimo', 'cierre', 'volumen'}].

    Si un día ya estaba, se reemplaza (la fuente puede corregir un cierre). Devuelve cuántos guardó.
    """
    with conectar(BASE) as con:
        con.executemany(
            "INSERT OR REPLACE INTO precios VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(ticker.upper(), plazo, f["fecha"], f.get("apertura"), f.get("maximo"), f.get("minimo"), f["cierre"],
              f.get("volumen"), fuente) for f in filas])
    return len(filas)


def entre(ticker: str, plazo: str, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    """Precios guardados entre dos fechas (inclusive), del más viejo al más nuevo."""
    if not ruta(BASE).exists():
        return []
    with conectar(BASE) as con:
        return [dict(f) for f in con.execute(
            "SELECT * FROM precios WHERE ticker = ? AND plazo = ? AND fecha BETWEEN ? AND ? ORDER BY fecha",
            (ticker.upper(), plazo, desde or "0000-00-00", hasta or "9999-12-31"))]


def rango(ticker: str, plazo: str) -> tuple[str, str, int] | None:
    """Primera fecha, última fecha y cantidad de precios guardados."""
    if not ruta(BASE).exists():
        return None
    with conectar(BASE) as con:
        primera, ultima, cantidad = con.execute(
            "SELECT MIN(fecha), MAX(fecha), COUNT(*) FROM precios WHERE ticker = ? AND plazo = ?",
            (ticker.upper(), plazo)).fetchone()
    return (primera, ultima, cantidad) if cantidad else None