"""Pruebas de las operaciones de cartera (etapa 3): posiciones, liquidez por moneda, money market, cauciones,
pasivos, cobros automáticos, costo promedio en pesos/MEP/CCL y resultado realizado. Sin datos de afuera.
Correr con:
    python -m tests.test_carteras_operaciones
"""
import tempfile
from datetime import date
from pathlib import Path

from carteras import excel
from carteras import operaciones as ops
from carteras.operaciones import Operacion as Op

D = lambda m, d: date(2026, m, d)
MEP = lambda d: 1000.0 if d < D(9, 1) else 1200.0
ops.tipo_de_cambio = lambda moneda, d: {"pesos": 1.0, "mep": MEP(d), "ccl": MEP(d) * 1.03}[moneda]
ops.es_renta_fija = lambda ticker: ticker in ("BONO", "AL30X")
ops.precio_cierre = lambda ticker, moneda, d: 1000.0
# BONO: el 1/8 paga 5 de renta y amortiza 25 (de 100); AL30X no paga en el período
ops.pagos = lambda ticker, desde, hasta: [
    {"fecha": D(8, 1), "moneda": "pesos", "renta": 5.0, "amortizacion": 25.0, "residual_antes": 100.0, "final": False}
] if ticker == "BONO" and desde < D(8, 1) <= hasta else []

OPERACIONES = [
    Op(D(6, 1), "Depósito", monto=1_000_000, contraparte="Cliente"),
    Op(D(6, 1), "Suscripción", monto=100_000, tasa=0.365),
    Op(D(6, 1), "Caución colocadora", monto=50_000, tasa=0.365, vencimiento=D(6, 8)),
    Op(D(6, 2), "Compra", "BONO", nominales=10_000, precio=90, gastos=100, contraparte="PPI"),
    Op(D(6, 3), "Compra", "AL30X", nominales=1_000, precio=60, moneda="mep"),
    Op(D(6, 5), "Ingreso", "ACC", nominales=100),
    Op(D(7, 1), "Pasivo", monto=20_000, tasa=0.365, vencimiento=D(7, 11)),
    Op(D(9, 1), "Venta", "BONO", nominales=5_000, precio=95, gastos=50),
    Op(D(9, 2), "Venta", "AL30X", nominales=1_000, precio=62, moneda="mep"),
    Op(D(9, 10), "Egreso", "ACC", nominales=40),
]


def test_libro():
    libro = ops.estado(OPERACIONES, D(9, 15))
    # Posiciones
    assert libro.tenencias["BONO"].nominales == 5_000 and libro.tenencias["AL30X"].nominales == 0
    assert libro.tenencias["ACC"].nominales == 60
    # Costo: BONO 9.100 (con gastos) → amortiza 25% (queda 6.825) → vende la mitad (queda 3.412,5)
    assert abs(libro.tenencias["BONO"].costo["pesos"] - 3_412.5) < 1e-9
    assert abs(libro.tenencias["BONO"].costo["mep"] - 3_412.5 / 1000) < 1e-9     # al MEP del día de la compra
    assert abs(libro.tenencias["ACC"].costo["pesos"] - 60_000) < 1e-9            # ingreso al cierre del día
    # Liquidez en pesos: depósito − MM − caución + caución con interés − compra BONO + cobro (renta + amortización)
    # + pasivo − pasivo con interés + venta BONO neta
    esperado = (1_000_000 - 100_000 - 50_000 + 50_000 * (1 + 0.365 * 7 / 365) - 9_100 + (500 + 2_500)
                + 20_000 - 20_000 * (1 + 0.365 * 10 / 365) + (4_750 - 50))
    assert abs(libro.liquidez["pesos"] - esperado) < 1e-6, (libro.liquidez["pesos"], esperado)
    assert abs(libro.liquidez["mep"] - (-600 + 620)) < 1e-9                     # compra y venta en MEP
    # Money market: 0,1% diario desde el 1/6
    assert abs(libro.mm["pesos"] - 100_000 * 1.001 ** (D(9, 15) - D(6, 1)).days) < 1e-6
    assert not libro.colocaciones                                                 # caución y pasivo vencidos
    # Resultado realizado
    r = {(x["ticker"], x["concepto"]): x["resultado"] for x in libro.realizado}
    assert abs(r[("BONO", "Cupón")]["pesos"] - 500) < 1e-9
    assert abs(r[("BONO", "Amortización")]["pesos"] - (2_500 - 2_275)) < 1e-9     # cobrado − costo de la parte
    assert abs(r[("BONO", "Venta")]["pesos"] - (4_700 - 3_412.5)) < 1e-9
    assert abs(r[("AL30X", "Venta")]["mep"] - 20) < 1e-9                          # en dólares gana 20
    assert abs(r[("AL30X", "Venta")]["pesos"] - (620 * 1200 - 600 * 1000)) < 1e-9 # en pesos, por el MEP
    assert abs(r[("", "Interés caución colocadora")]["pesos"] - 350) < 1e-9
    assert abs(r[("", "Interés pasivo")]["pesos"] + 200) < 1e-9
    assert ("ACC", "Egreso") not in r                                              # el egreso no es resultado
    assert [c["total"] for c in libro.cobros] == [3_000]


