"""Bonos y letras ajustados por CER que no pagan intereses ni amortizaciones (Boncer cero cupón, LeCER).

Definiciones de Agustin (docs/convenciones-renta-fija.md). Se implementan tal cual:
- Los precios y los cálculos se hacen en T+1 (liquidación), salvo que se indique otra cosa.
- Plazo residual = días corridos entre la liquidación y el vencimiento.
- Duration = plazo residual / 365.
- CER final = CER del décimo día hábil anterior al vencimiento.
- CER inicial (base) = CER del décimo día hábil anterior a la liquidación inicial del bono (dato de la ficha).
- CER corriente = CER del décimo día hábil anterior a la liquidación de la operación
  (operación del 12/11/26 → liquidación 13/11/26 → CER del 28/10/26: el 9/11 y el 10/11 fueron feriados).
- Días hábiles: calendario de BYMA.
- Ratio = CER corriente / CER inicial (por 100 de valor nominal, como el precio).
- TNA real = (ratio / precio − 1) × 365 / plazo residual.
- TIR (TEA real) = capitalización de la TNA por el plazo remanente en base 365:
      (1 + TNA × plazo / 365) ^ (365 / plazo) − 1
- Carry mensual = último dato de inflación mensual conocido + TNA / 12.

Funciones puras: el CER, la inflación y las fechas hábiles los recibe el que llama (tools/bonos.py).
"""
from datetime import date

REZAGO_HABILES = 10      # décimo día hábil anterior (CER inicial, corriente y final)
BASE = 365


def plazo_residual(liquidacion: date, vencimiento: date) -> int:
    return (vencimiento - liquidacion).days


def duration(plazo: int) -> float:
    return plazo / BASE


def ratio(cer_corriente: float, cer_inicial: float) -> float:
    """Ajuste acumulado por CER, por cada 100 de valor nominal."""
    if cer_inicial <= 0:
        raise ValueError("El CER inicial tiene que ser positivo.")
    return cer_corriente / cer_inicial * 100


def tna_real(ratio_actual: float, precio: float, plazo: int) -> float:
    if precio <= 0 or plazo <= 0:
        raise ValueError("El precio y el plazo residual tienen que ser positivos.")
    return (ratio_actual / precio - 1) * BASE / plazo


def tea_real(tna: float, plazo: int) -> float:
    """TIR: la TNA capitalizada por el plazo remanente, en base 365."""
    return (1 + tna * plazo / BASE) ** (BASE / plazo) - 1


def carry_mensual(inflacion_mensual: float, tna: float) -> float:
    """Último dato de inflación mensual (fracción: 0.019 = 1,9%) más la TNA mensualizada."""
    return inflacion_mensual + tna / 12


def calcular(precio: float, cer_inicial: float, cer_corriente: float, liquidacion: date, vencimiento: date,
             inflacion_mensual: float | None = None) -> dict:
    """Todas las variables de un CER cero cupón, con las definiciones de Agustin."""
    plazo = plazo_residual(liquidacion, vencimiento)
    r = ratio(cer_corriente, cer_inicial)
    tna = tna_real(r, precio, plazo)
    return {
        "plazo_residual": plazo,
        "duration": duration(plazo),
        "ratio": r,
        "tna_real": tna,
        "tea_real": tea_real(tna, plazo),
        "carry_mensual": carry_mensual(inflacion_mensual, tna) if inflacion_mensual is not None else None,
    }
