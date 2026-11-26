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


def test_al_anterior():
    bonos = [{"ticker": "C", "vencimiento": date(2027, 11, 26), "tea": 0.27},
             {"ticker": "A", "vencimiento": date(2027, 2, 26), "tea": 0.30},
             {"ticker": "B", "vencimiento": date(2027, 5, 26), "tea": 0.29},
             {"ticker": "B2", "vencimiento": date(2027, 5, 26), "tea": 0.291}]
    ant = fw.al_anterior(bonos, LIQ)
    _, celdas = fw.matriz(bonos, LIQ)
    assert ant["A"] is None
    assert abs(ant["B"] - celdas[("A", "B")]) < 1e-15 and abs(ant["B2"] - celdas[("A", "B2")]) < 1e-15
    assert abs(ant["C"] - celdas[("B2", "C")]) < 1e-15                 # el anterior de C es el último de mayo


def test_exit_yield():
    from renta_fija.calculadoras import exit_yield as ey
    # Bono cupón cero a 1 año que paga 130: hoy rinde 30%
    flujos = [{"fecha": date(2027, 11, 26), "total": 130.0}]
    r = ey.retorno(flujos, 0.30, LIQ, date(2027, 5, 26), 0.30)          # sale a la misma TIR: rinde la TIR
    assert abs(r["precio_hoy"] - 100) < 1e-9 and abs(r["anualizado"] - 0.30) < 1e-12
    r2 = ey.retorno(flujos, 0.30, LIQ, date(2027, 5, 26), 0.25)          # sale a una TIR menor: rinde más
    plazo_resto = (date(2027, 11, 26) - date(2027, 5, 26)).days / 365
    assert abs(r2["precio_salida"] - 130 / 1.25 ** plazo_resto) < 1e-9 and r2["anualizado"] > 0.30
    # Con cupones reinvertidos a la TIR de salida, si es igual a la de hoy también rinde la TIR
    con_cupon = [{"fecha": date(2027, 2, 26), "total": 10.0}, {"fecha": date(2027, 8, 26), "total": 10.0},
                 {"fecha": date(2028, 2, 26), "total": 110.0}]
    r3 = ey.retorno(con_cupon, 0.20, LIQ, date(2027, 11, 26), 0.20)
    assert abs(r3["anualizado"] - 0.20) < 1e-12 and r3["cobrado_nominal"] == 20.0
    # Vence antes de la salida: se cobra todo y se reinvierte
    r4 = ey.retorno(flujos, 0.30, LIQ, date(2028, 5, 26), 0.30)
    assert r4["vence_antes"] and r4["precio_salida"] == 0 and abs(r4["anualizado"] - 0.30) < 1e-12
    sens = ey.sensibilidad(flujos, 0.30, LIQ, date(2027, 5, 26), 0.30)
    assert [s["pb"] for s in sens][0] == -200 and sens[0]["retorno"] > sens[-1]["retorno"]


if __name__ == "__main__":
    for prueba in (test_ecuacion, test_siguiente_y_matriz, test_al_anterior, test_exit_yield):
        prueba()
        print(f"OK {prueba.__name__}")
