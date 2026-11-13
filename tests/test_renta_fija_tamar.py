"""Pruebas de la calculadora TAMAR contra la planilla de Agustin (ejemplo_tamar.xlsx, 13/11/2026).

La planilla proyectaba la TAMAR a mano (24,22% y 24%) y restaba un 24,19% fijo para el spread; la
herramienta usa el promedio de los últimos 5 días hábiles publicados. Por eso la TAMAR promedio de
cada bono se toma de la planilla como dato de entrada y se verifica el resto de la cuenta.
Correr con:
    python -m tests.test_renta_fija_tamar
"""
import tempfile
from datetime import date, timedelta
from pathlib import Path

from renta_fija import leer_fichas
from renta_fija.calculadoras import tamar

LIQUIDACION = date(2026, 11, 16)          # operación del 13/11/2026, T+1
TAMAR_SPREAD = 0.2419                     # TAMAR que restaba la planilla para el spread

# ticker, TAMAR promedio (planilla), emisión, vencimiento, precio, TEM, pago final, TNA, TEA, TNA 30 (NOMINAL 12), TEM 30
CASOS = [
    ("TTD26", 0.3197753333333333, "2025-01-29", "2026-12-15", 176.0, 0.026629640757246387, 180.79688259083844, 0.34303725424297193, 0.4027656502076371, 0.34326367059386076, 0.02820797728094404),
    ("TMF27", 0.24702681451612904, "2026-02-13", "2027-02-26", 127.4, 0.025984803080808083, 137.5684588387648, 0.28561328193963803, 0.3162509466408614, 0.27795783031296306, 0.02284225257566086),
    ("TML27", 0.23838460076045626, "2026-06-30", "2027-07-30", 112.85, 0.024350068431355343, 136.71910610722543, 0.301569551988859, 0.3146404667646654, 0.2767052511977921, 0.02273933308492282),
    ("TMG27", 0.23805801749271135, "2026-04-01", "2027-08-31", 122.0, 0.024822255772648516, 151.71388194371036, 0.30867392160323426, 0.3181819511352326, 0.2794578523394282, 0.02296550328623903),
    ("TMF28", 0.23790889737991264, "2026-04-20", "2028-02-25", 112.55, 0.025225976005227357, 173.71387003028775, 0.4256536925134836, 0.40487029921783124, 0.3448058853418825, 0.02833468558535457),
    ("TMG28", 0.23832352173913043, "2026-04-30", "2028-08-31", 108.05, 0.025593381161336914, 202.91112697773298, 0.48998030624720956, 0.42148573352131513, 0.3569072856075053, 0.0293289286417322),
    ("TXMJ8", 0.23842749042145592, "2026-05-15", "2028-06-30", 102.2, 0.02235604014086312, 175.73378489309883, 0.4436159802913737, 0.3968170155675359, 0.33889321701751296, 0.027848899804917115),
    ("TXMJ9", 0.23864033333333332, "2026-04-30", "2029-06-29", 92.95, 0.022373756640148956, 231.6583784756334, 0.569755167595877, 0.41716696615991355, 0.35377435077334507, 0.02907153006424168),
    ("TXMD9", 0.23913657120743034, "2026-06-12", "2029-12-14", 85.9, 0.02241506214877287, 254.08899060733475, 0.6358152694689914, 0.4221549345995448, 0.35739195877638164, 0.02936874879141471),
    ("TXMJ0", 0.23913657120743034, "2026-06-12", "2030-06-28", 82.8, 0.02241506214877287, 293.2526818964056, 0.7028182997748381, 0.41861760202295284, 0.35482765091046087, 0.02915806817750699),
]


