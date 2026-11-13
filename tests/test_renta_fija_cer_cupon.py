"""Pruebas de la calculadora CER con cupón: TX28 contra el Excel de Agustin (ejemplo_tx28.xlsx, 13/11/2026) y TX31 por su norma.

Valores del Excel con las correcciones acordadas: la TIR y sus equivalentes coinciden; la duration,
la duration modificada y la convexidad se comparan contra un cálculo independiente porque el Excel
mezclaba fechas corridas (en la TIR) y sin correr (en la duration).
Correr con:
    python -m tests.test_renta_fija_cer_cupon
"""
from datetime import date, timedelta

from renta_fija import leer_fichas
from renta_fija.calculadoras import cer_cupon

LIQUIDACION = date(2026, 11, 16)          # operación del 13/11/2026, T+1
CER_CORRIENTE = 861.75259534429           # CER BCRA del 29/10/2026 (10.º día hábil anterior)
PRECIO = 1820.0                           # 18,20 por 1 VN en el Excel = 1.820 por 100 VN

EXCEL = {                                 # por 100 VN (el Excel trabaja por 1 VN)
    "ratio": 38.22544645877114,
    "residual": 40.0,
    "interes_corrido": 0.0175,
    "valor_tecnico": 40.0175,
    "precio_dirty_real": 47.612262736108725,
    "precio_clean_nominal": 1819.3310546870396,
    "paridad": 1.1897860370115256,
    "tir_real": -0.1112061519175768,
    "tna_semestral": ((1 - 0.1112061519175768) ** 0.5 - 1) * 2,   # TNA semestral exacta (decisión del 13/11/2026)
    "tna_30": -0.11732065010313024,
    "tem": -0.009642793159161389,
}


def _ajustar(d: date) -> date:
    """Fechas de pago corridas: en estas fechas solo hay fines de semana (sin feriados)."""
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _resultado():
    f = leer_fichas.ficha("TX28")
    return cer_cupon.calcular(PRECIO, f["cer_inicial"], CER_CORRIENTE, LIQUIDACION, f["pagos"], f["cupon"],
                              f["frecuencia"], f["emision"], _ajustar)


def test_como_el_excel():
    r = _resultado()
    for clave, esperado in EXCEL.items():
        tolerancia = 1e-8 if clave in ("tir_real", "tna_semestral", "tna_30", "tem") else 1e-9   # precisión del XIRR
        assert abs(r[clave] - esperado) <= tolerancia * max(1, abs(esperado)), (clave, r[clave], esperado)


def test_duration_y_convexidad_independientes():
    """Recalculadas a mano con las fechas corridas y la TIR del motor."""
    r = _resultado()
    t = [((f.fecha - LIQUIDACION).days / 365, f.total) for f in r["flujos"]]
    y, p = r["tir_real"], r["precio_dirty_real"]
    dur = sum(ti * m / (1 + y) ** ti for ti, m in t) / p
    cvx = sum(ti * (ti + 1) * m / (1 + y) ** (ti + 2) for ti, m in t) / p
    assert abs(r["duration"] - dur) < 1e-6 and abs(r["convexidad"] - cvx) < 1e-6
    assert abs(r["duration_modificada"] - dur / (1 + y)) < 1e-6


def test_current_y_cash_yield():
    r = _resultado()
    clean = EXCEL["precio_dirty_real"] - EXCEL["interes_corrido"]
    assert abs(r["current_yield"] - 0.0225 * 40 / clean) < 1e-12               # cupón actual / clean
    assert abs(r["cash_yield"] - (10.45 + 10.3375) / clean) < 1e-12           # may-27 y nov-27


def test_flujos():
    r = _resultado()
    assert [(f.fecha.isoformat(), round(f.total, 4)) for f in r["flujos"]] == [
        ("2027-05-10", 10.45), ("2027-11-09", 10.3375), ("2028-05-09", 10.225), ("2028-11-09", 10.1125)]


def test_tx31_estructura():
    """TX31 según su norma: sin amortizaciones hasta mayo 2027, 10 cuotas de 10%, cupón 2,5% semestral 30/360.

    Sin valores de contraste todavía: verifica el cronograma, el corrido y las fechas corridas.
    """
    from admin_datos import feriados
    from carga_datos import feriados as carga
    if not feriados.rango_cargado() or feriados.rango_cargado()[1] < 2031:
        carga.cargar()
    f = leer_fichas.ficha("TX31")
    r = cer_cupon.calcular(100.0, 1.0, 1.0, LIQUIDACION, f["pagos"], f["cupon"], f["frecuencia"], f["emision"],
                           lambda d: feriados.proximo_dia_habil(d, "BYMA"))
    assert r["residual"] == 100
    assert abs(r["interes_corrido"] - 100 * 0.025 * 166 / 360) < 1e-12        # 30/05/2026 → 16/11/2026: 166 días 30/360
    assert len(r["flujos"]) == 11                                             # nov-26 ... nov-31
    assert r["flujos"][0].fecha == date(2026, 11, 30) and r["flujos"][0].total == 1.25
    assert r["flujos"][1].fecha == date(2027, 5, 31) and r["flujos"][1].total == 10 + 1.25   # 30/05/2027 es domingo
    assert r["flujos"][-1].fecha == date(2031, 12, 1) and abs(r["flujos"][-1].total - 10.125) < 1e-12  # 30/11/2031 es domingo


if __name__ == "__main__":
    for prueba in (test_como_el_excel, test_duration_y_convexidad_independientes, test_current_y_cash_yield, test_flujos,
                   test_tx31_estructura):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas del TX28 y el TX31 pasaron.")
