"""Pruebas de la base de series (datos/series.db) sin conectarse al BCRA: la API se reemplaza
por una falsa y la base se crea en una carpeta temporal.
Correr con:
    python -m tests.test_series
"""
import tempfile
from datetime import date, timedelta
from pathlib import Path

import config
from admin_datos import series as db
from carga_datos import series as carga
from conexiones import bcra
from conexiones.http import ErrorAPI


PUBLICADO_HASTA = date.today() + timedelta(days=40)


def _listado_falso():
    return [{"id": 30, "primera_fecha": "2002-02-02", "ultima_fecha": PUBLICADO_HASTA.isoformat()}]


def _bcra_falso(pedidos):
    """CER inventado = 1 + días desde el 2/2/2002 / 1000, publicado hasta 40 días después de hoy.
    Como el BCRA real, responde con error 400 si se le piden fechas fuera de ese rango."""

    def obtener_serie(id_variable, desde, hasta):
        pedidos.append((desde, hasta))
        d, h = date.fromisoformat(desde), date.fromisoformat(hasta)
        if d < date(2002, 2, 2) or d > PUBLICADO_HASTA or h > PUBLICADO_HASTA:
            raise ErrorAPI("La API respondió con error 400 (falso).", 400)
        return [{"fecha": (d + timedelta(days=i)).isoformat(), "valor": 1 + ((d + timedelta(days=i)) - date(2002, 2, 2)).days / 1000}
                for i in range((h - d).days + 1)]
    return obtener_serie


def test_carga_completa_e_incremental():
    original_dir, original_api, original_listado = config.DATOS_DIR, bcra.obtener_serie, bcra.listar_variables
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR = Path(tmp)
        pedidos = []
        bcra.obtener_serie = _bcra_falso(pedidos)
        bcra.listar_variables = _listado_falso
        try:
            nuevos = carga.actualizar("CER")
            primera, ultima, cantidad = db.rango("CER")
            assert primera == "2002-02-02" and ultima == (date.today() + timedelta(days=40)).isoformat()
            assert nuevos == cantidad
            assert all((date.fromisoformat(h) - date.fromisoformat(d)).days < 366 for d, h in pedidos)  # de a un año
            assert db.valor("CER", date(2022, 5, 13)) == 1 + (date(2022, 5, 13) - date(2002, 2, 2)).days / 1000
            pedidos.clear()
            assert carga.actualizar("CER") == 0                      # ya está al día: no guarda nada nuevo
            assert pedidos == []                                     # ni siquiera le pregunta al BCRA

            from tools import bonos                                   # la calculadora lee el CER de la base
            assert bonos._cer(date(2020, 8, 20)) == db.valor("CER", date(2020, 8, 20))
        finally:
            config.DATOS_DIR, bcra.obtener_serie, bcra.listar_variables = original_dir, original_api, original_listado


def test_series_definidas():
    """CER (id 30) y TAMAR de bancos privados en TNA (id 44, no la 45 que es la TEA)."""
    assert carga.SERIES["CER"] == 30 and carga.SERIES["TAMAR"] == 44 and carga.SERIES["A3500"] == 5


def test_fichas_sin_cer_inicial():
    """Las fichas CER tienen fecha de emisión y no traen el CER inicial."""
    from renta_fija import leer_fichas
    cer = [f for f in leer_fichas.todas() if f["familia"].startswith("cer")]
    assert cer and all(isinstance(f["emision"], date) and "cer_inicial" not in f for f in cer)


if __name__ == "__main__":
    for prueba in (test_carga_completa_e_incremental, test_series_definidas, test_fichas_sin_cer_inicial):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de la base de series pasaron.")
