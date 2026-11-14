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


MESES_REFERENCIA = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6, "jul": 7, "ago": 8, "sep": 9, "oct": 10,
                    "nov": 11, "dic": 12}


def por_mes(variable: str, relevamiento: str | None = None, estadistico: str = "mediana",
            incluir_anuales: bool = True, incluir_proximos: bool = False) -> dict[tuple[int, int], float]:
    """{(año, mes): valor}: los períodos mensuales y, si se pide, los anuales (y los "próximos 12/24 meses")
    ubicados en el mes que indica su referencia (ej.: "var. % i.a.; dic-27" o "$/USD; oct-27"). Un mes con dato
    mensual no se pisa."""
    import re
    relevamiento = relevamiento or ultimo()
    if relevamiento is None:
        return {}
    with conectar(BASE) as con:
        filas = [dict(f) for f in con.execute(
            f"SELECT periodo, referencia, {estadistico} AS valor FROM rem WHERE relevamiento = ? AND variable = ?",
            (relevamiento, variable))]
    salida = {}
    for f in filas:
        if re.fullmatch(r"\d{4}-\d{2}", f["periodo"]):
            salida[(int(f["periodo"][:4]), int(f["periodo"][5:]))] = f["valor"]
    if incluir_anuales:
        for f in filas:
            if not (f["periodo"].isdigit() or (incluir_proximos and f["periodo"].startswith("prox"))):
                continue
            m = re.search(r"([a-z]{3})-(\d{2})\s*$", (f["referencia"] or "").lower())
            if m and m.group(1) in MESES_REFERENCIA:
                mes = (2000 + int(m.group(2)), MESES_REFERENCIA[m.group(1)])
                salida.setdefault(mes, f["valor"])
    return salida

