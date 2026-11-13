"""Bonos soberanos en dólares (hard dollar): Bonares (ley argentina, AL) y Globales (ley Nueva York, GD).

Convenciones (decisiones de Agustin, 13/11/2026; docs/convenciones-renta-fija.md):
- Precio por 100 VN original, en dólares, como cotiza (con cupón corrido). Se calcula con el precio
  MEP (ticker D) y con el cable (ticker C).
- Cupón step-up: cada período devenga la tasa vigente al inicio del período, sobre el residual,
  en base 30/360: residual × tasa × días 30/360 / 360.
- Interés corrido = residual × tasa vigente × días 30/360 desde el último cupón / 360.
- TIR: nominal anual con capitalización semestral, base 30/360 (convención de mercado de los bonos
  en dólares). TEA equivalente = (1 + TIR/2)^2 − 1.
- Duration (Macaulay, años), duration modificada = duration / (1 + TIR/2) y convexidad con esa TIR.
- Spread contra Treasuries: TIR − rendimiento del Treasury (constant maturity de FRED, que también es
  semestral) interpolado linealmente a la duration del bono.

Funciones puras: precios, fechas hábiles y curva de Treasuries los recibe el que llama.
"""
from datetime import date, timedelta

from renta_fija.calculadoras import motor
from renta_fija.calculadoras.motor import Flujo

VN = 100.0
FRECUENCIA_TIR = 2      # TIR semestral


def tasa_vigente(tramos: list[dict], fecha: date) -> float:
    """Tasa del step-up vigente en una fecha: la del último tramo que empezó en o antes de esa fecha."""
    vigentes = [t for t in sorted(tramos, key=lambda t: t["desde"]) if t["desde"] <= fecha]
    if not vigentes:
        raise ValueError(f"No hay tasa vigente al {fecha}: el primer tramo empieza después.")
    return vigentes[-1]["tasa"]


def cronograma(pagos: list[dict], tramos: list[dict], emision: date) -> list[dict]:
    """Cada pago con su residual anterior, su tasa, su renta y su amortización (por 100 VN)."""
    residual, filas, anterior = VN, [], emision
    for p in sorted(pagos, key=lambda p: p["fecha"]):
        tasa = tasa_vigente(tramos, anterior)
        renta = residual * tasa * motor.dias_30_360(anterior, p["fecha"]) / 360
        amort = p.get("amortizacion", 0.0)
        filas.append({"fecha": p["fecha"], "residual_previo": residual, "tasa": tasa, "renta": renta,
                      "amortizacion": amort})
        residual -= amort
        anterior = p["fecha"]
    return filas


def calcular(precio: float, liquidacion: date, pagos: list[dict], tramos: list[dict], emision: date,
             ajustar_fecha) -> dict:
    """Todas las variables con un precio en dólares (por 100 VN original, con cupón corrido)."""
    filas = cronograma(pagos, tramos, emision)
    pasados = [f for f in filas if f["fecha"] <= liquidacion]
    futuros = [f for f in filas if f["fecha"] > liquidacion]
    if not futuros:
        raise ValueError("El bono ya no tiene pagos después de la liquidación.")
    residual = VN - sum(f["amortizacion"] for f in pasados)
    ultimo_cupon = pasados[-1]["fecha"] if pasados else emision
    tasa = tasa_vigente(tramos, ultimo_cupon)
    corrido = residual * tasa * motor.dias_30_360(ultimo_cupon, liquidacion) / 360
    tecnico = residual + corrido
    clean = precio - corrido
    flujos = [Flujo(ajustar_fecha(f["fecha"]), f["renta"], f["amortizacion"]) for f in futuros]

    tir = motor.tir_30_360(flujos, precio, liquidacion, FRECUENCIA_TIR)
    dur = motor.duration_30_360(flujos, liquidacion, tir, FRECUENCIA_TIR)
    md = motor.duration_modificada_30_360(flujos, liquidacion, tir, FRECUENCIA_TIR)
    cvx = motor.convexidad_30_360(flujos, liquidacion, tir, FRECUENCIA_TIR)
    caja_12m = sum(f.total for f in flujos if f.fecha <= liquidacion + timedelta(days=365))
    return {
        "residual": residual,
        "tasa_vigente": tasa,
        "interes_corrido": corrido,
        "valor_tecnico": tecnico,
        "precio_clean": clean,
        "paridad": precio / tecnico,
        "tir": tir,
        "tea": (1 + tir / FRECUENCIA_TIR) ** FRECUENCIA_TIR - 1,
        "duration": dur,
        "duration_modificada": md,
        "convexidad": cvx,
        "pv01": motor.sensibilidad(precio, md, cvx, 0.0001),
        "dd": motor.sensibilidad(precio, md, cvx, 0.01),
        "current_yield": tasa * residual / clean,
        "cash_yield": caja_12m / clean,
        "flujos": flujos,
    }


def interpolar(curva: list[tuple[float, float]], plazo: float) -> float:
    """Interpolación lineal en una curva [(plazo en años, tasa)]; fuera del rango, el extremo más cercano."""
    puntos = sorted(curva)
    if plazo <= puntos[0][0]:
        return puntos[0][1]
    for (p0, t0), (p1, t1) in zip(puntos, puntos[1:]):
        if plazo <= p1:
            return t0 + (t1 - t0) * (plazo - p0) / (p1 - p0)
    return puntos[-1][1]
