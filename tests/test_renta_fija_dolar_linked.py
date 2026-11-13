"""Pruebas de la calculadora dollar linked (bullet del Tesoro).
Correr con:
    python -m tests.test_renta_fija_dolar_linked
"""
import tempfile
from datetime import date, timedelta
from pathlib import Path

from renta_fija import leer_fichas
from renta_fija.calculadoras import dolar_linked


def test_cuentas():
    liq, vto = date(2026, 11, 16), date(2027, 6, 30)            # TZV27
    r = dolar_linked.calcular_bullet(140_000.0, 1450.0, liq, vto)
    plazo = (vto - liq).days
    p = 140_000 / 1450
    assert abs(r["precio_usd"] - p) < 1e-12 and r["plazo_residual"] == plazo
    tna = (100 / p - 1) * 365 / plazo
    assert abs(r["tna"] - tna) < 1e-15
    assert abs(r["tea"] - ((100 / p) ** (365 / plazo) - 1)) < 1e-12
    assert abs(r["tem"] - ((100 / p) ** (30 / plazo) - 1)) < 1e-12
    assert abs(r["duration"] - plazo / 365) < 1e-15


def test_fichas():
    dl = {f["ticker"] for f in leer_fichas.todas() if f["familia"] == "dolar_linked_bullet"}
    assert dl == {"D30N6", "D15E7", "D31M7", "TZV27", "TZV28", "TZVD8"}
    assert leer_fichas.ficha("TZVD8")["vencimiento"] == date(2028, 12, 15)


def test_a3500_del_dia_o_estimado():
    """Con el A3500 del día de concertación publicado se usa ese; si no, el del día hábil anterior (estimado)."""
    import config
    from admin_datos import series as db_series
    from tools import bonos
    original, original_carga = config.DATOS_DIR, bonos.carga_series.actualizar
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR = Path(tmp)
        bonos.carga_series.actualizar = lambda variable: 0            # sin conexión
        try:
            db_series.guardar("A3500", [{"fecha": "2026-11-12", "valor": 1440.0}], "prueba")
            assert bonos._a3500(date(2026, 11, 13)) == (1440.0, date(2026, 11, 12), True)
            db_series.guardar("A3500", [{"fecha": "2026-11-13", "valor": 1450.0}], "prueba")
            assert bonos._a3500(date(2026, 11, 13)) == (1450.0, date(2026, 11, 13), False)
            texto = bonos.calcular_bono("TZV27", precio=140000, fecha="2026-11-13")
            assert "Precio en dólares: 96.5517" in texto and "A3500 del día de concertación, 2026-11-13" in texto
        finally:
            config.DATOS_DIR, bonos.carga_series.actualizar = original, original_carga


if __name__ == "__main__":
    for prueba in (test_cuentas, test_fichas, test_a3500_del_dia_o_estimado):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de dollar linked pasaron.")
