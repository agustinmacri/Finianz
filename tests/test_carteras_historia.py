"""Pruebas de la etapa 2 de carteras: variaciones, backtest y proyección por escenarios, con series simuladas.
Correr con:
    python -m tests.test_carteras_historia
"""
from datetime import date, timedelta

from carteras import historia, proyeccion, valuar
from carteras.excel import Cartera, Liquidez
from carteras.valuar import Contexto

HOY = date(2026, 11, 16)
INICIO = date(2026, 5, 18)
DIAS = [INICIO + timedelta(days=i) for i in range((HOY - INICIO).days + 1) if (INICIO + timedelta(days=i)).weekday() < 5]


def _serie(f):
    return historia.Serie({d: f(d) for d in DIAS})


MEP = lambda d: 1200 + (d - INICIO).days          # sube 1 peso por día
SERIES = {"AL30": _serie(lambda d: MEP(d) * 60), "AL30D": _serie(lambda d: 60.0), "AL30C": _serie(lambda d: 60.0 * MEP(d) / (MEP(d) * 1.03)),
          "BONO": _serie(lambda d: 100.0), "NUEVO": historia.Serie({d: 50.0 for d in DIAS if d >= date(2026, 8, 3)}),
          "GGAL": _serie(lambda d: 5000.0 + (d - INICIO).days * 10)}
CUPON = date(2026, 8, 17)
historia.cierres = lambda t: SERIES[t.upper()]
historia.serie = lambda variable: _serie(lambda d: 36.5) if variable == "TAMAR" else historia.Serie({})
historia.flujos_pesos = lambda fila, desde, hasta, fx: [(CUPON, 5.0, False)] if fila["ticker"] == "BONO" and desde < CUPON <= hasta else []


def _fila(ticker, total, categoria="Renta Fija", emision=date(2020, 1, 1), **extra):
    return {"ticker": ticker, "descripcion": ticker, "categoria": categoria, "subclase": extra.pop("subclase", "Tasa fija"),
            "moneda_activo": extra.pop("moneda_activo", "Pesos"), "total_pesos": total, "_tipo_fx": None,
            "_legs": [({"emision": emision, "familia": "tasa_fija_capitalizable"}, {})], "_px": 100.0,
            "precio_pesos": extra.pop("precio_pesos", 100.0), "nominales": extra.pop("nominales", total / 1.0), **extra}


def test_backtest():
    v = {"fecha": HOY, "fx": {"mep": MEP(HOY), "ccl": MEP(HOY) * 1.03},
         "filas": [_fila("BONO", 600_000.0), _fila("NUEVO", 300_000.0, emision=date(2026, 8, 1)),
                   {"ticker": "", "categoria": "Liquidez", "liquidez": True, "total_pesos": 100_000.0,
                    "_liq": Liquidez("Liquidez", "pesos", 100_000.0)}]}
    r = historia.backtest(v, INICIO)
    p = r["puntos"]
    assert p[0]["fecha"] == INICIO and abs(p[0]["pesos"] - 1_000_000) < 1e-6
    # BONO: precio fijo 100, cupón de 5 por 100 VN reinvertido: 600.000 → 630.000
    # NUEVO: TAMAR 36,5% TNA (0,1% diario) hasta su primer precio (3/8), después precio fijo
    dias_tamar = (date(2026, 8, 3) - INICIO).days
    nuevo = 300_000 * 1.001 ** dias_tamar
    assert abs(p[-1]["pesos"] - (630_000 + nuevo + 100_000)) < 1e-3, p[-1]["pesos"]
    assert abs(p[-1]["mep"] - p[-1]["pesos"] / MEP(DIAS[-1])) < 1e-9
    assert any("NUEVO" in a for a in r["avisos"])
    assert r["resumen"]["pesos"]["rendimiento"] > 0 and r["resumen"]["mep"]["rendimiento"] < r["resumen"]["pesos"]["rendimiento"]


