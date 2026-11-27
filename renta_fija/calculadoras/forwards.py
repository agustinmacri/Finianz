"""Tasas forward entre bonos de una misma curva (funciones puras).

Definición (Agustin, 25/11/2026): la forward es la tasa que iguala comprar el bono largo con comprar el corto y, a su
vencimiento, renovarlo hasta el vencimiento del largo:

    (1 + r_largo)^t_largo = (1 + r_corto)^t_corto · (1 + f)^(t_largo − t_corto)
    f = [(1 + r_largo)^t_largo / (1 + r_corto)^t_corto]^(1 / (t_largo − t_corto)) − 1

r = TIR (TEA base 365) de cada bono a su precio; t = años desde la liquidación hasta el vencimiento (días / 365).
En la curva CER, r es la TIR real y f es una forward real. Para bonos con cupones es la aproximación con la TIR de cada
bono (la forward exacta entre fechas sale de descontar flujo por flujo; queda para la etapa de exit yield).
"""
from datetime import date


def tasa_forward(r_corto: float, t_corto: float, r_largo: float, t_largo: float) -> float | None:
    """Forward (TEA) entre el vencimiento del corto y el del largo. None si no hay plazo entre ambos."""
    if t_largo - t_corto <= 1e-9 or t_corto < 0:
        return None
    return ((1 + r_largo) ** t_largo / (1 + r_corto) ** t_corto) ** (1 / (t_largo - t_corto)) - 1


def _plazos(bonos: list[dict], liquidacion: date) -> list[dict]:
    """bonos: [{"ticker", "vencimiento", "tea"}] -> ordenados por vencimiento, con t en años."""
    return sorted(({**b, "t": (b["vencimiento"] - liquidacion).days / 365} for b in bonos if b.get("tea") is not None),
                  key=lambda b: (b["vencimiento"], b["ticker"]))


def al_anterior(bonos: list[dict], liquidacion: date) -> dict[str, float | None]:
    """Para cada bono, la forward desde el vencimiento anterior de la curva hasta el suyo (decisión de Agustin,
    26/11/2026: la columna de forwards de cada bono es contra el anterior). El más corto queda en None; los que
    vencen el mismo día que otro usan el vencimiento anterior distinto."""
    ordenados = _plazos(bonos, liquidacion)
    salida = {}
    for i, largo in enumerate(ordenados):
        corto = next((b for b in reversed(ordenados[:i]) if b["vencimiento"] < largo["vencimiento"]), None)
        salida[largo["ticker"]] = tasa_forward(corto["tea"], corto["t"], largo["tea"], largo["t"]) if corto else None
    return salida


def matriz(bonos: list[dict], liquidacion: date) -> tuple[list[str], dict[tuple[str, str], float]]:
    """Forward entre cada par (corto, largo) con el largo venciendo después: (tickers ordenados, {(corto, largo): f})."""
    ordenados = _plazos(bonos, liquidacion)
    celdas = {}
    for i, corto in enumerate(ordenados):
        for largo in ordenados[i + 1:]:
            f = tasa_forward(corto["tea"], corto["t"], largo["tea"], largo["t"])
            if f is not None:
                celdas[(corto["ticker"], largo["ticker"])] = f
    return [b["ticker"] for b in ordenados], celdas
