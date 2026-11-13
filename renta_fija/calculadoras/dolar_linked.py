"""Bonos dollar linked: valor nominal en dólares, se suscriben, cotizan y pagan en pesos al tipo de cambio.

Definiciones de Agustin (13/11/2026; docs/convenciones-renta-fija.md):
- Precio en dólares = precio en pesos (por 100 VN) / A3500 del día de concertación de la operación.
  Intradiario, mientras no se publica (a las 15 h), se estima con el A3500 del día hábil anterior.
- Bullet (los del Tesoro): al vencimiento pagan 100 dólares por 100 VN, en pesos al tipo de cambio de
  pago que fija el prospecto. En dólares, el flujo es 100.
- Convención actual/365 (distinta de los hard dollar):
  TNA = (100 / precio en dólares − 1) × 365 / plazo residual; TIR = (1 + TNA × plazo/365)^(365/plazo) − 1;
  duration = plazo / 365; TEM de 30 días corridos.
- Con cupones y amortizaciones (corporativos): para más adelante.

Funciones puras: el precio y el tipo de cambio los recibe el que llama.
"""
from datetime import date

from renta_fija.calculadoras import tasa_fija

PAGO_FINAL_USD = 100.0


def calcular_bullet(precio_pesos: float, tipo_cambio: float, liquidacion: date, vencimiento: date) -> dict:
    if tipo_cambio <= 0:
        raise ValueError("El tipo de cambio tiene que ser positivo.")
    precio_usd = precio_pesos / tipo_cambio
    r = tasa_fija.calcular_capitalizable(precio_usd, PAGO_FINAL_USD, liquidacion, vencimiento)
    return {"precio_usd": precio_usd, "tipo_cambio": tipo_cambio, **{k: v for k, v in r.items() if k != "pago_final"}}
