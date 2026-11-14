"""Pruebas de los caminos de TAMAR y de tipo de cambio, sus escenarios y las herramientas de proyección.
Correr con:
    python -m tests.test_proyecciones
"""
import tempfile
from datetime import date
from pathlib import Path

import config
from tools import proyecciones as pr


def test_leer_tasas():
    assert pr.leer_tasa("24%") == 0.24 and pr.leer_tasa("24") == 0.24 and pr.leer_tasa("0.24") == 0.24
    assert pr.leer_variacion("1.5%") == 0.015 and pr.leer_variacion("1.5") == 0.015 and pr.leer_variacion("0.015") == 0.015


def test_escenarios_y_caminos():
    original_dir, original_esc = config.DATOS_DIR, pr.ESCENARIOS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR, pr.ESCENARIOS_DIR = Path(tmp), Path(tmp)
        (Path(tmp) / "tamar.toml").write_text(
            '[[escenario]]\nnombre = "baja"\ndescripcion = "x"\nmensual = { "2026-12" = 0.23, "2027-01" = 0.22 }\nresto = 0.20\n',
            encoding="utf-8")
        (Path(tmp) / "dolar_mep.toml").write_text(
            '[[escenario]]\nnombre = "salto"\ndescripcion = "x"\nnivel = { "2027-01" = 1600.0 }\n'
            'mensual = { "2027-02" = 0.02 }\nresto = 0.01\n', encoding="utf-8")
        try:
            camino, _ = pr.camino_tamar("escenario:baja", date(2026, 11, 13))
            assert camino((2026, 12)) == 0.23 and camino((2027, 1)) == 0.22 and camino((2028, 5)) == 0.20
            assert camino((2026, 11)) == 0.23                                    # antes del primero, el primero
            plana, _ = pr.camino_tamar("tna:21%", date(2026, 11, 13))
            assert plana((2030, 1)) == 0.21
            from tools import bonos
            originales = bonos._precio
            bonos._precio = lambda t, f: ({"AL30": 87000.0, "AL30D": 60.0, "AL30C": 58.0}[t], "prueba")
            try:
                nivel, _, hoy, _ = pr.camino_dolar("mep", "escenario:salto", date(2026, 11, 13))
                assert hoy == 1450.0 and abs(nivel(date(2027, 1, 15)) - 1600.0) < 1e-9
                assert abs(nivel(date(2027, 2, 15)) - 1632.0) < 1e-9                # +2% en febrero
                assert abs(nivel(date(2027, 2, 15) + (date(2027, 4, 1) - date(2027, 2, 15))) -
                           1632.0 * 1.01 ** ((date(2027, 4, 1) - date(2027, 2, 15)).days / 30.4375)) < 1e-9
                mensual, _, hoy_ccl, _ = pr.camino_dolar("ccl", "mensual:1%", date(2026, 11, 13))
                assert abs(hoy_ccl - 87000 / 58) < 1e-9
                assert abs(mensual(date(2027, 11, 13)) - hoy_ccl * 1.01 ** (365 / 30.4375)) < 1e-9
            finally:
                bonos._precio = originales
            try:
                pr.camino_dolar("mep", "rem", date(2026, 11, 13))
                raise AssertionError("el MEP no tiene REM")
            except (ValueError, KeyError):
                pass
        finally:
            config.DATOS_DIR, pr.ESCENARIOS_DIR = original_dir, original_esc


def test_rem_oficial_sin_el_mes_en_curso():
    """El A3500 del REM arranca en el valor de hoy y no usa el promedio esperado del mes en curso."""
    from carga_datos import rem
    from tools import bonos
    original = config.DATOS_DIR
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR = Path(tmp)
        originales = bonos._a3500
        bonos._a3500 = lambda op: (1452.0, op, False)
        try:
            rem.cargar()
            nivel, _, hoy, _ = pr.camino_dolar("oficial", "rem", date(2026, 11, 13))
            assert abs(nivel(date(2026, 12, 15)) - 1590) < 1e-9 and hoy == 1452.0
            assert 1452.0 < nivel(date(2026, 11, 30)) < 1590                    # sin saltar al 1.574 de noviembre
        finally:
            config.DATOS_DIR, bonos._a3500 = original, originales


if __name__ == "__main__":
    for prueba in (test_leer_tasas, test_escenarios_y_caminos, test_rem_oficial_sin_el_mes_en_curso):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de proyecciones pasaron.")
