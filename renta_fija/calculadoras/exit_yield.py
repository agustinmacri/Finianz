"""Retorno de un bono si se vende en una fecha a una TIR de salida (exit yield). Funciones puras.

Con los flujos futuros del bono (por 100 VN original, en su unidad: pesos en tasa fija y TAMAR, pesos reales en
CER, dólares en dollar linked y hard dollar):
- Precio hoy en la unidad del bono: valor presente de los flujos a la TIR de hoy (TEA, actual/365 desde la
  liquidación). Así, con una TIR de salida igual a la de hoy, el retorno anualizado es exactamente esa TIR.
- Cobrado hasta la salida: cupones y amortizaciones con fecha entre la liquidación y la salida, reinvertidos hasta
  la salida a la TIR de salida.
- Precio de salida: valor presente, en la fecha de salida, de los flujos posteriores, a la TIR de salida (precio
  dirty teórico, en la unidad del bono).
- Retorno del período = (precio de salida + cobrado reinvertido) / precio hoy − 1; anualizado (TEA) con días / 365.
Si el bono vence antes de la fecha de salida, se cobra todo y se reinvierte a la TIR de salida hasta esa fecha.
"""
from datetime import date


def _descontar(flujos, desde: date, tasa: float) -> float:
    return sum(x["total"] / (1 + tasa) ** ((x["fecha"] - desde).days / 365) for x in flujos)


def retorno(flujos: list[dict], tea_hoy: float, liquidacion: date, salida: date, tea_salida: float) -> dict:
    """flujos: [{"fecha", "total"}] futuros (fecha > liquidación). Devuelve precio hoy y de salida, cobrado y retornos."""
    if salida <= liquidacion:
        raise ValueError("La fecha de salida tiene que ser posterior a la liquidación.")
    futuros = [x for x in flujos if x["fecha"] > liquidacion and x["total"]]
    if not futuros:
        raise ValueError("El bono no tiene flujos futuros.")
    precio_hoy = _descontar(futuros, liquidacion, tea_hoy)
    cobrados = [x for x in futuros if x["fecha"] <= salida]
    restantes = [x for x in futuros if x["fecha"] > salida]
    cobrado = sum(x["total"] * (1 + tea_salida) ** ((salida - x["fecha"]).days / 365) for x in cobrados)
    precio_salida = _descontar(restantes, salida, tea_salida) if restantes else 0.0
    dias = (salida - liquidacion).days
    total = (precio_salida + cobrado) / precio_hoy - 1
    return {"precio_hoy": precio_hoy, "precio_salida": precio_salida, "cobrado": cobrado,
            "cobrado_nominal": sum(x["total"] for x in cobrados), "retorno": total,
            "anualizado": (1 + total) ** (365 / dias) - 1 if total > -1 else None, "dias": dias,
            "vence_antes": not restantes}


def sensibilidad(flujos: list[dict], tea_hoy: float, liquidacion: date, salida: date, tea_salida: float,
                 pasos_pb=(-200, -100, -50, 0, 50, 100, 200)) -> list[dict]:
    """El retorno para TIR de salida alrededor de la elegida (en puntos básicos)."""
    return [{"pb": pb, "tea_salida": tea_salida + pb / 1e4,
             **retorno(flujos, tea_hoy, liquidacion, salida, tea_salida + pb / 1e4)} for pb in pasos_pb]
