"""Pruebas de los breakevens entre curvas.
Correr con:
    python -m tests.test_breakevens
"""
from datetime import date

from renta_fija.calculadoras import breakeven as be
from renta_fija.calculadoras import tamar


def test_interpolar_sin_extrapolar():
    puntos = [(30, 0.40), (90, 0.34), (365, 0.30)]
    assert abs(be.interpolar(puntos, 60) - 0.37) < 1e-15
    assert be.interpolar(puntos, 10) is None and be.interpolar(puntos, 400) is None
    assert be.interpolar(puntos, 365) == 0.30


def test_formulas():
    assert abs(be.inflacion(0.05, 0.3125) - 0.25) < 1e-12               # 1,3125 / 1,05 = 1,25
    assert abs(be.devaluacion(0.08, 0.35) - 0.25) < 1e-12
    assert abs(be.tipo_cambio_real(0.08, 0.05) - (1.05 / 1.08 - 1)) < 1e-15
    assert abs(be.brecha(0.08, 0.10) - (1.08 / 1.10 - 1)) < 1e-15
    assert abs(be.mensual(0.25) - (1.25 ** (1 / 12) - 1)) < 1e-15
    assert abs(be.acumulado(0.25, 365) - 0.25) < 1e-15


def test_cruzar_y_forwards():
    tasa_fija = [{"ticker": "S1", "x": 30, "tea": 0.40}, {"ticker": "S2", "x": 365, "tea": 0.30}]
    cer = [{"ticker": "X1", "vencimiento": date(2027, 1, 1), "x": 100, "tea": 0.05},
           {"ticker": "X2", "vencimiento": date(2027, 6, 1), "x": 300, "tea": 0.06},
           {"ticker": "X3", "vencimiento": date(2030, 1, 1), "x": 1000, "tea": 0.08}]
    filas = be.cruzar(cer, tasa_fija, be.inflacion)
    tf_100 = 0.40 + (0.30 - 0.40) * 70 / 335
    assert abs(filas[0]["tea_otra"] - tf_100) < 1e-15
    assert abs(filas[0]["anual"] - ((1 + tf_100) / 1.05 - 1)) < 1e-15
    assert filas[2]["anual"] is None                                     # fuera del rango de la tasa fija
    tramo = be.forwards(filas)[0]
    a, b = filas[0], filas[1]
    assert tramo["dias"] == 200
    assert abs((1 + a["acumulado"]) * (1 + tramo["periodo"]) - (1 + b["acumulado"])) < 1e-12
    assert len(be.forwards(filas)) == 1


def test_tamar_implicita_ida_y_vuelta():
    """Si la TAMAR por publicar es la implícita, el bono TAMAR rinde exactamente la TEA objetivo."""
    emision, vto, liq = date(2026, 2, 13), date(2027, 2, 26), date(2026, 11, 16)
    conocidas, a_estimar, margen, precio = [0.25] * 190, 58, 0.065, 127.4
    dias360 = 373                                                        # DAYS360(13/02/2026, 26/02/2027)
    from renta_fija.calculadoras import motor
    assert motor.dias_30_360(emision, vto) == dias360
    x = be.tamar_implicita(0.30, precio, (vto - liq).days, dias360, margen, conocidas, a_estimar)
    prom = tamar.tamar_del_bono(conocidas, a_estimar, x)
    r = tamar.calcular(precio, prom, margen, emision, vto, liq, 0.24)
    assert abs(r["tea"] - 0.30) < 1e-12
    assert be.tamar_implicita(0.30, precio, 100, dias360, margen, conocidas, 0) is None


