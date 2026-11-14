"""Curva teórica de tasa fija: TEA = a + b × ln(duration), ajustada por mínimos cuadrados.

Lectura (Agustin, 14/11/2026): estar por encima o por debajo de la curva no dice por sí solo que un bono esté
barato o caro; sirve para comparar bonos de plazos parecidos. Por eso, además del desvío contra la curva, se
compara cada bono con sus vecinos de plazo (el anterior y el siguiente).
Funciones puras.
"""
import math


def ajustar_log(puntos: list[tuple[float, float]]) -> dict:
    """puntos: [(duration en años, TEA)]. Devuelve a, b y el R² del ajuste."""
    if len(puntos) < 3:
        raise ValueError("Hacen falta al menos 3 bonos para ajustar la curva.")
    xs = [math.log(d) for d, _ in puntos]
    ys = [y for _, y in puntos]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        raise ValueError("Todos los bonos tienen la misma duration.")
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (a + b * x)) ** 2 for x, y in zip(xs, ys))
    return {"a": a, "b": b, "r2": 1 - ss_res / ss_tot if ss_tot else 1.0}


def tea_teorica(ajuste: dict, duration: float) -> float:
    return ajuste["a"] + ajuste["b"] * math.log(duration)


def desvios(bonos: list[dict], ajuste: dict) -> list[dict]:
    """bonos: [{ticker, duration, tea, ...}]. Agrega la TEA de la curva, el desvío en pb y la comparación con
    los vecinos de plazo: cuánto más (o menos) se desvía que el anterior y que el siguiente."""
    ordenados = sorted(bonos, key=lambda b: b["duration"])
    filas = [dict(b, tea_curva=tea_teorica(ajuste, b["duration"]),
                  desvio_pb=(b["tea"] - tea_teorica(ajuste, b["duration"])) * 10000) for b in ordenados]
    for i, f in enumerate(filas):
        f["vecinos"] = [(v["ticker"], f["desvio_pb"] - v["desvio_pb"], (v["duration"] - f["duration"]) * 365)
                        for v in (filas[i - 1] if i > 0 else None, filas[i + 1] if i + 1 < len(filas) else None) if v]
    return filas
