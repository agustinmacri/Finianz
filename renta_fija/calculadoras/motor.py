"""Motor financiero de bonos: una sola matemática para todas las familias.

Recibe flujos ya generados (fecha, renta, amortización) y un precio, y calcula los indicadores.
No sabe de CER, tasa fija ni dólares: eso lo resuelven los generadores de cada familia
(un archivo por familia en renta_fija/calculadoras/), que entregan los flujos y el precio en las mismas unidades.

Convenciones (acordadas con Agustin):
- TIR efectiva anual, base 365 días corridos, desde la fecha de liquidación:
      precio = Σ flujo_i / (1 + TIR) ^ (días_i / 365)
- Solo cuentan los flujos posteriores a la liquidación.
- Duration de Macaulay en años; duration modificada = Macaulay / (1 + TIR); convexidad en años².
- Precio y flujos por cada 100 de valor nominal original.
"""
from dataclasses import dataclass
from datetime import date, timedelta

BASE = 365
TOLERANCIA = 1e-12
MAX_ITERACIONES = 200


@dataclass
class Flujo:
    fecha: date
    renta: float = 0.0
    amortizacion: float = 0.0

    @property
    def total(self) -> float:
        return self.renta + self.amortizacion


def futuros(flujos: list[Flujo], liquidacion: date) -> list[Flujo]:
    """Flujos que todavía no se cobraron a la fecha de liquidación."""
    return sorted((f for f in flujos if f.fecha > liquidacion), key=lambda f: f.fecha)


def _plazos(flujos: list[Flujo], liquidacion: date) -> list[tuple[float, float]]:
    """(años, monto) de cada flujo futuro."""
    return [((f.fecha - liquidacion).days / BASE, f.total) for f in futuros(flujos, liquidacion)]


def valor_presente(flujos: list[Flujo], liquidacion: date, tir: float) -> float:
    return sum(m / (1 + tir) ** t for t, m in _plazos(flujos, liquidacion))


def tir(flujos: list[Flujo], precio: float, liquidacion: date) -> float:
    """TIR efectiva anual (fracción: 0.08 = 8%) que iguala el valor presente de los flujos al precio.

    Newton-Raphson con respaldo por bisección: el valor presente baja cuando sube la tasa,
    así que la solución es única si todos los flujos son positivos.
    """
    plazos = _plazos(flujos, liquidacion)
    if not plazos:
        raise ValueError("No quedan flujos después de la fecha de liquidación.")
    if precio <= 0:
        raise ValueError("El precio tiene que ser positivo.")

    def f(r):
        return sum(m / (1 + r) ** t for t, m in plazos) - precio

    def df(r):
        return sum(-t * m / (1 + r) ** (t + 1) for t, m in plazos)

    # Bisección en un rango amplio (de −99% a +10.000% anual) y Newton para afinar
    bajo, alto = -0.99, 100.0
    if f(bajo) < 0 or f(alto) > 0:
        raise ValueError("No hay una TIR razonable para ese precio (revisá el precio y los flujos).")
    r = 0.1
    for _ in range(MAX_ITERACIONES):
        valor = f(r)
        if abs(valor) < TOLERANCIA * max(1.0, precio):
            return r
        if valor > 0:
            bajo = r
        else:
            alto = r
        derivada = df(r)
        siguiente = r - valor / derivada if derivada else None
        r = siguiente if siguiente is not None and bajo < siguiente < alto else (bajo + alto) / 2
    return r


def duration(flujos: list[Flujo], liquidacion: date, tir_: float) -> float:
    """Duration de Macaulay, en años."""
    plazos = _plazos(flujos, liquidacion)
    vp = sum(m / (1 + tir_) ** t for t, m in plazos)
    return sum(t * m / (1 + tir_) ** t for t, m in plazos) / vp


def duration_modificada(flujos: list[Flujo], liquidacion: date, tir_: float) -> float:
    """Variación porcentual aproximada del precio ante un cambio de 1 punto en la TIR."""
    return duration(flujos, liquidacion, tir_) / (1 + tir_)


