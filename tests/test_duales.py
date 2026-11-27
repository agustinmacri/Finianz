"""Pruebas del dual TAMAR / dollar linked (TMVE8): pata TAMAR sobre el VN en dólares al tipo de cambio inicial y
resumen de qué pata paga. Correr con: python -m tests.test_duales"""
from datetime import date

from renta_fija import metricas
from fuentes_datos import mercado
from renta_fija.calculadoras import tamar
from tools import bonos, proyecciones

LIQ, OP = date(2026, 11, 27), date(2026, 11, 26)
EMISION, VTO = date(2026, 7, 31), date(2028, 1, 28)
TAMAR = {"ticker": "TMVE8", "tipo": "DUAL TAMAR/DL", "familia": "tamar_capitalizable", "emision": EMISION,
         "vencimiento": VTO, "margen": 0.0, "tipo_cambio_inicial": 1300.0}
DL = {"ticker": "TMVE8", "tipo": "DUAL TAMAR/DL", "familia": "dolar_linked_bullet", "emision": EMISION, "vencimiento": VTO}
DATOS = {"referencia": 0.30, "tamar_bono": 0.31, "conocidas": [0.31] * 80, "a_estimar": 200, "desde_estimar": OP,
         "inicio": EMISION, "fin": date(2028, 1, 14)}


def _parches():
    mercado.datos_tamar = lambda f, corte: DATOS
    mercado.a3500 = lambda operacion: (1450.0, operacion, False)
    mercado.a3500_pago_conocido = lambda f, operacion=None: None
    mercado.feriados.sumar_dias_habiles = lambda d, n, calendario=None: date.fromordinal(d.toordinal() + n)
    proyecciones.camino_tamar = lambda fuente, operacion: (None, "TAMAR actual")
    proyecciones.tamar_del_bono = lambda f, operacion, camino: (DATOS["tamar_bono"], DATOS)
    proyecciones.camino_dolar = lambda tipo, fuente, operacion, fecha_precios=None: (
        (lambda d: 1450.0 * (1.30 if fuente == "rem" else 1.10)), fuente, 1450.0, "")


def test_pata_tamar_escalada():
    _parches()
    precio = 150_000.0                                       # pesos por 100 VN en dólares
    m = metricas.calculadora(TAMAR, LIQ, OP)(precio)
    r = tamar.calcular(precio / 1300.0, 0.31, 0.0, EMISION, VTO, LIQ, 0.30)
    assert abs(m["tea"] - r["tea"]) < 1e-12                  # la TIR no cambia con la escala
    assert abs(m["flujos"][-1]["total"] - r["pago_final"] * 1300.0) < 1e-6
    assert mercado.tipo_cambio_inicial({"ticker": "X"}) == 1.0


def test_resumen_dual():
    _parches()
    precio = 150_000.0
    texto = bonos._dual_dl_tamar([DL, TAMAR], precio, LIQ, OP, "actual", None)
    r = tamar.calcular(precio / 1300.0, 0.31, 0.0, EMISION, VTO, LIQ, 0.30)
    indiferencia = r["pago_final"] * 1300.0 / 100
    assert f"{indiferencia:,.2f}" in texto, texto
    # REM: A3500 1885 > indiferencia → paga dollar linked si 100×1885 > pago TAMAR
    gana_rem = "dollar linked" if 1450 * 1.30 > indiferencia else "TAMAR"
    gana_be = "dollar linked" if 1450 * 1.10 > indiferencia else "TAMAR"
    lineas = texto.splitlines()
    assert f"paga la pata {gana_rem}" in next(x for x in lineas if x.startswith("Con el REM"))
    assert f"paga la pata {gana_be}" in next(x for x in lineas if x.startswith("Con el breakeven"))
    sin_tc = dict(TAMAR)
    del sin_tc["tipo_cambio_inicial"]
    assert "Falta el tipo de cambio inicial" in bonos._dual_dl_tamar([DL, sin_tc], precio, LIQ, OP, "actual", None)


if __name__ == "__main__":
    for prueba in (test_pata_tamar_escalada, test_resumen_dual):
        prueba()
        print(f"OK {prueba.__name__}")
