"""Pruebas del panel web: la lectura de las salidas de texto de las herramientas (sin abrir el panel).
Correr con:
    python -m tests.test_web
"""
from web import salidas

TEXTO = """Proyección del CER – calculadora de Finianz
Inflación mensual:
Mes | usada (breakeven) | REM
nov-26 | 0.79% | 1.70%
dic-26 | 1.82%* | –
Año (dic/dic) | usada (breakeven) | REM
2026 | 30.10% | 29.90%
Acumulada nov-26 a dic-26: usada 2.62% | REM 3.57%

Inflación implícita (CER vs tasa fija)
Bono | vence | días | TEA CER (real)
X30N6 | 2026-11-30 | 13 | 6.00%
TZXD7 | 2027-12-15 | 393 | fuera del rango
Bono | vence | días | TEA DL (USD)
"""


def test_bloques():
    b = salidas.bloques(TEXTO)
    tipos = [t for t, _ in b]
    assert tipos == ["texto", "tabla", "tabla", "texto", "texto", "tabla", "texto"], tipos
    meses, anios, bonos = b[1][1], b[2][1], b[5][1]
    assert list(meses.columns) == ["Mes", "usada (breakeven)", "REM"] and len(meses) == 2
    assert anios.columns[0] == "Año (dic/dic)" and anios.iloc[0, 1] == "30.10%"
    assert b[4][1] == "Inflación implícita (CER vs tasa fija)"                      # el título queda solo
    assert bonos.iloc[1].tolist() == ["TZXD7", "2027-12-15", "393", "fuera del rango"]
    assert b[6][1] == "_(sin bonos para comparar en este cruce)_"                    # tabla sin filas


def test_numeros_y_camino():
    assert salidas.numero("2.15%") == 0.0215 and salidas.numero("1.82%*") == 0.0182
    assert salidas.numero("1,500.00 (+1.5%)") == 1500.0 and salidas.numero("–") is None
    assert salidas.numero("-0.12 pp") == -0.12
    camino = salidas.tabla_de_meses(TEXTO)
    assert list(camino.index) == ["nov-26", "dic-26"] and camino.loc["dic-26", "REM"] is None or \
        camino.loc["dic-26", "REM"] != camino.loc["dic-26", "REM"]                    # sin dato: vacío
    assert abs(camino.loc["nov-26", "usada (breakeven)"] - 0.0079) < 1e-12


if __name__ == "__main__":
    for prueba in (test_bloques, test_numeros_y_camino):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas del panel web pasaron.")
