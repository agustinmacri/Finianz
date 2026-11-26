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


def test_cer_con_cer_final_conocido():
    """CER con el CER final publicado: pago fijo en pesos y curva de tasa fija (Agustin, 26/11/2026)."""
    f = next(x for x in leer_fichas.todas() if x["familia"] == "cer_cero_cupon" and x["vencimiento"] > LIQUIDACION)
    originales = mercado.datos_cer, mercado.cer_final_conocido
    mercado.datos_cer = lambda ficha, liq: ("", dict(ficha, cer_inicial=200.0), 250.0)
    try:
        mercado.cer_final_conocido = lambda fecha: None            # todavía no se conoce: curva CER, TEA real
        m = metricas.calculadora(f, LIQUIDACION, LIQUIDACION)(120.0)
        assert m["curva"] == "cer" and not m.get("cer_conocido")
        mercado.cer_final_conocido = lambda fecha: 260.0           # ya publicado
        m = _ida_y_vuelta(f, 128.0)
        plazo = (f["vencimiento"] - LIQUIDACION).days
        pago = 100 * 260 / 200
        assert m["curva"] == "tasa_fija" and m["cer_conocido"] and m["ajuste"] is None
        assert abs(m["tea"] - ((pago / 128) ** (365 / plazo) - 1)) < 1e-12
        assert abs(m["flujos"][-1]["total"] - pago) < 1e-9 and abs(m["extra"]["pago_final"] - pago) < 1e-9
        assert "tea_real" in m["detalle"]
    finally:
        mercado.datos_cer, mercado.cer_final_conocido = originales


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
    for prueba in (test_lecap, test_hard_dollar, test_cer_con_cer_final_conocido, test_tasa_imposible):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de métricas pasaron.")
