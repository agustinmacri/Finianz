"""Pruebas del módulo de carteras (lectura del Excel, valuación, monedas y salida), sin datos de afuera: precios y
contexto simulados, con fichas reales de Lecap, Bonar y Global. Correr con:
    python -m tests.test_carteras
"""
import tempfile
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook

from carteras import excel, valuar
from renta_fija import leer_fichas
from fuentes_datos import mercado

OPERACION, LIQUIDACION = date(2026, 11, 16), date(2026, 11, 17)
MEP, CCL = 1450.0, 1500.0
PRECIOS = {"AL30": 87000.0, "AL30D": 87000.0 / MEP, "AL30C": 87000.0 / CCL, "AL30D_": 60.0, "GD30C": 62.0,
           "GGAL": 6500.0}
mercado.feriados.proximo_dia_habil = lambda d, calendario=None: d
mercado.contexto = lambda fecha=None: (OPERACION, LIQUIDACION, OPERACION)
valuar.carga_precios.registrar = lambda t: {"tipo": "ACCIONES", "descripcion": "Grupo Financiero Galicia"}
# Supuesto de dólar constante: la TIR en pesos de un hard dollar tiene que dar igual a su TIR en dólares
valuar.Proyecciones.dolar = lambda self, tipo: (lambda d: self.ctx.fx[tipo])

LECAP = next(f["ticker"] for f in leer_fichas.todas() if f["familia"] == "tasa_fija_capitalizable"
             and f["vencimiento"] > LIQUIDACION and "DUAL" not in f.get("tipo", "").upper())


def _precio(ticker, fecha=None):
    t = ticker.upper()
    if t == "AL30D" and _precio.valuando:      # el precio del bono (no el del tipo de cambio)
        return 60.0, "p"
    if t == LECAP:
        return 101.0, "p"
    if t in _precio.precios_extra:
        return _precio.precios_extra[t], "p"
    return PRECIOS[t], "p"


_precio.valuando = False
_precio.precios_extra = {}
mercado.precio = _precio


def _excel(carpeta: Path, nombre: str, filas, supuestos=None, encabezado=("Ticker", "Nominales")):
    wb = Workbook()
    h = wb.active
    h.title = "Cartera"
    h.append(["Cartera de prueba"])            # una fila de título antes del encabezado
    h.append(list(encabezado))
    for fila in filas:
        h.append(list(fila))
    if supuestos:
        s = wb.create_sheet("Supuestos")
        s.append(["Variable", "Fuente"])
        for k, v in supuestos.items():
            s.append([k, v])
    wb.save(carpeta / f"{nombre}.xlsx")


def _con_carpeta(prueba):
    def envoltura():
        with tempfile.TemporaryDirectory() as d:
            original = excel.carpeta
            excel.carpeta = lambda: Path(d)
            try:
                prueba(Path(d))
            finally:
                excel.carpeta = original
    envoltura.__name__ = prueba.__name__
    return envoltura


@_con_carpeta
def test_leer(d):
    _excel(d, "Pérez Juan", [(None, "al30", 1000), ("Acción", "GGAL", "200"), (None, None, None)], {"Inflación": "mensual:2%"},
           encabezado=("Tipo Activo", "Ticker", "Cantidad"))
    c = excel.leer("perez juan")                # sin acentos ni mayúsculas
    assert [p.ticker for p in c.posiciones] == ["AL30", "GGAL"]
    assert c.posiciones[1].nominales == 200
    assert c.supuestos["inflacion"] == "mensual:2%"
    assert excel.listar() == ["Pérez Juan"]


