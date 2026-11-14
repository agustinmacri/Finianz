"""Bonos y letras a tasa fija en pesos.

Definiciones de Agustin (docs/convenciones-renta-fija.md), tomadas de su planilla de tasa fija
(13/11/2026). Todo por cada 100 de valor nominal original, en T+1.

Capitalizables (Lecap "S", Boncap "T"): no pagan cupón; al vencimiento pagan el pago final.
- Pago final = 100 × (1 + cupón de licitación) ^ (días 30/360 entre emisión y vencimiento / 30). El cupón de
  licitación es la tasa mensual capitalizable con la que se emite (la TEM de emisión).
- Plazo residual = días corridos entre la liquidación y el vencimiento.
- Duration = plazo residual / 365.
- TNA = (pago final / precio − 1) × 365 / plazo residual.
- TEA (TIR) = (1 + TNA × plazo / 365) ^ (365 / plazo) − 1.
- TEM = (pago final / precio) ^ (30 / plazo) − 1   (TEM de 30 días corridos, base 365).

Con cupón y amortización (Bonte, ej. TY30P): la misma matemática que los CER con cupón
(renta_fija/calculadoras/cer_cupon.py) sin ajuste por CER, es decir con ratio = 1.

A descuento (sin capitalización): para más adelante.
"""
from datetime import date

from renta_fija.calculadoras import cer_cupon, motor

BASE = 365


def pago_final(cupon: float, emision: date, vencimiento: date) -> float:
    """Lo que paga una Lecap/Boncap al vencimiento, por 100 VN, según sus condiciones de emisión."""
    return 100 * (1 + cupon) ** (motor.dias_30_360(emision, vencimiento) / 30)


def calcular_capitalizable(precio: float, pago_final_: float, liquidacion: date, vencimiento: date) -> dict:
    plazo = (vencimiento - liquidacion).days
    if precio <= 0 or plazo <= 0:
        raise ValueError("El precio y el plazo residual tienen que ser positivos.")
    tna = (pago_final_ / precio - 1) * BASE / plazo
    return {
        "pago_final": pago_final_,
        "plazo_residual": plazo,
        "meses_al_vencimiento": motor.dias_30_360(liquidacion, vencimiento) / 30,
        "duration": plazo / BASE,
        "tna": tna,
        "tea": (1 + tna * plazo / BASE) ** (BASE / plazo) - 1,
        "tem": (pago_final_ / precio) ** (30 / plazo) - 1,
    }


def calcular_cupon(precio: float, liquidacion: date, pagos: list[dict], tasa: float, frecuencia: int,
                   emision: date, ajustar_fecha) -> dict:
    """Bono a tasa fija con cupón y amortización: la calculadora con cupón, sin CER (ratio = 1)."""
    r = cer_cupon.calcular(precio, 1.0, 1.0, liquidacion, pagos, tasa, frecuencia, emision, ajustar_fecha)
    return {k: v for k, v in r.items()
            if k not in ("ratio", "precio_clean_nominal", "precio_dirty_real", "precio_clean_real")} | {
        "precio_dirty": r["precio_dirty_real"], "precio_clean": r["precio_clean_real"]}
