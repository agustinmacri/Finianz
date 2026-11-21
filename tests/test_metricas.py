"""Pruebas de renta_fija/metricas.py: precio → tasa y tasa → precio (ida y vuelta), con bonos que no necesitan datos
de afuera (Lecap y Bonares/Globales). Correr con:
    python -m tests.test_metricas
"""
from datetime import date

from renta_fija import leer_fichas
from renta_fija import mercado, metricas

LIQUIDACION = date(2026, 11, 17)
# Sin base de feriados (datos/ puede no existir): las fechas de pago no se corren. No cambia la ida y vuelta.
mercado.feriados.proximo_dia_habil = lambda d, calendario=None: d


def _ida_y_vuelta(f: dict, precio: float):
    ticker = f["ticker"]
    calc = metricas.calculadora(f, LIQUIDACION, LIQUIDACION)
    m = calc(precio)
    for campo in ("tea", "tna"):
        assert abs(metricas.precio_para(calc, m[campo], campo, referencia=precio) - precio) < 1e-6, (ticker, campo)
    return m


def test_lecap():
    lecap = next(f for f in leer_fichas.todas() if f["familia"] == "tasa_fija_capitalizable"
                 and f["vencimiento"] > LIQUIDACION and "DUAL" not in f.get("tipo", "").upper())
    m = _ida_y_vuelta(lecap, 101.0)
    plazo = (lecap["vencimiento"] - LIQUIDACION).days
    assert abs((1 + m["tna"] * plazo / 365) ** (365 / plazo) - 1 - m["tea"]) < 1e-12      # TNA simple al vencimiento
    assert m["curva"] == "tasa_fija" and m["duration"] > 0


def test_hard_dollar():
    m = _ida_y_vuelta(leer_fichas.ficha("GD30"), 80.0)
    assert m["curva"] == "hd" and abs((1 + m["tna"] / 2) ** 2 - 1 - m["tea"]) < 1e-12         # TNA semestral


def test_tasa_imposible():
    f = leer_fichas.ficha("GD30")
    calc = metricas.calculadora(f, LIQUIDACION, LIQUIDACION)
    try:
        metricas.precio_para(calc, -1.5, "tea")         # menos de -100%: imposible
    except ValueError as e:
        assert "no hay un precio" in str(e) or "no converge" in str(e)
    else:
        raise AssertionError("debería fallar")


if __name__ == "__main__":
    for prueba in (test_lecap, test_hard_dollar, test_tasa_imposible):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de métricas pasaron.")