@_con_carpeta
def test_valuar_y_monedas(d):
    _excel(d, "cliente", [(LECAP, 1_000_000), ("AL30", 10_000), ("GD30", 10_000), ("GGAL", 200)])
    c = excel.leer("cliente")
    _precio.valuando = False
    fx = valuar.tipos_de_cambio(OPERACION)
    assert abs(fx["mep"] - MEP) < 1e-9 and abs(fx["ccl"] - CCL) < 1e-9
    _precio.valuando = True
    v = valuar.valuar(c, "pesos")
    filas = {f["ticker"]: f for f in v["filas"]}
    assert not v["avisos"], v["avisos"]
    # Valuación: pesos por 100 VN; Bonar al MEP; Global al CCL; acción por unidad
    assert abs(filas[LECAP]["total"] - 1_000_000 * 101 / 100) < 1e-6
    assert abs(filas["AL30"]["total"] - 10_000 * 60 * MEP / 100) < 1e-6
    assert abs(filas["GD30"]["total"] - 10_000 * 62 * CCL / 100) < 1e-6
    assert filas["GGAL"]["total"] == 200 * 6500
    assert abs(sum(f["peso"] for f in v["filas"]) - 1) < 1e-12
    # Tasas: tasa fija sin referencia y proyectada = propia; hard dollar en USD y con dólar constante igual en pesos
    assert filas[LECAP]["referencia"] == "" and filas[LECAP]["tir_proyectada"] == filas[LECAP]["tir_propia"]
    for t in ("AL30", "GD30"):
        assert filas[t]["referencia"] == "USD"
        # La TIR propia sale de la TNA semestral 30/360; la proyectada descuenta por días corridos: difieren < 1 pb
        assert abs(filas[t]["tir_proyectada"] - filas[t]["tir_propia"]) < 1e-4, (t, filas[t]["tir_proyectada"], filas[t]["tir_propia"])
    assert filas["AL30"]["tipo"] == "Bonar (ley AR)" and filas["GD30"]["tipo"] == "Global (ley NY)"
    # Renta variable: sin tasas ni duration
    assert filas["GGAL"]["tir_propia"] is None and filas["GGAL"]["duration"] is None and filas["GGAL"]["tipo"] == "Acción"
    # Otras monedas: todo dividido por el tipo de cambio, los pesos no cambian
    for moneda, tc in (("mep", MEP), ("ccl", CCL)):
        w = valuar.valuar(c, moneda)
        assert abs(w["totales"]["total"] - v["totales"]["total"] / tc) < 1e-6
        assert abs({f["ticker"]: f for f in w["filas"]}["AL30"]["precio"] - (60 * MEP / tc)) < 1e-9
        assert [f["peso"] for f in w["filas"]] == [f["peso"] for f in v["filas"]]
    # Salida: tabla de texto con las columnas en orden y Excel con encabezado y filas
    t = valuar.texto(v)
    assert " | ".join(excel.COLUMNAS) in t and "USD + " in t
    ruta = excel.guardar_valuacion(v)
    hoja = load_workbook(ruta)["Cartera"]
    valores = [[c.value for c in fila] for fila in hoja.iter_rows()]
    fila_enc = next(i for i, fila in enumerate(valores) if fila[:len(excel.COLUMNAS)] == excel.COLUMNAS)
    # Arriba la liquidez (pesos, MEP, cable), money market y caución; abajo crédito y pasivo (en cero si no hay)
    primeras = [fila[1] for fila in valores[fila_enc + 1:fila_enc + 6]]
    assert primeras == ["Liquidez en pesos", "Liquidez en dólares MEP", "Liquidez en dólares cable", "Money market",
                        "Caución colocadora"], primeras
    assert valores[fila_enc + 6][2] == LECAP
    tipos = [f["tipo"] for f in v["filas"]]
    assert tipos[-2:] == ["Crédito", "Pasivo"] and all(f["total"] == 0 for f in v["filas"] if f.get("liquidez"))


@_con_carpeta
def test_errores(d):
    _excel(d, "con_error", [("NOEXISTE", 5), (LECAP, 100)])
    _precio.valuando = True
    original = valuar.carga_precios.registrar
    valuar.carga_precios.registrar = lambda t: (_ for _ in ()).throw(ValueError("ticker desconocido"))
    try:
        v = valuar.valuar(excel.leer("con_error"))
    finally:
        valuar.carga_precios.registrar = original
    assert [f["ticker"] for f in v["filas"] if f["ticker"]] == [LECAP]
    assert v["avisos"] and "NOEXISTE" in v["avisos"][0]
    try:
        valuar.valuar(excel.leer("con_error"), "euros")
        raise AssertionError("tendría que rechazar la moneda")
    except ValueError:
        pass
    try:
        excel.leer("no_esta")
        raise AssertionError("tendría que avisar que no existe")
    except ValueError:
        pass


