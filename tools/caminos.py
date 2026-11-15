"""Tabla del camino proyectado contra el breakeven y el REM, con el mismo formato para inflación, TAMAR y dólar.

Mes a mes hasta diciembre del año que viene y, después, un renglón por año (lo que pidió Agustin para las
proyecciones). Cada columna es una fuente: la que se usó para el cálculo y, como contraste, la que descuenta el
mercado (breakeven) y la del REM. Una columna sin dato para un mes muestra "–"; un asterisco marca los meses en
que la fuente se extendió más allá de su último dato (por ejemplo, el breakeven después del último bono).
"""
from dataclasses import dataclass, field
from typing import Callable

from renta_fija.calculadoras import proyeccion_cer as pc

MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")
Mes = tuple[int, int]


def nombre_mes(mes: Mes) -> str:
    return f"{MESES[mes[1] - 1]}-{mes[0] % 100:02d}"


def pct(x: float | None, decimales: int = 2) -> str:
    if x is None:
        return "–"
    return f"{x * 100:.{decimales}f}%"


def pesos(x: float | None) -> str:
    if x is None:
        return "–"
    return f"{x:,.2f}"


@dataclass
class Columna:
    titulo: str
    mensual: Callable[[Mes], float | None]          # valor del mes (None si la fuente no lo tiene)
    anual: Callable[[int, Mes, Mes], float | None]   # valor del año entre dos meses (inclusive)
    extendido: Callable[[Mes], bool] = field(default=lambda mes: False)


def _seguro(funcion, *args):
    try:
        return funcion(*args)
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return None


def tabla(titulo: str, columnas: list[Columna], desde: Mes, hasta: Mes, anio_operacion: int,
          formato=pct, formato_anual=None, nota_anual: str = "") -> list[str]:
    """Renglones de texto de la tabla: meses uno por uno hasta diciembre del año siguiente, después años."""
    formato_anual = formato_anual or formato
    corte = (anio_operacion + 1, 12)
    encabezado = f"{titulo} | " + " | ".join(c.titulo for c in columnas)
    lineas = [encabezado]
    mes = desde
    while mes <= min(hasta, corte):
        celdas = []
        for c in columnas:
            valor = _seguro(c.mensual, mes)
            celdas.append(formato(valor) + ("*" if valor is not None and _seguro(c.extendido, mes) else ""))
        lineas.append(f"{nombre_mes(mes)} | " + " | ".join(celdas))
        mes = pc.sumar_meses(mes, 1)
    # Resumen anual de todos los años del horizonte
    anuales = []
    for anio in range(desde[0], hasta[0] + 1):
        primero, ultimo = max(desde, (anio, 1)), min(hasta, (anio, 12))
        etiqueta = str(anio) if ultimo[1] == 12 else f"{anio} (hasta {MESES[ultimo[1] - 1]})"
        celdas = []
        for c in columnas:
            valor = _seguro(c.anual, anio, primero, ultimo)
            celdas.append(formato_anual(valor) + ("*" if valor is not None and _algun_extendido(c, primero, ultimo) else ""))
        anuales.append(f"{etiqueta} | " + " | ".join(celdas))
    if anuales:
        lineas.append(f"Año{(' (' + nota_anual + ')') if nota_anual else ''} | " + " | ".join(c.titulo for c in columnas))
        lineas += anuales
    return lineas


def _algun_extendido(columna: Columna, primero: Mes, ultimo: Mes) -> bool:
    mes = primero
    while mes <= ultimo:
        if _seguro(columna.extendido, mes):
            return True
        mes = pc.sumar_meses(mes, 1)
    return False


# --- Agregados anuales ---

def inflacion_anual(camino: Callable[[Mes], float | None], publicadas: dict[Mes, float], desde: Mes):
    """Inflación de diciembre a diciembre: los meses publicados con el dato del INDEC y los demás con el camino.
    Si el horizonte termina antes de diciembre, la acumulada de enero hasta ese mes."""
    def anual(anio: int, primero: Mes, ultimo: Mes) -> float | None:
        total = 1.0
        for m in range(1, ultimo[1] + 1):
            mes = (anio, m)
            valor = publicadas.get(mes) if mes < desde else camino(mes)
            if valor is None:
                return None
            total *= 1 + valor
        return total - 1
    return anual


def promedio(camino: Callable[[Mes], float | None]):
    """Promedio simple de los meses del año dentro del horizonte (para la TAMAR)."""
    def anual(anio: int, primero: Mes, ultimo: Mes) -> float | None:
        valores, mes = [], primero
        while mes <= ultimo:
            v = camino(mes)
            if v is None:
                return None
            valores.append(v)
            mes = pc.sumar_meses(mes, 1)
        return sum(valores) / len(valores) if valores else None
    return anual


def acumulado(camino: Callable[[Mes], float | None], desde: Mes, hasta: Mes, compuesto: bool = True) -> float | None:
    """Inflación acumulada (compuesta) o promedio simple del camino en el horizonte."""
    valores, mes = [], desde
    while mes <= hasta:
        v = _seguro(camino, mes)
        if v is None:
            return None
        valores.append(v)
        mes = pc.sumar_meses(mes, 1)
    if not valores:
        return None
    if not compuesto:
        return sum(valores) / len(valores)
    total = 1.0
    for v in valores:
        total *= 1 + v
    return total - 1
