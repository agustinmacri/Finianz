"""Pruebas de la revisión periódica de avisos del Tesoro, sin internet ni modelo.
Correr con:
    python -m tests.test_avisos_tesoro
"""
import tempfile
from pathlib import Path

from carga_datos import avisos_tesoro as at
from carga_datos import fichas_documentos as fd


def _resumen(direccion):
    return {"documento": "llamado a licitación" if "llamado" in direccion else "resultado de licitación",
            "fecha": "2026-11-18", "ya_cargados": ["TZXD7"], "vencidos": [], "nuevos": [], "completados": [],
            "sin_familia": [], "descartados": []}


def test_lee_los_nuevos_y_recuerda_hasta_donde():
    original_registro, original_borradores = at.REGISTRO, fd.BORRADORES
    with tempfile.TemporaryDirectory() as tmp:
        at.REGISTRO = Path(tmp) / "avisos_tesoro.json"
        fd.BORRADORES = Path(tmp) / "borradores" / "borradores.toml"
        publicados = {at.url("llamado", 17), at.url("llamado", 19),          # el 18 no existe: hay un salto
                      at.url("resultado", 18)}
        leidos = []
        try:
            informe = at.revisar(lector=lambda d: leidos.append(d) or _resumen(d), comprobar=lambda d: d in publicados)
            assert leidos == [at.url("llamado", 17), at.url("llamado", 19), at.url("resultado", 18)]
            assert at.cargar_registro()["series"] == {"llamado": 19, "resultado": 18}
            assert "[llamado 17]" in informe[0] and "Ya tienen ficha (no se tocan): TZXD7" in informe[0]

            # La segunda vez no hay nada nuevo: no relee
            leidos.clear()
            informe = at.revisar(lector=lambda d: leidos.append(d) or _resumen(d), comprobar=lambda d: d in publicados)
            assert leidos == [] and informe[0].startswith("No hay avisos nuevos")

            # Si el lector falla (por ejemplo, el modelo saturado), no avanza: se reintenta la próxima vez
            publicados.add(at.url("resultado", 19))
            def falla(d):
                raise RuntimeError("503 modelo saturado")
            informe = at.revisar(lector=falla, comprobar=lambda d: d in publicados)
            assert "Se reintenta" in informe[0] and at.cargar_registro()["series"]["resultado"] == 18
            at.revisar(lector=lambda d: leidos.append(d) or _resumen(d), comprobar=lambda d: d in publicados)
            assert leidos == [at.url("resultado", 19)] and at.cargar_registro()["series"]["resultado"] == 19

            # Si no se puede consultar la página (sin conexión), tampoco se da por inexistente
            def sin_red(d):
                raise ConnectionError("sin conexión")
            informe = at.revisar(lector=lambda d: _resumen(d), comprobar=sin_red)
            assert all("no se pudo consultar" in r for r in informe) and at.cargar_registro()["series"]["llamado"] == 19
            assert len(at.cargar_registro()["leidos"]) == 4
        finally:
            at.REGISTRO, fd.BORRADORES = original_registro, original_borradores


def test_direcciones():
    assert at.url("llamado", 16) == ("https://www.argentina.gob.ar/noticias/llamado-licitacion-de-instrumentos-del-tesoro-"
                                     "nacional-denominados-en-pesos-y-en-dolares-16")
    assert at.url("resultado", 17).endswith("resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-17")


if __name__ == "__main__":
    for prueba in (test_lee_los_nuevos_y_recuerda_hasta_donde, test_direcciones):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de los avisos del Tesoro pasaron.")