def test_como_la_planilla():
    for t, prom, emi, vto, precio, tem_, pf, tna, tea, _nominal, tem30 in CASOS:
        f = leer_fichas.ficha(t, "tamar_capitalizable")
        assert f["emision"].isoformat() == emi and f["vencimiento"].isoformat() == vto, t
        r = tamar.calcular(precio, prom, f["margen"], f["emision"], f["vencimiento"], LIQUIDACION, TAMAR_SPREAD)
        for clave, esperado in (("tem_bono", tem_), ("pago_final", pf), ("tna", tna), ("tea", tea), ("tem_30", tem30)):
            assert abs(r[clave] / esperado - 1) < 1e-9, (t, clave, r[clave], esperado)


def test_tna_30_y_spread():
    """TNA 30 d = ((1+TIR)^(30/365) − 1) × 365/30 (la planilla usaba NOMINAL(TEA;12): difiere en menos de 3 pb)."""
    for t, prom, emi, vto, precio, _tem, _pf, _tna, tea, nominal, tem30 in CASOS:
        f = leer_fichas.ficha(t, "tamar_capitalizable")
        r = tamar.calcular(precio, prom, f["margen"], f["emision"], f["vencimiento"], LIQUIDACION, TAMAR_SPREAD)
        assert abs(r["tna_30"] - ((1 + tea) ** (30 / 365) - 1) * 365 / 30) < 1e-12, t
        assert abs(r["tna_30"] - tem30 * 365 / 30) < 1e-12, t
        assert abs(r["tna_30"] - nominal) < 0.0003, (t, r["tna_30"], nominal)
        assert abs(r["spread"] - (r["tna_30"] - TAMAR_SPREAD)) < 1e-15, t


def test_promedio_con_estimacion():
    assert tamar.tamar_del_bono([0.30, 0.20], 2, 0.25) == 0.25
    assert abs(tamar.tamar_del_bono([0.30], 3, 0.20) - 0.225) < 1e-15


def test_ventana_y_dias_estimados():
    """Con una TAMAR inventada en una base temporal: la ventana, los días publicados y los estimados."""
    import config
    from admin_datos import series as db_series
    from tools import bonos
    original = config.DATOS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR = Path(tmp)
        try:
            bonos._asegurar_feriados(date(2025, 1, 1), date(2030, 12, 31))
            corte = date(2026, 11, 13)
            habiles = bonos.feriados.dias_habiles_entre(date(2025, 1, 2), corte, "BYMA")
            db_series.guardar("TAMAR", [{"fecha": d.isoformat(), "valor": 30.0 if d < date(2026, 11, 1) else 24.0}
                                        for d in habiles], "prueba")
            db_series.guardar("CER", [{"fecha": (date(2026, 1, 1) + timedelta(days=i)).isoformat(), "valor": 800.0}
                                      for i in range(365)], "prueba")            # para la parte CER del dual, sin red
            f = leer_fichas.ficha("TMF27", "tamar_capitalizable")
            d = bonos._datos_tamar(f, corte)
            assert d["inicio"] == date(2026, 1, 30) and d["fin"] == date(2027, 2, 12)        # como la planilla
            assert d["referencia"] == 0.24                                                    # últimos 5: 24%
            estimados = bonos.feriados.dias_habiles_entre(corte + timedelta(days=1), d["fin"], "BYMA")
            assert d["a_estimar"] == len(estimados)
            assert len(d["conocidas"]) == len([h for h in habiles if h >= d["inicio"]])
            esperado = (sum(d["conocidas"]) + 0.24 * len(estimados)) / (len(d["conocidas"]) + len(estimados))
            assert abs(d["tamar_bono"] - esperado) < 1e-15
            texto = bonos.calcular_bono("TXMJ8", precio=102.2, fecha="2026-11-13")
            assert "Calculado como CER" in texto and "Calculado como TAMAR" in texto
        finally:
            config.DATOS_DIR = original


if __name__ == "__main__":
    for prueba in (test_como_la_planilla, test_tna_30_y_spread, test_promedio_con_estimacion, test_ventana_y_dias_estimados):
        prueba()
        print(f"OK  {prueba.__name__}")
    print(f"Todas las pruebas de TAMAR pasaron ({len(CASOS)} bonos de la planilla).")
