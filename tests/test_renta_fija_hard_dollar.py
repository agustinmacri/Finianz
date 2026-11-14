"""Pruebas de la calculadora de bonos en dólares (AL30 y GD30).

Todavía no hay planilla de Agustin para contrastar: se verifican el cronograma contra las condiciones
de emisión (cupones step-up y amortizaciones publicados) y cada indicador contra su fórmula escrita aparte.
Correr con:
    python -m tests.test_renta_fija_hard_dollar
"""
from datetime import date

from renta_fija import leer_fichas
from renta_fija.calculadoras import hard_dollar, motor

LIQUIDACION = date(2026, 11, 16)
PRECIO = 61.5                         # USD por 100 VN original, con cupón corrido (ejemplo)


def _sin_ajuste(d):
    return d


def test_cronograma_al30():
    f = leer_fichas.ficha("AL30")
    filas = hard_dollar.cronograma(f["pagos"], f["tramos"], f["emision"])
    rentas = {r["fecha"].isoformat(): round(r["renta"], 6) for r in filas}
    assert rentas["2021-07-09"] == round(100 * 0.00125 * 305 / 360, 6)    # primer cupón: 4/9/2020 a 9/7/2021
    assert rentas["2022-01-09"] == 0.25 and rentas["2024-01-09"] == 0.375
    assert rentas["2026-01-09"] == 0.30 and rentas["2026-07-09"] == 0.27
    assert rentas["2028-01-09"] == 0.42 and rentas["2030-07-09"] == 0.07   # step-up a 1,75% desde 9/7/2027
    assert sum(r["amortizacion"] for r in filas) == 100
    assert leer_fichas.ficha("GD30")["pagos"] == f["pagos"] and leer_fichas.ficha("GD30")["tramos"] == f["tramos"]


def test_cronogramas_de_todos():
    """Cupones de enero y julio de 2026 (conocidos) y amortización total de cada bono."""
    esperados = {   # ticker: (cupón 9/1/2026, cupón 9/7/2026, último pago)
        "AL29": (0.40, 0.35, "2029-07-09"), "AL35": (2.0625, 2.0625, "2035-07-09"), "AE38": (2.5, 2.5, "2038-01-09"),
        "AL41": (1.75, 1.75, "2041-07-09"), "GD46": (1.96875, 1.921875, "2046-07-09"),
    }
    for ticker, (ene, jul, ultimo) in esperados.items():
        f = leer_fichas.ficha(ticker)
        filas = {r["fecha"].isoformat(): r for r in hard_dollar.cronograma(f["pagos"], f["tramos"], f["emision"])}
        assert abs(filas["2026-01-09"]["renta"] - ene) < 1e-9 and abs(filas["2026-07-09"]["renta"] - jul) < 1e-9, ticker
        assert f["vencimiento"].isoformat() == ultimo and abs(sum(r["amortizacion"] for r in filas.values()) - 100) < 1e-9
        if f.get("par"):                                   # el Bonar y el Global del mismo año son iguales
            otro = leer_fichas.ficha(f["par"])
            assert otro["pagos"] == f["pagos"] and otro["tramos"] == f["tramos"] and otro["par"] == ticker
    assert "par" not in leer_fichas.ficha("GD46")


def test_indicadores():
    f = leer_fichas.ficha("GD30")
    r = hard_dollar.calcular(PRECIO, LIQUIDACION, f["pagos"], f["tramos"], f["emision"], _sin_ajuste)
    assert r["residual"] == 64 and r["tasa_vigente"] == 0.0075
    assert abs(r["interes_corrido"] - 64 * 0.0075 * 127 / 360) < 1e-12           # 9/7 al 16/11: 127 días 30/360
    assert abs(r["precio_clean"] - (PRECIO - r["interes_corrido"])) < 1e-12
    assert abs(r["precio_clean_residual"] - (PRECIO - r["interes_corrido"]) / 0.64) < 1e-12   # por 100 de residual
    assert abs(r["paridad"] - PRECIO / (64 + r["interes_corrido"])) < 1e-12
    y = r["tir"]
    n = [(motor.dias_30_360(LIQUIDACION, fl.fecha) / 180, fl.total) for fl in r["flujos"]]
    vp = sum(m / (1 + y / 2) ** k for k, m in n)
    assert abs(vp - PRECIO) < 1e-8                                                # precio = VP a la TIR semestral
    assert abs(r["tea"] - ((1 + y / 2) ** 2 - 1)) < 1e-15
    dur = sum(k / 2 * m / (1 + y / 2) ** k for k, m in n) / vp
    assert abs(r["duration"] - dur) < 1e-10
    assert abs(r["duration_modificada"] - dur / (1 + y / 2)) < 1e-10
    assert abs(r["current_yield"] - 0.0075 * 64 / r["precio_clean"]) < 1e-15
    caja = (0.24 + 8) + (0.21 + 8)                                               # 9/1/2027 y 9/7/2027
    assert abs(r["cash_yield"] - caja / r["precio_clean"]) < 1e-12
    # la duration modificada aproxima la variación del precio ante 1 pb
    sube = sum(m / (1 + (y + 0.0001) / 2) ** k for k, m in n)
    assert abs((sube - vp) / vp + r["duration_modificada"] * 0.0001) < 1e-6


def test_interpolar():
    curva = [(1, 0.04), (2, 0.05), (5, 0.06)]
    assert hard_dollar.interpolar(curva, 1.5) == 0.045
    assert abs(hard_dollar.interpolar(curva, 3.5) - 0.055) < 1e-15
    assert hard_dollar.interpolar(curva, 0.5) == 0.04 and hard_dollar.interpolar(curva, 30) == 0.06


def test_herramienta():
    """La herramienta con precios y Treasuries inventados (sin conexión)."""
    from tools import bonos
    precios = {"AL30D": 60.0, "AL30C": 60.5, "GD30D": 62.0, "GD30C": 62.4, "AL30": 87000.0}
    originales = bonos._precio, bonos._treasuries
    bonos._precio = lambda t, fecha: (precios[t.upper()], "prueba")
    bonos._treasuries = lambda fecha: ([(1, 0.04), (2, 0.039), (3, 0.0385), (5, 0.039)], "2026-11-12")
    try:
        texto = bonos.calcular_bono("AL30D", fecha=None)
        assert "Con precio MEP (AL30D)" in texto and "Con precio cable (AL30C)" in texto
        assert "Spread contra Treasuries" in texto and "Spread ley NY − ley AR" in texto
        assert "TNA (semestral 30/360)" in texto and "TIR (TEA)" in texto and "Precio clean (por 100 de residual)" in texto
        assert "MEP: 1,450.00" in texto and "CCL: 1,438.02" in texto
        assert "AVISO" not in texto                                   # AL30 y GD30 ya validados
        precios.update({"GD46D": 70.0, "GD46C": 70.3, "GD46": 101000.0})
        gd46 = bonos.calcular_bono("GD46")
        assert "Spread ley" not in gd46 and "AVISO" in gd46           # sin par de ley argentina; ficha por revisar
        solo = bonos.calcular_bono("GD30", precio=62.0)
        assert "Con precio MEP (indicado)" in solo and "cable" not in solo
    finally:
        bonos._precio, bonos._treasuries = originales


if __name__ == "__main__":
    for prueba in (test_cronograma_al30, test_cronogramas_de_todos, test_indicadores, test_interpolar, test_herramienta):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de hard dollar pasaron.")
