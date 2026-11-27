"""Pruebas de lo que pidió Agustin para la sección Curvas (27/11/2026), sin datos de afuera:
- curvas_mercado.armar con todas=True: duales en su serie (cada pata en la curva de su familia), Globales aparte de
  los Bonares y hard dollar en MEP o cable; por defecto (breakevens) solo las curvas principales.
- Precio de emisión de un bono nuevo (resultado de la licitación) hasta su liquidación.
- Exit yield desde un precio de salida y spread TAMAR editable.
Correr con:
    python -m tests.test_curvas_panel
"""
import tempfile
from datetime import date
from pathlib import Path

from fuentes_datos import mercado
from fuentes_datos.bases import licitaciones
from fuentes_datos.carga import fichas_documentos as fd
from renta_fija import curvas_mercado, duales, leer_fichas, metricas
from renta_fija.calculadoras import exit_yield

OPERACION, LIQUIDACION = date(2026, 11, 16), date(2026, 11, 17)
LECAP = {"ticker": "SPRUE", "tipo": "LECAP", "familia": "tasa_fija_capitalizable", "emision": date(2026, 6, 30),
         "vencimiento": date(2027, 6, 30), "cupon": 0.02}
NUEVA = dict(LECAP, ticker="SNUEV", emision=date(2026, 11, 20), vencimiento=date(2027, 11, 30))
DUAL_TF = dict(LECAP, ticker="TDUAL", tipo="DUAL TAMAR/TASA FIJA")
AL = {"ticker": "AL30", "familia": "hard_dollar", "ley": "AR"}
GD = {"ticker": "GD30", "familia": "hard_dollar", "ley": "NY"}


def _con(fichas: list[dict], precios: dict, prueba):
    """Corre 'prueba' con estas fichas y precios inventados (por ticker con sufijo)."""
    originales = leer_fichas.todas, leer_fichas.fichas_de, mercado.precio, mercado.feriados.proximo_dia_habil
    por_ticker = {}
    for f in fichas:
        por_ticker.setdefault(f["ticker"], []).append(f)
    leer_fichas.todas = lambda: [dict(f) for f in fichas]
    leer_fichas.fichas_de = lambda t: [dict(f) for f in por_ticker.get(t.upper(), [])]
    mercado.precio = lambda t, fecha: (precios[t.upper()], "prueba")
    mercado.feriados.proximo_dia_habil = lambda d, calendario=None: d
    try:
        return prueba()
    finally:
        leer_fichas.todas, leer_fichas.fichas_de, mercado.precio, mercado.feriados.proximo_dia_habil = originales


def _hd():
    return [dict(leer_fichas.ficha("AL30")), dict(leer_fichas.ficha("GD30"))]


def test_series_duales_y_globales():
    fichas = [LECAP, DUAL_TF] + _hd()
    precios = {"SPRUE": 100.0, "TDUAL": 101.0, "AL30D": 60.0, "AL30C": 58.0, "GD30D": 62.0, "GD30C": 60.0}

    def prueba():
        base, _, _ = curvas_mercado.armar(OPERACION, LIQUIDACION, None)
        assert [p["ticker"] for p in base["tasa_fija"]] == ["SPRUE"]            # sin duales (breakevens)
        assert [p["ticker"] for p in base["hd"]] == ["AL30"] and base["hd"][0]["precio"] == 60.0   # Bonares en MEP
        todas, _, _ = curvas_mercado.armar(OPERACION, LIQUIDACION, None, todas=True, dolar="ccl")
        series = {p["ticker"]: p["serie"] for p in todas["tasa_fija"]}
        assert series == {"SPRUE": None, "TDUAL": "Duales tasa fija"}, series
        hd = {p["ticker"]: (p["serie"], p["precio"]) for p in todas["hd"]}
        assert hd == {"AL30": (curvas_mercado.SERIE_BONARES, 58.0), "GD30": (curvas_mercado.SERIE_GLOBALES, 60.0)}
    _con(fichas, precios, prueba)


def test_precio_de_emision():
    with tempfile.TemporaryDirectory() as d:
        licitaciones.REGISTRO = Path(d) / "licitaciones.json"
        try:
            ins = fd.Instrumento(nombre="Lecap nueva", ticker="SNUEV", familia="tasa_fija_capitalizable",
                                 emision="2026-11-20", vencimiento="2027-11-30", variable_licitada="precio",
                                 valor_corte=985.5)
            assert "98,55" in fd.registrar_corte(ins, "2026-11-18", "prueba")       # por 1.000 VNO -> por 100 VN
            ins_margen = fd.Instrumento(nombre="TAMAR nuevo", ticker="MNUEV", familia="tamar_capitalizable",
                                        emision="2026-11-20", vencimiento="2028-11-30", variable_licitada="margen",
                                        valor_corte=0.05)
            assert "a la par" in fd.registrar_corte(ins_margen, "2026-11-18", "prueba")
            assert fd.registrar_corte(fd.Instrumento(nombre="reapertura", ticker="S30J7", reapertura=True,
                                                     emision="2026-11-20", variable_licitada="precio",
                                                     valor_corte=1000.0), None, "prueba") is None

            def prueba():
                precio, origen, liq = mercado.precio_bono(NUEVA, None, LIQUIDACION)
                assert (precio, liq) == (98.55, NUEVA["emision"]) and origen.startswith("precio de corte")
                curvas, _, errores = curvas_mercado.armar(OPERACION, LIQUIDACION, None)
                punto = next(p for p in curvas["tasa_fija"] if p["ticker"] == "SNUEV")
                assert punto["sin_emitir"] and punto["liquidacion"] == NUEVA["emision"] and not errores
                m = metricas.calculadora(NUEVA, NUEVA["emision"], OPERACION)(98.55)   # TIR desde la emisión
                assert abs(punto["tea"] - m["tea"]) < 1e-12
                # Ya liquidada: el precio de mercado
                assert mercado.precio_bono(NUEVA, None, date(2026, 11, 24))[1] == "prueba"
                # A la par (licitado por margen): 100 por 100 VN
                assert mercado.precio_licitacion({"ticker": "MNUEV"})[0] == 100.0
            _con([LECAP, NUEVA], {"SPRUE": 100.0, "SNUEV": 99.0}, prueba)
        finally:
            licitaciones.REGISTRO = None


