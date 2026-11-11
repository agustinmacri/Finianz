"""Consultas del calendario de publicaciones (datos/publicaciones.db)."""
import unicodedata
from datetime import date

from admin_datos.db import conectar, ruta

BASE = "publicaciones"
NIVELES = {"alta": ("alta",), "media": ("alta", "media"), "baja": ("alta", "media", "baja")}


def hay_datos() -> bool:
    if not ruta(BASE).exists():
        return False
    with conectar(BASE) as con:
        return con.execute("SELECT 1 FROM publicaciones LIMIT 1").fetchone() is not None


def entre(desde: date, hasta: date, pais: str | None = None, importancia: str = "media",
          texto: str | None = None) -> list[dict]:
    """Publicaciones entre dos fechas (inclusive), ordenadas por fecha.

    importancia: nivel mínimo ("alta" muestra solo alta; "media", alta y media; "baja", todas).
    texto: filtra por código o por palabras del título, sin distinguir mayúsculas ni tildes.
    """
    niveles = NIVELES[importancia]
    consulta = (f"SELECT * FROM publicaciones WHERE fecha BETWEEN ? AND ? "
                f"AND importancia IN ({', '.join('?' * len(niveles))})")
    parametros = [desde.isoformat(), hasta.isoformat(), *niveles]
    if pais:
        consulta += " AND pais = ?"
        parametros.append(pais)
    with conectar(BASE) as con:
        filas = [dict(f) for f in con.execute(consulta + " ORDER BY fecha, importancia, organismo", parametros)]
    if texto:
        filas = [f for f in filas if _coincide(f, texto)]
    return filas


def rango_cargado(pais: str | None = None) -> tuple[str, str] | None:
    """Primera y última fecha con publicaciones cargadas (para avisar si se pide algo fuera de rango)."""
    if not ruta(BASE).exists():
        return None
    consulta, parametros = "SELECT MIN(fecha), MAX(fecha) FROM publicaciones", []
    if pais:
        consulta += " WHERE pais = ?"
        parametros.append(pais)
    with conectar(BASE) as con:
        desde, hasta = con.execute(consulta, parametros).fetchone()
    return (desde, hasta) if desde else None


def _coincide(fila: dict, texto: str) -> bool:
    buscado = _normalizar(texto)
    if fila["codigo"] and _normalizar(fila["codigo"]) == buscado.replace(" ", "_"):
        return True
    titulo = _normalizar(fila["titulo"])
    return all(palabra in titulo for palabra in buscado.split())


def _normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar textos."""
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
