"""Bonos a tasa TAMAR capitalizables: Bonos TAMAR del Tesoro (TMF27, TMG27...) y la pata TAMAR de los
duales (TTD26 contra tasa fija; TXM contra CER, que también se calculan como CER).

Definiciones de Agustin (docs/convenciones-renta-fija.md), tomadas de su planilla de TAMAR
(13/11/2026). Todo por cada 100 de valor nominal original, en T+1.

- TAMAR del bono: promedio simple de la TAMAR de bancos privados (% TNA) de los días hábiles entre
  el 10.º día hábil anterior a la emisión y el 10.º anterior al vencimiento. Los días todavía no
  publicados se estiman con el promedio simple de los últimos 5 días hábiles publicados.
- TEM del bono (condiciones de emisión): ((1 + (TAMAR + margen) × 32/365) ^ (365/32)) ^ (1/12) − 1.
- Pago final = 100 × (1 + TEM) ^ (días 30/360 entre emisión y vencimiento / 30).
- Desde el precio, como una Lecap: TNA, TEA (TIR), TEM de 30 días y duration = plazo / 365.
- TNA 30 d = ((1 + TIR) ^ (30/365) − 1) × 365/30.
- Spread sobre TAMAR = TNA 30 d − promedio de los últimos 5 días hábiles publicados de TAMAR (la TAMAR
  es una tasa a 30 días, por eso se compara con la TNA de 30 días y no con la del plazo).

Funciones puras: las TAMAR publicadas y los días hábiles los recibe el que llama.
"""
from datetime import date

from renta_fija.calculadoras import motor, tasa_fija

DIAS_TAMAR = 32          # la TEM se arma capitalizando la TNA cada 32 días (condiciones de emisión)
REZAGO_HABILES = 10      # la ventana de la TAMAR empieza y termina 10 días hábiles antes de la emisión y el vencimiento
DIAS_ESTIMACION = 5      # la TAMAR por publicar se estima con el promedio de los últimos 5 días hábiles


def tamar_del_bono(conocidas: list[float], dias_a_estimar: int, estimacion: float) -> float:
    """Promedio simple de la ventana: las TAMAR publicadas más los días que faltan, a la estimación."""
    n = len(conocidas) + dias_a_estimar
    if n == 0:
        raise ValueError("La ventana de la TAMAR no tiene días hábiles.")
    return (sum(conocidas) + dias_a_estimar * estimacion) / n


def tem(tamar: float, margen: float) -> float:
    """TEM del bono según sus condiciones de emisión (tasas en fracción: 0.24 = 24%)."""
    return ((1 + (tamar + margen) * DIAS_TAMAR / 365) ** (365 / DIAS_TAMAR)) ** (1 / 12) - 1


def pago_final(tem_: float, emision: date, vencimiento: date) -> float:
    return 100 * (1 + tem_) ** (motor.dias_30_360(emision, vencimiento) / 30)


def calcular(precio: float, tamar_bono: float, margen: float, emision: date, vencimiento: date,
             liquidacion: date, tamar_referencia: float) -> dict:
    """Todas las variables de un bono TAMAR capitalizable.

    tamar_bono: TAMAR promedio de la ventana (con la parte estimada). tamar_referencia: promedio de los
    últimos 5 días hábiles publicados, para el spread.
    """
    tem_bono = tem(tamar_bono, margen)
    pf = pago_final(tem_bono, emision, vencimiento)
    r = tasa_fija.calcular_capitalizable(precio, pf, liquidacion, vencimiento)
    tna_30 = motor.tna_equivalente(r["tea"], 30)
    return {
        "tamar_bono": tamar_bono,
        "margen": margen,
        "tem_bono": tem_bono,
        "pago_final": pf,
        "plazo_residual": r["plazo_residual"],
        "duration": r["duration"],
        "tna": r["tna"],
        "tea": r["tea"],
        "tem_30": r["tem"],
        "tna_30": tna_30,
        "tna_semestral": motor.tna_semestral(r["tea"]),
        "tamar_referencia": tamar_referencia,
        "spread": tna_30 - tamar_referencia,
    }
