"""Bonos dollar linked: valor nominal en dólares, se suscriben, cotizan y pagan en pesos al tipo de cambio.

Definiciones de Agustin (13/11/2026; docs/convenciones-renta-fija.md):
- Precio en dólares = precio en pesos (por 100 VN) / A3500 del día de concertación de la operación.
  Intradiario, mientras no se publica (a las 15 h), se estima con el A3500 del día hábil anterior.
- Bullet (los del Tesoro): al vencimiento pagan 100 dólares por 100 VN, en pesos al tipo de cambio de
  pago que fija el prospecto. En dólares, el flujo es 100.
- Convención actual/365 (distinta de los hard dollar):
  TNA = (100 / precio en dólares − 1) × 365 / plazo residual; TIR = (1 + TNA × plazo/365)^(365/plazo) − 1;
  duration = plazo / 365; TEM de 30 días corridos.
- Con cupones y amortizaciones (corporativos, ONs): flujos en dólares por 100 VN. La renta de cada período es
  residual × tasa × fracción de año según la base del prospecto (30/360, actual/365 o actual/360). Precio en
  dólares, interés corrido, valor técnico y paridad como los demás bonos con cupón. TIR efectiva anual (base 365,
  fechas corridas), TNA semestral exacta, duration, duration modificada, convexidad, current y cash yield.
  Los pagos se cobran en pesos al tipo de cambio de pago de cada prospecto (informativo: en dólares, el flujo es
  el de la ficha).

Funciones puras: el precio y el tipo de cambio los recibe el que llama.
"""
from datetime import date, timedelta

from renta_fija.calculadoras import motor, tasa_fija
from renta_fija.calculadoras.motor import Flujo

PAGO_FINAL_USD = 100.0


def calcular_bullet(precio_pesos: float, tipo_cambio: float, liquidacion: date, vencimiento: date) -> dict:
    if tipo_cambio <= 0:
        raise ValueError("El tipo de cambio tiene que ser positivo.")
    precio_usd = precio_pesos / tipo_cambio
    r = tasa_fija.calcular_capitalizable(precio_usd, PAGO_FINAL_USD, liquidacion, vencimiento)
    return {"precio_usd": precio_usd, "tipo_cambio": tipo_cambio, **{k: v for k, v in r.items() if k != "pago_final"}}


def cronograma(pagos: list[dict], tasa: float, emision: date, base: str) -> list[dict]:
    """Cada pago con su residual anterior, su renta y su amortización (por 100 VN, en dólares)."""
    residual, filas, anterior = 100.0, [], emision
    for p in sorted(pagos, key=lambda p: p["fecha"]):
        renta = residual * tasa * motor.fraccion_anio(anterior, p["fecha"], base)
        amort = p.get("amortizacion", 0.0)
        filas.append({"fecha": p["fecha"], "residual_previo": residual, "renta": renta, "amortizacion": amort})
        residual -= amort
        anterior = p["fecha"]
    return filas


def calcular_cupon(precio_pesos: float, tipo_cambio: float, liquidacion: date, pagos: list[dict], tasa: float,
                   emision: date, base: str, ajustar_fecha) -> dict:
    """Dollar linked con cupón y amortización: todo en dólares, con el precio pasado a dólares."""
    if tipo_cambio <= 0:
        raise ValueError("El tipo de cambio tiene que ser positivo.")
    precio = precio_pesos / tipo_cambio
    filas = cronograma(pagos, tasa, emision, base)
    pasados = [f for f in filas if f["fecha"] <= liquidacion]
    futuros = [f for f in filas if f["fecha"] > liquidacion]
    if not futuros:
        raise ValueError("El bono ya no tiene pagos después de la liquidación.")
    residual = 100.0 - sum(f["amortizacion"] for f in pasados)
    ultimo = pasados[-1]["fecha"] if pasados else emision
    corrido = motor.interes_corrido(residual, tasa, ultimo, liquidacion, base)
    tecnico = residual + corrido
    flujos = [Flujo(ajustar_fecha(f["fecha"]), f["renta"], f["amortizacion"]) for f in futuros]
    tir = motor.tir(flujos, precio, liquidacion)
    md = motor.duration_modificada(flujos, liquidacion, tir)
    cvx = motor.convexidad(flujos, liquidacion, tir)
    sin_corrido = precio - corrido
    caja = sum(f.total for f in flujos if f.fecha <= liquidacion + timedelta(days=365))
    return {
        "precio_usd": precio, "tipo_cambio": tipo_cambio, "residual": residual, "interes_corrido": corrido,
        "valor_tecnico": tecnico, "paridad": precio / tecnico, "tir": tir, "tna_semestral": motor.tna_semestral(tir),
        "tem": motor.tem(tir), "duration": motor.duration(flujos, liquidacion, tir), "duration_modificada": md,
        "convexidad": cvx, "pv01": motor.sensibilidad(precio, md, cvx, 0.0001), "dd": motor.sensibilidad(precio, md, cvx, 0.01),
        "current_yield": tasa * residual / sin_corrido, "cash_yield": caja / sin_corrido, "flujos": flujos,
    }

