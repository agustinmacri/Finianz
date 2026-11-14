"""Pruebas del lector de fichas desde documentos, sin llamar al modelo: el extractor se reemplaza por uno que
devuelve lo que diría el modelo para el llamado a licitación del 15/04/2026 y su resultado.
Correr con:
    python -m tests.test_fichas_documentos
"""
import shutil
import tempfile
import tomllib
from datetime import date
from pathlib import Path

from carga_datos import fichas_documentos as fd
from renta_fija import leer_fichas
from tools import lector_fichas

HOY = date(2026, 4, 15)   # el día del llamado: todavía no venció nada

LLAMADO = fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2026-04-13", instrumentos=[
    fd.Instrumento(nombre="LECAP capitalizable con vencimiento 14 de agosto de 2026", familia="tasa_fija_capitalizable",
                   tipo="LECAP", emision="2026-04-17", vencimiento="2026-08-14",
                   pendiente=["cupon: se define en la licitación", "ticker: no figura en el llamado"],
                   cita="Interés capitalizable mensualmente, base 30/360. Amortización íntegra al vencimiento."),
    fd.Instrumento(nombre="BONCER TZXS8 (reapertura)", ticker="TZXS8", reapertura=True, familia="cer_cero_cupon",
                   tipo="BONCER", vencimiento="2028-09-29"),
    fd.Instrumento(nombre="Bono TAMAR con vencimiento 25 de febrero de 2028 (canje)", familia="tamar_capitalizable",
                   tipo="BONO TAMAR", emision="2026-04-20", vencimiento="2028-02-25",
                   pendiente=["margen: se define en la licitación"]),
    fd.Instrumento(nombre="BONAR 2027 6%", ticker="AO27", reapertura=True, familia="hard_dollar", tipo="BONAR", ley="AR",
                   vencimiento="2027-10-29", pendiente=["emision: no figura (reapertura)", "pagos: no figuran"]),
])
RESULTADO = fd.Documento(tipo_documento="resultado de licitación", fecha_documento="2026-04-15", instrumentos=[
    fd.Instrumento(nombre="LECAP 14/08/2026", ticker="S14G6", familia="tasa_fija_capitalizable", tipo="LECAP",
                   vencimiento="2026-08-14", cupon=0.0215),
    fd.Instrumento(nombre="TAMAR 25/02/2028", ticker="TMF28", familia="tamar_capitalizable", tipo="BONO TAMAR",
                   vencimiento="2028-02-25", margen=0.065),
])


