"""Consultas de la base del REM (datos/rem.db). La carga está en carga_datos/rem.py."""
from admin_datos.db import conectar, ruta

BASE = "rem"


def relevamientos() -> list[str]:
    """Relevamientos cargados (AAAA-MM), del más viejo al más nuevo."""
    if not ruta(BASE).exists():
        return []
    with conectar(BASE) as con:
        return [f["relevamiento"] for f in con.execute("SELECT DISTINCT relevamiento FROM rem ORDER BY relevamiento")]


def ultimo() -> str | None:
    lista = relevamientos()
    return lista[-1] if lista else None


def valores(variable: str, relevamiento: str | None = None, estadistico: str = "mediana") -> dict[str, float]:
    """{periodo: valor} de una variable en un relevamiento (por defecto, el último)."""
    if estadistico not in ("mediana", "promedio", "maximo", "minimo", "p90", "p75", "p25", "p10"):
        raise ValueError(f"Estadístico desconocido: {estadistico}.")
    relevamiento = relevamiento or ultimo()
    if relevamiento is None:
        return {}
    with conectar(BASE) as con:
        return {f["periodo"]: f[estadistico] for f in con.execute(
            f"SELECT periodo, {estadistico} FROM rem WHERE relevamiento = ? AND variable = ?", (relevamiento, variable))}
