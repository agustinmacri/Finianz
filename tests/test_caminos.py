"""Pruebas de la tabla de caminos (usado contra breakeven y REM), con caminos inventados: no usa la base ni precios.
Correr con:
    python -m tests.test_caminos
"""
from tools import caminos as tc


def test_meses_hasta_diciembre_del_anio_siguiente_y_despues_anios():
    usada = lambda mes: 0.02
    breakeven = lambda mes: 0.018 if mes <= (2027, 3) else 0.017
    rem = lambda mes: None if mes > (2028, 12) else 0.015
    publicadas = {(2026, m): 0.025 for m in range(1, 11)}
    desde, hasta = (2026, 11), (2029, 6)
    columnas = [tc.Columna("usada", usada, tc.inflacion_anual(usada, publicadas, desde)),
                tc.Columna("breakeven", breakeven, tc.inflacion_anual(breakeven, publicadas, desde),
                           extendido=lambda mes: mes > (2027, 3)),
                tc.Columna("REM", rem, tc.inflacion_anual(rem, publicadas, desde))]
    lineas = tc.tabla("Mes", columnas, desde, hasta, 2026)
    meses = [l.split(" | ")[0] for l in lineas[1:] if "-" in l.split(" | ")[0]]
    assert meses[0] == "nov-26" and meses[-1] == "dic-27" and len(meses) == 14          # mensual hasta dic del año que viene
    assert "ene-27 | 2.00% | 1.80% | 1.50%" in lineas
    assert "abr-27 | 2.00% | 1.70%* | 1.50%" in lineas                                  # breakeven extendido
    anios = [l for l in lineas if l[:4].isdigit()]
    assert [l.split(" | ")[0] for l in anios] == ["2026", "2027", "2028", "2029 (hasta jun)"]
    # 2026: diez meses publicados al 2,5% y dos del camino al 2%
    assert anios[0].split(" | ")[1] == tc.pct(1.025 ** 10 * 1.02 ** 2 - 1)
    assert anios[1].split(" | ")[2].endswith("*")                                     # el año tiene meses extendidos
    assert anios[3].split(" | ")[3] == "–"                                             # el REM no llega a 2029
    assert abs(tc.acumulado(usada, (2026, 11), (2027, 10)) - (1.02 ** 12 - 1)) < 1e-12
    assert tc.acumulado(rem, (2026, 11), (2029, 6)) is None


def test_promedio_y_formato_de_niveles():
    tamar = lambda mes: 0.30 if mes < (2027, 1) else 0.24
    assert abs(tc.promedio(tamar)(2027, (2027, 1), (2027, 6)) - 0.24) < 1e-12
    assert abs(tc.promedio(tamar)(2026, (2026, 11), (2026, 12)) - 0.30) < 1e-12
    columnas = [tc.Columna("usada", lambda mes: (1500.0, 0.015), lambda a, p, u: (1600.0, 0.2))]
    formato = lambda x: "–" if x is None else f"{tc.pesos(x[0])} ({tc.pct(x[1], 1)})"
    lineas = tc.tabla("Mes", columnas, (2026, 11), (2026, 12), 2026, formato=formato)
    assert lineas[1] == "nov-26 | 1,500.00 (1.5%)" and lineas[-1] == "2026 | 1,600.00 (20.0%)"


if __name__ == "__main__":
    for prueba in (test_meses_hasta_diciembre_del_anio_siguiente_y_despues_anios, test_promedio_y_formato_de_niveles):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de la tabla de caminos pasaron.")