def test_cobro_del_aviso_y_errores():
    con_aviso = OPERACIONES[:4] + [Op(D(8, 1), "Cobro", "BONO", monto=3_100)]
    libro = ops.estado(con_aviso, D(8, 15))
    cobro = libro.cobros[0]
    assert cobro["aviso"] and abs(cobro["total"] - 3_100) < 1e-9
    assert abs(cobro["renta"] - 3_100 * 500 / 3_000) < 1e-9                       # se reparte en proporción
    try:
        ops.estado(OPERACIONES[:1] + [Op(D(6, 2), "Venta", "BONO", nominales=10, precio=90)], D(6, 3))
        raise AssertionError("tendría que rechazar vender lo que no hay")
    except ValueError as e:
        assert "hay 0" in str(e)


def test_excel_y_valuacion():
    with tempfile.TemporaryDirectory() as d:
        original = excel.carpeta
        excel.carpeta = lambda: Path(d)
        try:
            c = excel.Cartera("Con operaciones", [], {}, [], OPERACIONES)
            excel.guardar(c)
            leida = excel.leer("con operaciones")
            assert len(leida.operaciones) == len(OPERACIONES) and not leida.posiciones
            assert leida.operaciones[3].contraparte == "PPI" and leida.operaciones[1].tasa == 0.365
            assert [op.tipo for op in leida.operaciones] == [op.tipo for op in OPERACIONES]
            # Errores de carga con la fila
            from openpyxl import load_workbook
            ruta = excel.ruta("con operaciones")
            libro = load_workbook(ruta)
            libro["Operaciones"].append([date(2026, 9, 20), "", "Compra", "BONO", 100, None, "pesos"])
            libro.save(ruta)
            try:
                excel.leer("con operaciones")
                raise AssertionError("tendría que pedir el precio")
            except ValueError as e:
                assert "fila 12" in str(e) and "precio" in str(e)
        finally:
            excel.carpeta = original
    # Las filas de la liquidez salen del libro, en el orden pedido
    from carteras import valuar
    libro = ops.estado(OPERACIONES[:3] + [Op(D(6, 4), "Pasivo", monto=20_000, tasa=0.30, vencimiento=D(12, 4))], D(6, 5))
    filas = valuar._liquidez_de_libro(libro, D(6, 5))
    assert [(x.tipo, x.moneda) for x in filas] == [("Liquidez", "pesos"), ("Liquidez", "mep"), ("Liquidez", "ccl"),
                                                    ("Money market", "pesos"), ("Caución colocadora", "pesos"),
                                                    ("Pasivo", "pesos")]
    assert filas[0].monto == 1_000_000 - 100_000 - 50_000 + 20_000


def test_evolucion_y_twr():
    from datetime import timedelta
    from carteras import evolucion, historia
    dias = [D(6, 1) + timedelta(days=i) for i in range(61) if (D(6, 1) + timedelta(days=i)).weekday() < 5]
    serie = lambda f: historia.Serie({d: f(d) for d in dias})
    evolucion.series_tipo_de_cambio = lambda: {"mep": serie(lambda d: 1000.0), "ccl": serie(lambda d: 1030.0)}
    evolucion.precio_historico = lambda ticker: (lambda d: 1000.0 if d < D(7, 1) else 1100.0)
    originales = ops.tipo_de_cambio
    ops.tipo_de_cambio = lambda moneda, d: {"pesos": 1.0, "mep": 1000.0, "ccl": 1030.0}[moneda]
    try:
        operaciones = [Op(D(6, 1), "Depósito", monto=1_000_000), Op(D(6, 1), "Compra", "ACC", nominales=1_000, precio=1_000),
                       Op(D(7, 15), "Depósito", monto=500_000)]
        r = evolucion.evolucion(operaciones, D(7, 31))
        res = r["resumen"]["pesos"]
        # La acción sube 10%; el aporte del 15/7 queda en liquidez y no es rendimiento
        assert abs(res["final"] - 1_600_000) < 1e-6 and abs(res["aportes_netos"] - 1_500_000) < 1e-6
        assert abs(res["ganancia"] - 100_000) < 1e-6
        assert abs(res["twr"] - 0.10) < 1e-12, res["twr"]
        assert abs(r["resumen"]["mep"]["twr"] - 0.10) < 1e-12 and abs(r["resumen"]["mep"]["final"] - 1_600) < 1e-9
        # TIR: los aportes contra el patrimonio final
        tir = res["tir"]
        vpn = (-1_000_000 - 500_000 / (1 + tir) ** ((D(7, 15) - D(6, 1)).days / 365)
               + 1_600_000 / (1 + tir) ** ((D(7, 31) - D(6, 1)).days / 365))
        assert abs(vpn) < 1e-3 and tir > 0.10
        assert r["puntos"][0]["fecha"] == D(6, 1) and r["puntos"][-1]["fecha"] == D(7, 31)
    finally:
        ops.tipo_de_cambio = originales


if __name__ == "__main__":
    for prueba in (test_libro, test_cobro_del_aviso_y_errores, test_excel_y_valuacion, test_evolucion_y_twr):
        prueba()
        print(f"OK {prueba.__name__}")