def test_borradores_aprobacion():
    original_carpeta, original_borradores = leer_fichas.CARPETA, fd.BORRADORES
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "fichas"
        shutil.copytree(original_carpeta, carpeta, ignore=shutil.ignore_patterns("borradores"))
        leer_fichas.CARPETA, fd.BORRADORES = carpeta, carpeta / "borradores" / "borradores.toml"
        documento = Path(tmp) / "llamado.txt"
        documento.write_text("Llamado a licitación del Tesoro. " * 20, encoding="utf-8")
        try:
            r = fd.leer(str(documento), extractor=lambda texto: LLAMADO, hoy=HOY)
            assert "TZXS8" in r["ya_cargados"]                                  # reapertura de un bono cargado
            assert "AO27" in r["nuevos"] and "tasa_fija_capitalizable-2026-08-14" in r["nuevos"]
            lecap = next(b for b in fd.pendientes() if b["clave"] == "tasa_fija_capitalizable-2026-08-14")
            assert lecap["revisado"] is False and "cupon" not in lecap and len(lecap["pendiente"]) == 2

            r = fd.leer(str(documento), extractor=lambda texto: RESULTADO, hoy=HOY)          # el resultado completa
            claves = dict(r["completados"])
            assert set(claves["S14G6"]) >= {"ticker", "cupon"}
            assert "TMF28" in r["ya_cargados"] and r["descartados"] == ["tamar_capitalizable-2028-02-25"]  # ya estaba cargado
            lecap = next(b for b in fd.pendientes() if b["clave"] == "S14G6")
            assert lecap["cupon"] == 0.0215 and lecap.get("pendiente") is None    # ya no queda nada pendiente

            assert "No hay ningún borrador" in _error(lambda: fd.aprobar("TMF28", hoy=HOY))
            assert "falta el campo 'emision'" in _error(lambda: fd.aprobar("AO27", hoy=HOY))
            assert "S14G6 aprobado" in fd.aprobar("S14G6", hoy=HOY)
            nueva = leer_fichas.ficha("S14G6")
            assert nueva["revisado"] is True and nueva["cupon"] == 0.0215 and "cita" not in nueva
            assert "S14G6" not in [b["clave"] for b in fd.pendientes()]
            tomllib.loads((carpeta / "tasa_fija.toml").read_text(encoding="utf-8"))   # el archivo sigue siendo válido
            assert "descartado" in fd.descartar("AO27")

            # Meses después: la Lecap de agosto ya venció. No se carga y el borrador que quedaba se saca solo.
            fd.leer(str(documento), extractor=lambda texto: LLAMADO, hoy=HOY)
            assert "tasa_fija_capitalizable-2026-08-14" in [b["clave"] for b in fd.pendientes()]
            r = fd.leer(str(documento), extractor=lambda texto: LLAMADO, hoy=date(2026, 11, 14))
            assert any(v.startswith("tasa_fija_capitalizable-2026-08-14 (borrador") for v in r["vencidos"])
            assert any("14/08/2026" in v and "borrador" not in v for v in r["vencidos"])
            assert "tasa_fija_capitalizable-2026-08-14" not in [b["clave"] for b in fd.pendientes()]
            assert "ya venció" in _error(lambda: fd.aprobar("tasa_fija_capitalizable-2026-08-14", hoy=date(2026, 11, 14))) \
                or "No hay ningún borrador" in _error(lambda: fd.aprobar("tasa_fija_capitalizable-2026-08-14", hoy=date(2026, 11, 14)))

            # Desde el agente: ver, aprobar (con la misma validación) y descartar.
            assert "AO27" in lector_fichas.ver_borradores()
            assert "No se aprobó AO27" in lector_fichas.aprobar_ficha("AO27")              # le falta la emisión
            nueva_lecap = fd.Documento(tipo_documento="resultado de licitación", fecha_documento="2026-11-12", instrumentos=[
                fd.Instrumento(nombre="LECAP 14/05/2027", ticker="S14Y7", familia="tasa_fija_capitalizable", tipo="LECAP",
                               emision="2026-11-14", vencimiento="2027-05-14", cupon=0.019, base="30/360")])
            fd.leer(str(documento), extractor=lambda texto: nueva_lecap, hoy=date(2026, 11, 14))
            salida = lector_fichas.aprobar_ficha("S14Y7")
            assert "S14Y7 aprobado" in salida, salida
            assert "vía agente" in leer_fichas.ficha("S14Y7")["fuente"]
            assert "descartado" in lector_fichas.descartar_borrador("tamar_capitalizable-2028-02-25")
        finally:
            leer_fichas.CARPETA, fd.BORRADORES = original_carpeta, original_borradores


def _error(funcion) -> str:
    try:
        funcion()
    except (ValueError, leer_fichas.ErrorFicha) as e:
        return str(e)
    return ""


def test_texto_html():
    html = "<html><head><style>x{}</style><script>var a=1</script></head><body><h1>Llamado</h1><p>LECAP <b>S14G6</b></p></body></html>"
    texto = fd._html_a_texto(html)
    assert "Llamado" in texto and "S14G6" in texto and "var a" not in texto


def test_toml_ida_y_vuelta():
    from datetime import date
    ficha = {"ticker": "AO27", "familia": "hard_dollar", "emision": date(2025, 10, 29), "vencimiento": date(2027, 10, 29),
             "tramos": [{"desde": date(2025, 10, 29), "tasa": 0.06}], "revisado": False, "fuente": 'dice "6%"'}
    leido = tomllib.loads(fd.a_toml(ficha))["bono"][0]
    assert leido == ficha


if __name__ == "__main__":
    for prueba in (test_borradores_aprobacion, test_texto_html, test_toml_ida_y_vuelta):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas del lector de fichas pasaron.")