def test_variaciones():
    fila = _fila("GGAL", 200 * 6700.0, categoria="Renta Variable", subclase="Acciones", precio_pesos=6700.0, nominales=200)
    v = {"fecha": HOY, "moneda": "pesos", "fx": {"mep": MEP(HOY), "ccl": MEP(HOY) * 1.03}, "filas": [fila]}
    r = historia.variaciones(v)
    d0 = HOY - timedelta(days=30)                                  # sábado: toma el cierre del viernes
    hace_un_mes = SERIES["GGAL"].en(d0)
    assert hace_un_mes == 5000.0 + (date(2026, 10, 16) - INICIO).days * 10
    assert abs(r["filas"][0]["precio"]["Mes"] - (6700 / hace_un_mes - 1)) < 1e-12
    assert r["filas"][0]["precio"]["12 meses"] is None          # no hay precios de hace un año
    assert abs(r["cartera"]["precio"]["Mes"] - r["filas"][0]["precio"]["Mes"]) < 1e-12
    r = historia.variaciones(v, "mep")                            # en dólares: precio sobre el MEP de cada día
    mep_d0 = SERIES["AL30"].en(d0) / SERIES["AL30D"].en(d0)
    assert abs(r["filas"][0]["precio"]["Mes"] - ((6700 / MEP(HOY)) / (hace_un_mes / mep_d0) - 1)) < 1e-12
    bono = _fila("BONO", 100_000.0, nominales=100_000.0)
    v["filas"] = [bono]
    original = historia.flujos_pesos
    historia.flujos_pesos = lambda fila, desde, hasta, fx: [(HOY - timedelta(days=10), 5.0, False)]
    try:
        r = historia.variaciones(v)
    finally:
        historia.flujos_pesos = original
    f = r["filas"][0]
    assert f["precio"]["12 meses"] is None and f["precio"]["Mes"] == 0
    assert abs(f["total"]["Mes"] - 0.05) < 1e-12 and f["total"]["Semana"] == 0      # el cupón cayó hace 10 días


def test_proyeccion():
    t0 = date(2026, 11, 17)
    ctx = Contexto(HOY, t0, HOY, {"mep": 1450.0, "ccl": 1500.0}, [])
    mensual = 0.02
    nivel = lambda base: (lambda d: base * (1 + mensual) ** ((d - HOY).days / 30))
    valuar.Proyecciones.dolar = lambda self, tipo: nivel(ctx.fx[tipo])
    lecap = {"familia": "tasa_fija_capitalizable", "vencimiento": date(2027, 3, 31)}
    filas = [{"categoria": "Renta Fija", "subclase": "Tasa fija", "moneda_activo": "Pesos", "total_pesos": 1_000_000.0,
              "_f": lecap, "_m": {"tea": 0.30}, "_legs": [(lecap, {"tea": 0.30})], "_px": 100.0, "_tipo_fx": None,
              "_vencimiento": lecap["vencimiento"]},
             {"categoria": "Renta Variable", "subclase": "Acciones", "moneda_activo": "Pesos", "total_pesos": 500_000.0},
             {"categoria": "Liquidez", "subclase": "Liquidez", "moneda_activo": "Pesos", "total_pesos": 100_000.0,
              "liquidez": True, "tir_proyectada": 0.0, "_liq": Liquidez("Liquidez", "pesos", 100_000.0)}]
    v = {"_ctx": ctx, "filas": filas}
    r = proyeccion.proyectar(v, Cartera("x", [], {}), date(2027, 2, 17), {"Base": {}})
    puntos = r["escenarios"]["Base"]["puntos"]
    final = puntos[-1]
    anios = (date(2027, 2, 17) - t0).days / 365
    accion = 500_000 * nivel(1450.0)(date(2027, 2, 17)) / nivel(1450.0)(t0)
    esperado = 1_000_000 * 1.30 ** anios + accion + 100_000
    assert abs(final["pesos"] - esperado) < 1e-6, (final["pesos"], esperado)
    # En MEP, la acción queda constante en dólares
    assert abs(final["mep"] - (1_000_000 * 1.30 ** anios + 100_000) / nivel(1450.0)(date(2027, 2, 17))
               - 500_000 / nivel(1450.0)(t0)) < 1e-6
    # Después del vencimiento de la Lecap, lo cobrado se reparte entre la acción y la liquidez: el total se conserva
    r = proyeccion.proyectar(v, Cartera("x", [], {}), date(2027, 6, 30), {"Base": {}})
    puntos = r["escenarios"]["Base"]["puntos"]
    venc = next(p for p in puntos if p["fecha"] == lecap["vencimiento"])
    anios_v = (lecap["vencimiento"] - t0).days / 365
    accion_v = 500_000 * nivel(1450.0)(lecap["vencimiento"]) / nivel(1450.0)(t0)
    assert abs(venc["pesos"] - (1_000_000 * 1.30 ** anios_v + accion_v + 100_000)) < 1e-6
    assert "acciones" in r["aclaracion"].lower()
    disponibles = proyeccion.escenarios_disponibles(Cartera("x", [], {"inflacion": "mensual:2%"}))
    assert disponibles["Supuestos de la cartera"]["inflacion"] == "mensual:2%" and "REM" in disponibles


if __name__ == "__main__":
    for prueba in (test_backtest, test_variaciones, test_proyeccion):
        prueba()
        print(f"OK {prueba.__name__}")
