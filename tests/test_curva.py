"""Pruebas de la curva teórica de tasa fija.
Correr con:
    python -m tests.test_curva
"""
import math

from renta_fija.calculadoras import curva


def test_ajuste_exacto_y_desvios():
    """Puntos sobre una curva conocida: el ajuste la recupera; un bono corrido 50 pb muestra el desvío."""
    a, b = 0.35, -0.03
    bonos = [{"ticker": f"S{i}", "duration": d, "tea": a + b * math.log(d)} for i, d in enumerate((0.1, 0.3, 0.6, 1.0, 1.5))]
    ajuste = curva.ajustar_log([(x["duration"], x["tea"]) for x in bonos])
    assert abs(ajuste["a"] - a) < 1e-12 and abs(ajuste["b"] - b) < 1e-12 and abs(ajuste["r2"] - 1) < 1e-12
    bonos[2]["tea"] += 0.005
    filas = curva.desvios(bonos, ajuste)
    medio = next(f for f in filas if f["ticker"] == "S2")
    assert abs(medio["desvio_pb"] - 50) < 1e-6
    assert [v[0] for v in medio["vecinos"]] == ["S1", "S3"] and abs(medio["vecinos"][0][1] - 50) < 1e-6
    assert len(filas[0]["vecinos"]) == 1                                          # el más corto tiene un solo vecino


def test_minimo_de_bonos():
    try:
        curva.ajustar_log([(0.1, 0.3), (0.5, 0.28)])
        raise AssertionError("tenía que pedir al menos 3 bonos")
    except ValueError:
        pass


if __name__ == "__main__":
    for prueba in (test_ajuste_exacto_y_desvios, test_minimo_de_bonos):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de la curva pasaron.")