def test_herramienta_con_curvas_inventadas():
    from tools import breakevens
    curvas = {
        "tasa_fija": [{"ticker": "S1", "vencimiento": date(2026, 12, 15), "x": 30, "tea": 0.40},
                      {"ticker": "T1", "vencimiento": date(2027, 11, 15), "x": 365, "tea": 0.30}],
        "cer": [{"ticker": "X1", "vencimiento": date(2027, 3, 1), "x": 100, "tea": 0.05},
                {"ticker": "X2", "vencimiento": date(2027, 9, 1), "x": 300, "tea": 0.06}],
        "dl": [{"ticker": "D1", "vencimiento": date(2027, 3, 31), "x": 135, "tea": 0.08}],
        "hd": [{"ticker": "AL30", "vencimiento": date(2030, 7, 9), "x": 90, "tea": 0.10},
               {"ticker": "AL35", "vencimiento": date(2035, 7, 9), "x": 2000, "tea": 0.11}],
        "tamar": [],
    }
    original_curvas, original_brecha = breakevens._curvas, breakevens._brecha_actual
    breakevens._curvas = lambda op, liq, fp: (curvas, {"a3500": (1450.0, date(2026, 11, 12), True)}, [])
    breakevens._brecha_actual = lambda fp, tc: 1.05
    try:
        texto = breakevens.calcular_breakevens("todos", fecha="2026-11-13")
        for titulo in breakevens.NOMBRES.values():
            assert titulo in texto, titulo
        assert "A3500 implícito" in texto and "Forwards" in texto and "Brecha actual" in texto
        assert "estimado" in texto
    finally:
        breakevens._curvas, breakevens._brecha_actual = original_curvas, original_brecha


def test_comparacion_con_rem():
    """Inflación acumulada por fracción de mes, interpolación geométrica, camino mensual y lectura del REM real."""
    import tempfile
    from pathlib import Path
    import config
    from admin_datos import rem as db_rem
    from carga_datos import rem
    infl = {(2026, 11): 0.02, (2026, 12): 0.03}
    acum = be.inflacion_acumulada(infl, date(2026, 11, 16), date(2026, 12, 16))
    assert abs(acum - (1.02 ** (15 / 30) * 1.03 ** (15 / 31) - 1)) < 1e-15
    assert abs(be.inflacion_acumulada(infl, date(2026, 11, 1), date(2027, 1, 1)) - (1.02 * 1.03 - 1)) < 1e-15
    puntos = [(date(2026, 11, 15), 1000.0), (date(2027, 11, 15), 1210.0)]
    medio = be.interpolar_log(puntos, date(2027, 5, 16))
    assert abs(medio - 1000 * 1.21 ** (182 / 365)) < 1e-9 and be.interpolar_log(puntos, date(2028, 1, 1)) is None
    camino = be.camino_con_resto({(2026, 11): 0.239, (2026, 12): 0.24, (2027, 4): 0.232}, 0.2627)
    assert camino((2026, 12)) == 0.24 and camino((2027, 4)) == 0.232
    assert camino((2027, 5)) == 0.2627 and camino((2029, 1)) == 0.2627 and camino((2026, 10)) == 0.239
    original = config.DATOS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR = Path(tmp)
        try:
            rem.cargar()
            tc = db_rem.por_mes("TIPO_CAMBIO", incluir_proximos=True)
            assert tc[(2026, 12)] == 1590 and abs(tc[(2027, 12)] - 1993.508048205643) < 1e-9 and (2027, 10) in tc
            tamar = db_rem.por_mes("TAMAR", incluir_anuales=False)
            assert len(tamar) == 6 and tamar[(2027, 4)] == 23.2                   # noviembre 2026 a abril 2027
            assert abs(db_rem.valores("TAMAR")["prox12"] - 26.27040108488353) < 1e-9
        finally:
            config.DATOS_DIR = original


if __name__ == "__main__":
    for prueba in (test_interpolar_sin_extrapolar, test_formulas, test_cruzar_y_forwards,
                   test_tamar_implicita_ida_y_vuelta, test_herramienta_con_curvas_inventadas,
                   test_comparacion_con_rem):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de breakevens pasaron.")