@_con_carpeta
def test_guardar_y_archivar(d):
    c = excel.Cartera("Gómez", [excel.Posicion(" al30 ", 1000), excel.Posicion("GGAL", 50, "Acción", "Galicia")],
                      {"inflacion": "mensual:2%"})
    excel.guardar(c)
    leida = excel.leer("gomez")
    assert [p.ticker for p in leida.posiciones] == ["AL30", "GGAL"] and leida.posiciones[1].descripcion == "Galicia"
    assert leida.supuestos["inflacion"] == "mensual:2%" and leida.supuestos["tamar"] == "rem"
    c.nombre = "Gómez Ana"                                   # renombrar: el archivo anterior se archiva, no se borra
    excel.guardar(c, nombre_anterior="Gómez")
    assert excel.listar() == ["Gómez Ana"] and len(list((d / "anteriores").iterdir())) == 1
    for mala, motivo in ((excel.Cartera("a/b", c.posiciones), "nombre"), (excel.Cartera("x", []), "vacía"),
                         (excel.Cartera("x", [excel.Posicion("AL30", 1), excel.Posicion("al30", 2)]), "repetido"),
                         (excel.Cartera("x", [excel.Posicion("AL30", -5)]), "negativo")):
        try:
            excel.guardar(mala)
            raise AssertionError(f"tendría que rechazar: {motivo}")
        except ValueError:
            pass
    excel.guardar(excel.Cartera("Otra", c.posiciones))
    try:
        excel.guardar(excel.Cartera("Otra", c.posiciones), nombre_anterior="Gómez Ana")   # no pisa otra cartera
        raise AssertionError("tendría que avisar que ya existe")
    except ValueError:
        pass
    excel.archivar("Otra")
    assert excel.listar() == ["Gómez Ana"]