def test_exit_yield_desde_precio():
    flujos = [{"fecha": date(2027, 6, 1), "total": 5.0}, {"fecha": date(2028, 6, 1), "total": 105.0}]
    r = exit_yield.retorno(flujos, 0.10, LIQUIDACION, date(2027, 7, 1), 0.12)
    assert abs(exit_yield.tasa_para(flujos, LIQUIDACION, date(2027, 7, 1), r["precio_salida"]) - 0.12) < 1e-9
    try:
        exit_yield.tasa_para(flujos, LIQUIDACION, date(2028, 7, 1), 100.0)
        raise AssertionError("vence antes: no hay precio de salida")
    except ValueError:
        pass


def test_spread_tamar_editable():
    """El spread sobre la TAMAR se puede llevar a un valor (precio_para con campo 'spread')."""
    f = {"ticker": "MPRUE", "familia": "tamar_capitalizable", "emision": date(2026, 6, 1),
         "vencimiento": date(2027, 6, 1), "margen": 0.05}
    originales = mercado.datos_tamar, mercado.feriados.proximo_dia_habil
    mercado.datos_tamar = lambda ficha, corte: {"tamar_bono": 0.30, "referencia": 0.29, "conocidas": [0.3] * 5,
                                                "a_estimar": 100, "desde_estimar": corte, "fin": date(2027, 5, 15),
                                                "inicio": date(2026, 5, 15), "ultimas": (corte, corte)}
    mercado.feriados.proximo_dia_habil = lambda d, calendario=None: d
    try:
        calc = metricas.calculadora(f, LIQUIDACION, OPERACION)
        m = calc(110.0)
        assert m["spread"] is not None and abs(m["spread"] - m["detalle"]["spread"]) < 1e-15
        precio = metricas.precio_para(calc, 0.03, "spread", referencia=110.0)
        assert abs(calc(precio)["spread"] - 0.03) < 1e-9
    finally:
        mercado.datos_tamar, mercado.feriados.proximo_dia_habil = originales


def test_dual_con_pata_definida():
    """Una pata queda definida si su pago mínimo (lo que falta publicar en 0) supera el máximo de la otra."""
    fija = {"ticker": "TDOS", "tipo": "DUAL", "familia": "tasa_fija_capitalizable", "emision": date(2025, 1, 15),
            "vencimiento": date(2026, 12, 15), "cupon": 0.02}
    variable = {"ticker": "TDOS", "tipo": "DUAL", "familia": "tamar_capitalizable", "emision": date(2025, 1, 15),
                "vencimiento": date(2026, 12, 15), "margen": 0.0}
    originales = mercado.datos_tamar, metricas.fichas_de
    metricas.fichas_de = lambda t: [dict(fija), dict(variable)]

    def ventana(tamar_publicada: float, faltan: int, fin=date(2026, 11, 30)):
        mercado.datos_tamar = lambda f, corte: {"conocidas": [tamar_publicada] * 400, "a_estimar": faltan,
                                                "tamar_bono": tamar_publicada, "referencia": tamar_publicada,
                                                "fin": fin, "inicio": date(2025, 1, 1), "desde_estimar": corte,
                                                "ultimas": (corte, corte)}
    try:
        ventana(0.40, 4)               # la TAMAR acumuló mucho: aun con 0 en los días que faltan, supera a la fija
        assert duales.pata_que_paga("TDOS", OPERACION) == "tamar_capitalizable"
        ventana(0.20, 4)               # TAMAR baja: todavía podría pagar cualquiera (la TAMAR no tiene techo)
        assert duales.pata_que_paga("TDOS", OPERACION) is None
        ventana(0.20, 0, fin=date(2026, 11, 10))   # ventana completa: las dos fijas, paga la mayor (la fija)
        assert duales.pata_que_paga("TDOS", OPERACION) == "tasa_fija_capitalizable"
    finally:
        mercado.datos_tamar, metricas.fichas_de = originales


if __name__ == "__main__":
    for prueba in (test_series_duales_y_globales, test_precio_de_emision, test_exit_yield_desde_precio,
                   test_spread_tamar_editable, test_dual_con_pata_definida):
        prueba()
        print("OK ", prueba.__name__)
    print("Todas las pruebas de curvas del panel pasaron.")