def convexidad(flujos: list[Flujo], liquidacion: date, tir_: float) -> float:
    """Convexidad, en años²."""
    plazos = _plazos(flujos, liquidacion)
    vp = sum(m / (1 + tir_) ** t for t, m in plazos)
    return sum(t * (t + 1) * m / (1 + tir_) ** (t + 2) for t, m in plazos) / vp


def residual(flujos: list[Flujo], liquidacion: date) -> float:
    """Valor residual: lo que falta amortizar a la fecha de liquidación."""
    return sum(f.amortizacion for f in futuros(flujos, liquidacion))


def indicadores(flujos: list[Flujo], precio: float, liquidacion: date,
                interes_corrido: float = 0.0) -> dict:
    """Todo junto: TIR, duration, duration modificada, convexidad, valor técnico y paridad.

    interes_corrido: lo devengado desde el último cupón (lo calcula el generador, porque
    depende de la base de cada bono). Valor técnico = residual + interés corrido.
    """
    t = tir(flujos, precio, liquidacion)
    tecnico = residual(flujos, liquidacion) + interes_corrido
    return {
        "tir": t,
        "duration": duration(flujos, liquidacion, t),
        "duration_modificada": duration_modificada(flujos, liquidacion, t),
        "convexidad": convexidad(flujos, liquidacion, t),
        "valor_residual": residual(flujos, liquidacion),
        "interes_corrido": interes_corrido,
        "valor_tecnico": tecnico,
        "paridad": precio / tecnico if tecnico else None,
        "flujos_futuros": futuros(flujos, liquidacion),
    }


# ---------------------------------------------------------------------------
# Convenciones comunes a todas las familias
# ---------------------------------------------------------------------------
def dias_30_360(desde: date, hasta: date) -> int:
    """Días entre dos fechas en base 30/360, método US (el DAYS360 de Excel por defecto)."""
    def fin_de_febrero(d: date) -> bool:
        return d.month == 2 and (d + timedelta(days=1)).month == 3

    d1, d2 = desde.day, hasta.day
    if fin_de_febrero(desde) and fin_de_febrero(hasta):
        d2 = 30
    if fin_de_febrero(desde):
        d1 = 30
    if d2 == 31 and d1 >= 30:
        d2 = 30
    if d1 == 31:
        d1 = 30
    return (hasta.year - desde.year) * 360 + (hasta.month - desde.month) * 30 + (d2 - d1)


def interes_corrido(residual: float, tasa_anual: float, ultimo_cupon: date, liquidacion: date,
                    base: str = "30/360") -> float:
    """Interés devengado desde el último cupón hasta la liquidación (por 100 VN)."""
    if base != "30/360":
        raise ValueError(f"Base de cálculo '{base}' todavía no implementada.")
    return residual * tasa_anual * dias_30_360(ultimo_cupon, liquidacion) / 360


def tna_equivalente(tir_: float, dias: int) -> float:
    """TNA con capitalización cada 'dias' días, equivalente a una TIR efectiva anual (base 365)."""
    return ((1 + tir_) ** (dias / BASE) - 1) * BASE / dias


def tna_semestral(tir_: float) -> float:
    """TNA con capitalización semestral exacta (medio año), equivalente a la TIR: ((1 + TIR)^(1/2) − 1) × 2."""
    return ((1 + tir_) ** 0.5 - 1) * 2


def tem(tir_: float) -> float:
    """Tasa efectiva mensual (30 días) equivalente a una TIR efectiva anual."""
    return (1 + tir_) ** (30 / BASE) - 1


def sensibilidad(precio: float, md: float, cvx: float, variacion: float) -> float:
    """Cambio del precio ante una suba de la TIR de 'variacion' (0.0001 = 1 pb): −MD·Δ + CVX·Δ²/2."""
    return precio * (-variacion * md + variacion ** 2 * cvx / 2)