@_con_carpeta
def test_liquidez_cuadros_y_cobros(d):
    from carteras.excel import Liquidez
    c = excel.Cartera("Con liquidez", [excel.Posicion("S30N6", 1_000_000), excel.Posicion("AL30", 10_000),
                                       excel.Posicion("GGAL", 100)], {},
                      [Liquidez("Liquidez", "pesos", 500_000, "Saldo"), Liquidez("Money market", "pesos", 1_000_000, "FCI MM", 0.30),
                       Liquidez("Liquidez", "mep", 1_000, "Dólares"),
                       Liquidez("Caución tomadora", "pesos", 300_000, "Caución", 0.32, date(2026, 11, 23))])
    excel.guardar(c)
    leida = excel.leer("con liquidez")
    assert [x.tipo for x in leida.liquidez] == ["Liquidez", "Money market", "Liquidez", "Caución tomadora"]
    assert leida.liquidez[1].tasa == 0.30 and leida.liquidez[3].vencimiento == date(2026, 11, 23)
    _precio.valuando = True
    valuar.carga_precios.registrar = lambda t: {"tipo": "ACCIONES", "descripcion": "Grupo Financiero Galicia"}
    _precio.precios_extra = {"S30N6": 99.0}
    v = valuar.valuar(leida, "pesos")
    filas = {(f["ticker"] or f["descripcion"]): f for f in v["filas"]}
    # Liquidez sin colocar: 0 y 0; money market con su tasa; pasivo resta del patrimonio
    assert filas["Saldo"]["tir_proyectada"] == 0 and filas["Saldo"]["duration"] == 0
    assert abs(filas["FCI MM"]["tir_proyectada"] - ((1 + 0.30 / 365) ** 365 - 1)) < 1e-12
    assert filas["Caución"]["total"] == -300_000 and filas["Caución"]["categoria"] == "Pasivos"
    assert abs(filas["Dólares"]["total"] - 1_000 * MEP) < 1e-9 and filas["Dólares"]["moneda_activo"] == "Dólar MEP"
    total = sum(f["total"] for f in v["filas"])
    assert abs(v["totales"]["total"] - total) < 1e-6
    # La TIR ponderada incluye liquidez y pasivos (con signo) y deja afuera la renta variable
    pond = [f for f in v["filas"] if f["categoria"] != "Renta Variable"]
    esperada = sum(f["tir_proyectada"] * f["total"] for f in pond) / sum(f["total"] for f in pond)
    assert abs(v["totales"]["tir_proyectada_rf"] - esperada) < 1e-12
    # Clasificación
    assert (filas["AL30"]["categoria"], filas["AL30"]["subclase"], filas["AL30"]["moneda_activo"]) == \
        ("Renta Fija", "Hard dollar", "Dólar MEP")
    assert filas["S30N6"]["subclase"] == "Tasa fija" and filas["S30N6"]["emisor"] == "Tesoro Nacional"
    assert filas["GGAL"]["categoria"] == "Renta Variable" and filas["GGAL"]["subclase"] == "Acciones"
    # Cuadros: cada uno suma el patrimonio
    cu = v["cuadros"]
    assert abs(sum(x["total"] for x in cu["categoria"] if x["subclase"] is None) - total) < 1e-6
    assert abs(sum(x["total"] for x in cu["moneda"]) - total) < 1e-6
    assert abs(sum(x["total"] for x in cu["emisor"]) - total) < 1e-6
    assert abs(sum(x["total"] for x in cu["clase_moneda"]) - total) < 1e-6
    assert [x["categoria"] for x in cu["categoria"] if x["subclase"] is None] == \
        ["Renta Fija", "Renta Variable", "Liquidez", "Pasivos"]
    # Cobros a 30 días: la Lecap que vence y la caución que hay que pagar
    conceptos = {(x["ticker"], x["concepto"]) for x in v["cobros"]}
    assert ("S30N6", "Vencimiento") in conceptos and ("Caución", "Vencimiento (a pagar)") in conceptos
    lecap = next(x for x in v["cobros"] if x["ticker"] == "S30N6")
    assert lecap["amortizacion"] == 1_000_000 and lecap["cupon"] > 0
    caucion = next(x for x in v["cobros"] if x["ticker"] == "Caución")
    assert abs(caucion["monto"] + 300_000 * (1 + 0.32 * 7 / 365)) < 1e-6
    assert "Por moneda" in valuar.texto(v)
    hojas = load_workbook(excel.guardar_valuacion(v)).sheetnames
    assert {"Cartera", "Composicion", "Cobros"} <= set(hojas)
    _precio.precios_extra = {}


def test_precio_con_ppi_caido():
    from fuentes_datos.conexiones.http import ErrorAPI
    originales = mercado.precio, valuar.carga_precios.actualizar, valuar.db_precios.entre

    def caido(*a, **k):
        raise ErrorAPI("La API falló 4 veces seguidas")
    mercado.precio = caido
    valuar.carga_precios.actualizar = caido
    try:
        valuar.db_precios.entre = lambda t, plazo, *a: [{"fecha": "2026-11-20", "cierre": 80.0},
                                                         {"fecha": "2026-11-23", "cierre": 81.5}]
        avisos = []
        assert valuar.precio("AL30D", None, avisos) == 81.5
        assert "2026-11-23" in avisos[0]
        valuar.db_precios.entre = lambda *a: []
        try:
            valuar.precio("AL30D", None, [])
            raise AssertionError("sin cierres guardados tendría que fallar")
        except ErrorAPI:
            pass
    finally:
        mercado.precio, valuar.carga_precios.actualizar, valuar.db_precios.entre = originales


if __name__ == "__main__":
    for prueba in (test_leer, test_valuar_y_monedas, test_errores, test_guardar_y_archivar, test_liquidez_cuadros_y_cobros,
                   test_precio_con_ppi_caido):
        prueba()
        print(f"OK {prueba.__name__}")
