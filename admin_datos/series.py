"""Consultas de la base de series (datos/series.db).

Guarda series diarias oficiales que usan las calculadoras, para no pedirlas a la API en cada
cálculo: el CER y la TAMAR de bancos privados (% TNA) del BCRA; más adelante tipo de cambio A3500, UVA, etc.
Los valores se guardan como los publica la fuente (la TAMAR en %, no en fracción).
La carga y la actualización están en carga_datos/series.py.
"""
from datetime import date

from admin_datos.db import conectar, ruta

BASE = "series"


def guardar(variable: str, filas: list[dict], fuente: str) -> int:
    """Guarda valores diarios [{'fecha': 'AAAA-MM-DD', 'valor': x}]. Si un día ya estaba, se reemplaza."""
    with conectar(BASE) as con:
        con.executemany("INSERT OR REPLACE INTO series VALUES (?, ?, ?, ?)",
                        [(variable, f["fecha"][:10], f["valor"], fuente) for f in filas])
    return len(filas)


def valor(variable: str, fecha: date) -> float | None:
    """Valor de una fecha exacta, o None si no está en la base."""
    if not ruta(BASE).exists():
        return None
    with conectar(BASE) as con:
        fila = con.execute("SELECT valor FROM series WHERE variable = ? AND fecha = ?",
                           (variable, fecha.isoformat())).fetchone()
    return fila["valor"] if fila else None


def entre(variable: str, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    """Valores guardados entre dos fechas (inclusive), del más viejo al más nuevo."""
    if not ruta(BASE).exists():
        return []
    with conectar(BASE) as con:
        return [dict(f) for f in con.execute(
            "SELECT fecha, valor, fuente FROM series WHERE variable = ? AND fecha BETWEEN ? AND ? ORDER BY fecha",
            (variable, desde or "0000-00-00", hasta or "9999-12-31"))]


def rango(variable: str) -> tuple[str, str, int] | None:
    """Primera fecha, última fecha y cantidad de valores guardados."""
    if not ruta(BASE).exists():
        return None
    with conectar(BASE) as con:
        primera, ultima, cantidad = con.execute(
            "SELECT MIN(fecha), MAX(fecha), COUNT(*) FROM series WHERE variable = ?", (variable,)).fetchone()
    return (primera, ultima, cantidad) if cantidad else None
