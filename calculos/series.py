"""Variaciones de series de tiempo, calculadas por el proyecto (no por la API de origen).

Todas las funciones reciben y devuelven listas [{'fecha': 'AAAA-MM-DD', 'valor': float}]
ordenadas de la más vieja a la más nueva. Las variaciones se devuelven en porcentaje
(0.3 = 0,3%), con las mismas definiciones que usan FRED y datos.gob.ar:

    variacion                 (x_t / x_t-1) − 1                       contra el período anterior
    variacion_interanual      (x_t / x_t-1año) − 1                    contra el mismo período del año anterior
    variacion_anualizada      (x_t / x_t-1) ^ (períodos por año) − 1  como se informa el PBI de EE. UU.
    variacion_acumulada_anio  (x_t / último valor del año anterior) − 1

Para calcularlas hacen falta datos anteriores al período pedido: pedí la serie desde
`desde_extendido(desde)` y después recortá con `recortar`.
"""
from bisect import bisect_right
from datetime import date, timedelta
from statistics import median

MODOS = ("valor", "variacion", "variacion_interanual", "variacion_anualizada", "variacion_acumulada_anio")
DIAS_PREVIOS = 800      # cuánto antes de 'desde' hay que traer datos para poder calcular cualquier variación
TOLERANCIA_DIAS = 7     # series diarias o semanales: cuán lejos puede estar el dato de "un año antes"


def periodos_por_anio(serie: list[dict]) -> int | None:
    """Frecuencia de la serie según la distancia típica entre fechas: 12 mensual, 4 trimestral, etc.

    Devuelve None para series diarias (no tiene sentido anualizar período a período).
    """
    if len(serie) < 3:
        return None
    fechas = [date.fromisoformat(d["fecha"][:10]) for d in serie]
    dias = median((b - a).days for a, b in zip(fechas, fechas[1:]))
    for limite, periodos in ((3, None), (10, 52), (40, 12), (100, 4), (200, 2), (400, 1)):
        if dias <= limite:
            return periodos
    return None


def transformar(serie: list[dict], modo: str) -> list[dict]:
    """Aplica el modo a toda la serie. Los puntos sin dato de comparación se omiten."""
    if modo not in MODOS:
        raise ValueError(f"modo '{modo}' inválido. Opciones: {', '.join(MODOS)}.")
    if modo == "valor":
        return list(serie)
    periodos = periodos_por_anio(serie)
    # Contra el período anterior: solo si es el inmediatamente anterior. Si falta un mes (ej.: el CPI de
    # octubre de 2025, que no se relevó), la variación de noviembre queda vacía, como en la fuente oficial.
    pares = [(a, b) for a, b in zip(serie, serie[1:]) if _ok(a) and _consecutivos(a, b, periodos)]
    if modo == "variacion":
        return [_punto(b, a) for a, b in pares]
    if modo == "variacion_anualizada":
        if periodos is None:
            raise ValueError("variacion_anualizada no aplica a series diarias.")
        return [{"fecha": b["fecha"], "valor": ((b["valor"] / a["valor"]) ** periodos - 1) * 100}
                for a, b in pares if b["valor"] / a["valor"] > 0]
    if modo == "variacion_interanual":
        return _contra(serie, _un_anio_antes(serie))
    return _contra(serie, _fin_del_anio_anterior(serie))      # variacion_acumulada_anio


def desde_extendido(desde: str) -> str:
    """Fecha desde la que hay que pedir datos para calcular variaciones a partir de 'desde'."""
    return (date.fromisoformat(desde) - timedelta(days=DIAS_PREVIOS)).isoformat()


def faltantes(niveles: list[dict], resultado: list[dict], modo: str, desde: str | None = None) -> list[dict]:
    """Fechas con nivel pero sin variación calculable, con el dato de comparación que falta.

    Devuelve [{'fecha': '2026-10-01', 'base': '2025-10-01'}, ...] desde 'desde'.
    """
    calculadas = {d["fecha"] for d in resultado}
    periodos = periodos_por_anio(niveles)
    return [{"fecha": d["fecha"][:10], "base": _base_esperada(d["fecha"][:10], modo, periodos)}
            for d in niveles if d["fecha"] not in calculadas and (not desde or d["fecha"][:10] >= desde)]


def recortar(serie: list[dict], desde: str | None = None, hasta: str | None = None) -> list[dict]:
    return [d for d in serie if (not desde or d["fecha"][:10] >= desde) and (not hasta or d["fecha"][:10] <= hasta)]


# ---------------------------------------------------------------------------
# Internas
# ---------------------------------------------------------------------------
def _ok(base: dict) -> bool:
    return base["valor"] not in (0, None)


def _base_esperada(fecha: str, modo: str, periodos: int | None) -> str:
    """Con qué fecha se compara cada punto, para explicar qué dato falta."""
    f = date.fromisoformat(fecha)
    if modo == "variacion_interanual":
        return f"{f.year - 1}{fecha[4:]}"
    if modo == "variacion_acumulada_anio":
        return f"diciembre de {f.year - 1}"
    if periodos in (12, 4, 2, 1):                       # el período anterior en series mensuales o más espaciadas
        meses = 12 // periodos
        total = f.year * 12 + f.month - 1 - meses
        return f"{total // 12}-{total % 12 + 1:02d}-{fecha[8:10]}"
    return "el período anterior"


def _consecutivos(a: dict, b: dict, periodos: int | None) -> bool:
    """¿b es el período siguiente a a? En series diarias se aceptan fines de semana y feriados."""
    dias = (date.fromisoformat(b["fecha"][:10]) - date.fromisoformat(a["fecha"][:10])).days
    return dias <= (365 / periodos) * 1.5 if periodos else dias <= TOLERANCIA_DIAS


def _punto(actual: dict, base: dict) -> dict:
    return {"fecha": actual["fecha"], "valor": (actual["valor"] / base["valor"] - 1) * 100}


def _contra(serie: list[dict], buscar_base) -> list[dict]:
    resultado = []
    for d in serie:
        base = buscar_base(d)
        if base and _ok(base):
            resultado.append(_punto(d, base))
    return resultado


def _un_anio_antes(serie: list[dict]):
    """Busca el dato de un año antes: exacto en series mensuales o más espaciadas; el más cercano anterior en diarias."""
    por_fecha = {d["fecha"][:10]: d for d in serie}
    fechas = [d["fecha"][:10] for d in serie]
    exacta = (periodos_por_anio(serie) or 365) <= 12

    def buscar(d):
        f = date.fromisoformat(d["fecha"][:10])
        objetivo = f.replace(year=f.year - 1) if not (f.month == 2 and f.day == 29) else date(f.year - 1, 2, 28)
        if exacta:
            return por_fecha.get(objetivo.isoformat())
        i = bisect_right(fechas, objetivo.isoformat()) - 1
        if i >= 0 and (objetivo - date.fromisoformat(fechas[i])).days <= TOLERANCIA_DIAS:
            return serie[i]
        return None
    return buscar


def _fin_del_anio_anterior(serie: list[dict]):
    """Último dato del año anterior, solo si es de diciembre (si no, la serie está incompleta)."""
    ultimo_por_anio = {}
    for d in serie:
        ultimo_por_anio[d["fecha"][:4]] = d

    def buscar(d):
        base = ultimo_por_anio.get(str(int(d["fecha"][:4]) - 1))
        return base if base and base["fecha"][5:7] == "12" else None
    return buscar
