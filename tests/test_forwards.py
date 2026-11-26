"""Pruebas de las tasas forward. Correr con: python -m tests.test_forwards"""
from datetime import date

from renta_fija.calculadoras import forwards as fw

LIQ = date(2026, 11, 26)


def test_ecuacion():
    # Invertir en el largo = invertir en el corto y renovar a la forward
    r1, t1, r2, t2 = 0.30, 0.5, 0.28, 1.5
    f = fw.tasa_forward(r1, t1, r2, t2)
    assert abs((1 + r2) ** t2 - (1 + r1) ** t1 * (1 + f) ** (t2 - t1)) < 1e-12
    assert fw.tasa_forward(0.3, 0.5, 0.3, 1.0) - 0.3 < 1e-12          # curva plana: forward = tasa
    assert fw.tasa_forward(0.3, 1.0, 0.3, 1.0) is None                # mismo vencimiento
    assert fw.tasa_forward(0.25, 0.5, 0.30, 1.0) > 0.30               # curva con pendiente positiva: forward arriba


def test_siguiente_y_matriz():
    bonos = [{"ticker": "C", "vencimiento": date(2027, 11, 26), "tea": 0.27},
             {"ticker": "A", "vencimiento": date(2027, 2, 26), "tea": 0.30},
             {"ticker": "B", "vencimiento": date(2027, 5, 26), "tea": 0.29},
             {"ticker": "B2", "vencimiento": date(2027, 5, 26), "tea": 0.291}]
    sig = fw.al_siguiente(bonos, LIQ)
    assert sig["A"][0] == "B" and sig["B"][0] == "C" and sig["B2"][0] == "C" and "C" not in sig
    tickers, celdas = fw.matriz(bonos, LIQ)
    assert tickers == ["A", "B", "B2", "C"]
    assert ("A", "C") in celdas and ("C", "A") not in celdas and ("B", "B2") not in celdas
    t = lambda d: (d - LIQ).days / 365
    esperado = fw.tasa_forward(0.30, t(date(2027, 2, 26)), 0.27, t(date(2027, 11, 26)))
    assert abs(celdas[("A", "C")] - esperado) < 1e-15
    assert abs(sig["A"][1] - celdas[("A", "B")]) < 1e-15


if __name__ == "__main__":
    for prueba in (test_ecuacion, test_siguiente_y_matriz):
        prueba()
        print(f"OK {prueba.__name__}")
