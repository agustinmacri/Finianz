"""Pruebas de las calculadoras de tasa fija contra la planilla de Agustin (tasa_fija.xlsx, 13/11/2026).

Lecap/Boncap (liquidación 16/11/2026): el Excel tenía mal el vencimiento del T15E7 (17/01 → 15/01/2027)
y del T31Y7 (30/05 → 31/05/2027); con las fechas corregidas, el pago final coincide con el publicado.
TY30P: valores del Excel con las correcciones acordadas (duration y convexidad con la TIR de mercado y
base 365; TNA semestral exacta).
Correr con:
    python -m tests.test_renta_fija_tasa_fija
"""
from datetime import date, timedelta

from renta_fija import leer_fichas
from renta_fija.calculadoras import tasa_fija

LIQUIDACION = date(2026, 11, 16)

# ticker: (precio, pago final del Excel, TNA, TEA, TEM 30/365) — filas sin error de fecha
LECAPS_EXCEL = {
    "S30N6": (127.7689999999998, 129.88822671719913, 0.4324309338268709, 0.5355426978174136, 0.03587940108856147),
    "S29E7": (105.43999999998701, 111.68490338270816, 0.29213357342891266, 0.32817997138340993, 0.02360101137055315),
    "T30A7": (138.60999999999854, 157.34102123941065, 0.2989343439030154, 0.3236450009326557, 0.02331329930255266),
    "T30J7": (131.79999999999703, 156.03729080688436, 0.2969977018180562, 0.31342030015832867, 0.02266127991686262),
}
# pagos finales publicados (calculador de LECAP de sinelefantesblancos.com.ar), para los dos corregidos
PUBLICADOS = {"T15E7": 161.104, "T31Y7": 151.563}


def test_lecaps_como_el_excel():
    for t, (precio, pf, tna, tea, tem) in LECAPS_EXCEL.items():
        f = leer_fichas.ficha(t)
        pago = tasa_fija.pago_final(f["cupon"], f["emision"], f["vencimiento"])
        assert abs(pago - pf) < 1e-9, (t, pago, pf)
        r = tasa_fija.calcular_capitalizable(precio, pago, LIQUIDACION, f["vencimiento"])
        assert abs(r["tna"] - tna) < 1e-9 and abs(r["tea"] - tea) < 1e-9 and abs(r["tem"] - tem) < 1e-9, t
        assert abs(r["duration"] - r["plazo_residual"] / 365) < 1e-15


def test_vencimientos_corregidos():
    for t, publicado in PUBLICADOS.items():
        f = leer_fichas.ficha(t)
        assert round(tasa_fija.pago_final(f["cupon"], f["emision"], f["vencimiento"]), 3) == publicado, t


def _ajustar(d: date) -> date:
    while d.weekday() >= 5:      # en las fechas futuras del TY30P solo hay fines de semana
        d += timedelta(days=1)
    return d


def _ty30p():
    f = leer_fichas.ficha("TY30P")
    return tasa_fija.calcular_cupon(113.29999999999862, LIQUIDACION, f["pagos"], f["cupon"], f["frecuencia"],
                                    f["emision"], _ajustar)


def test_ty30p_como_el_excel():
    r = _ty30p()
    assert abs(r["interes_corrido"] - 13.602777777777774) < 1e-9
    assert abs(r["valor_tecnico"] - 113.60277777777777) < 1e-9
    assert abs(r["paridad"] - 0.9973347678313691) < 1e-12
    assert abs(r["precio_clean"] - 99.69722222222085) < 1e-9
    assert abs(r["tir_real"] - 0.31818093657493596) < 1e-8                     # XIRR del Excel
    assert abs(r["current_yield"] - 0.2958959070519112) < 1e-9
    assert abs(r["tna_semestral"] - ((1 + r["tir_real"]) ** 0.5 - 1) * 2) < 1e-15


def test_ty30p_duration_con_tir_de_mercado():
    r = _ty30p()
    t = [((f.fecha - LIQUIDACION).days / 365, f.total) for f in r["flujos"]]
    y, p = r["tir_real"], r["precio_dirty"]
    dur = sum(ti * m / (1 + y) ** ti for ti, m in t) / p
    assert abs(r["duration"] - dur) < 1e-9 and abs(r["duration_modificada"] - dur / (1 + y)) < 1e-9
    assert [(f.fecha.isoformat(), f.total) for f in r["flujos"]][:2] == [("2026-11-30", 14.75), ("2027-05-31", 14.75)]
    assert r["flujos"][-1].fecha == date(2030, 5, 30) and r["flujos"][-1].total == 114.75


def test_letra_a_descuento():
    from datetime import date
    liq, vto = date(2026, 11, 16), date(2027, 2, 26)
    r = tasa_fija.calcular_descuento(93.0, liq, vto)
    plazo = (vto - liq).days
    assert r["pago_final"] == 100 and r["plazo_residual"] == plazo
    assert abs(r["tna"] - (100 / 93 - 1) * 365 / plazo) < 1e-15
    assert abs(r["tea"] - ((100 / 93) ** (365 / plazo) - 1)) < 1e-12
    assert abs(r["tasa_descuento"] - 0.07 * 365 / plazo) < 1e-15


if __name__ == "__main__":
    for prueba in (test_lecaps_como_el_excel, test_vencimientos_corregidos, test_ty30p_como_el_excel,
                   test_ty30p_duration_con_tir_de_mercado, test_letra_a_descuento):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de tasa fija pasaron.")
