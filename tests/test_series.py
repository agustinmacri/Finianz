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


def _bcra_falso(pedidos):
    """CER inventado = 1 + días desde el 2/2/2002 / 1000, publicado hasta 40 días después de hoy."""
    publicado_hasta = date.today() + timedelta(days=40)

    def obtener_serie(id_variable, desde, hasta):
        pedidos.append((desde, hasta))
        d, h = date.fromisoformat(desde), min(date.fromisoformat(hasta), publicado_hasta)
        if d > h:
            raise ErrorAPI(f"El BCRA no devolvió datos para la variable {id_variable} entre {desde} y {hasta}.")
        return [{"fecha": (d + timedelta(days=i)).isoformat(), "valor": 1 + ((d + timedelta(days=i)) - date(2002, 2, 2)).days / 1000}
                for i in range((h - d).days + 1)]
    return obtener_serie


def test_carga_completa_e_incremental():
    original_dir, original_api = config.DATOS_DIR, bcra.obtener_serie
    with tempfile.TemporaryDirectory() as tmp:
        config.DATOS_DIR = Path(tmp)
        pedidos = []
        bcra.obtener_serie = _bcra_falso(pedidos)
        try:
            nuevos = carga.actualizar("CER")
            primera, ultima, cantidad = db.rango("CER")
            assert primera == "2002-02-02" and ultima == (date.today() + timedelta(days=40)).isoformat()
            assert nuevos == cantidad
            assert all((date.fromisoformat(h) - date.fromisoformat(d)).days < 366 for d, h in pedidos)  # de a un año
            assert db.valor("CER", date(2022, 5, 13)) == 1 + (date(2022, 5, 13) - date(2002, 2, 2)).days / 1000
            pedidos.clear()
            assert carga.actualizar("CER") == 0                      # ya está al día: no guarda nada nuevo
            assert len(pedidos) == 1 and pedidos[0][0] == (date.today() + timedelta(days=41)).isoformat()

            from tools import bonos                                   # la calculadora lee el CER de la base
            assert bonos._cer(date(2020, 8, 20)) == db.valor("CER", date(2020, 8, 20))
        finally:
            config.DATOS_DIR, bcra.obtener_serie = original_dir, original_api


def test_fichas_sin_cer_inicial():
    """Las fichas CER tienen fecha de emisión y no traen el CER inicial."""
    from renta_fija import leer_fichas
    cer = [f for f in leer_fichas.leer_todas().values() if f["familia"].startswith("cer")]
    assert cer and all(isinstance(f["emision"], date) and "cer_inicial" not in f for f in cer)


if __name__ == "__main__":
    for prueba in (test_carga_completa_e_incremental, test_fichas_sin_cer_inicial):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de la base de series pasaron.")
