"""Pruebas del módulo de carteras (lectura del Excel, valuación, monedas y salida), sin datos de afuera: precios y
contexto simulados, con fichas reales de Lecap, Bonar y Global. Correr con:
    python -m tests.test_carteras
"""
import tempfile
from datetime import date
from pathlib import Path

from openpyxl import Workbook, load_workbook

from carteras import excel, valuar
from renta_fija import leer_fichas, mercado

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
    return PRECIOS[t], "p"


_precio.valuando = False
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
    assert valores[fila_enc + 1][2] == LECAP


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
    assert [f["ticker"] for f in v["filas"]] == [LECAP]
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


if __name__ == "__main__":
    for prueba in (test_leer, test_valuar_y_monedas, test_errores):
        prueba()
        print(f"OK {prueba.__name__}")
