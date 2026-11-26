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
fd.BUSCADOR = lambda ticker: []   # las pruebas no consultan PPI: por defecto, ningún ticker existe
fd.BUSCADOR_WEB = lambda consulta: []   # ni buscan en la web

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
            # El Bono TAMAR 25/02/2028 del llamado no trae ticker, pero coincide con el TMF28 cargado: no va al borrador
            assert any(y.startswith("tamar_capitalizable-2028-02-25 = TMF28") for y in r["ya_cargados"])
            assert "tamar_capitalizable-2028-02-25" not in r["nuevos"]
            lecap = next(b for b in fd.pendientes() if b["clave"] == "tasa_fija_capitalizable-2026-08-14")
            assert lecap["revisado"] is False and "cupon" not in lecap and len(lecap["pendiente"]) == 2

            r = fd.leer(str(documento), extractor=lambda texto: RESULTADO, hoy=HOY)          # el resultado completa
            claves = dict(r["completados"])
            assert set(claves["S14G6"]) >= {"ticker", "cupon"}
            assert "TMF28" in r["ya_cargados"] and r["descartados"] == []        # ya estaba cargado (y nunca fue borrador)
            lecap = next(b for b in fd.pendientes() if b["clave"] == "S14G6")
            assert lecap["cupon"] == 0.0215 and lecap.get("pendiente") is None    # ya no queda nada pendiente

            assert "No hay ningún borrador" in _error(lambda: fd.aprobar("TMF28", hoy=HOY))
            assert "es una reapertura y falta su fecha de emisión original" in _error(lambda: fd.aprobar("AO27", hoy=HOY))
            assert "S14G6 aprobado" in fd.aprobar("S14G6", hoy=HOY)
            nueva = leer_fichas.ficha("S14G6")
            assert nueva["revisado"] is True and nueva["cupon"] == 0.0215 and "cita" not in nueva
            assert "S14G6" not in [b["clave"] for b in fd.pendientes()]
            tomllib.loads((carpeta / "tasa_fija.toml").read_text(encoding="utf-8"))   # el archivo sigue siendo válido
            assert "descartado" in fd.descartar("AO27")

            # Releer el llamado (sin ticker) después de aprobar la Lecap: coincide con S14G6 y no vuelve al borrador
            r = fd.leer(str(documento), extractor=lambda texto: LLAMADO, hoy=HOY)
            assert any(y.startswith("tasa_fija_capitalizable-2026-08-14 = S14G6") for y in r["ya_cargados"])
            assert "tasa_fija_capitalizable-2026-08-14" not in [b["clave"] for b in fd.pendientes()]
            # Un borrador que vence mientras espera aprobación se saca solo
            fd._guardar_borradores(fd.pendientes() + [{"familia": "tasa_fija_capitalizable", "tipo": "LECAP",
                                                      "vencimiento": date(2026, 9, 30), "clave": "tasa_fija_capitalizable-2026-09-30",
                                                      "revisado": False, "fuente": "x"}])
            r = fd.leer(str(documento), extractor=lambda texto: LLAMADO, hoy=date(2026, 11, 14))
            assert any(v.startswith("tasa_fija_capitalizable-2026-09-30 (borrador") for v in r["vencidos"])
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
            assert "No hay" in lector_fichas.descartar_borrador("tamar_capitalizable-2028-02-25")   # nunca fue borrador
        finally:
            leer_fichas.CARPETA, fd.BORRADORES = original_carpeta, original_borradores


# Resultado del 11/11/2026 (argentina.gob.ar): reaperturas por precio y una letra TAMAR nueva licitada por margen.
RESULTADO_NOV = fd.Documento(tipo_documento="resultado de licitación", fecha_documento="2026-11-11", instrumentos=[
    fd.Instrumento(nombre="LECAP 29/01/2027", ticker="S29E7", reapertura=True, familia="tasa_fija_capitalizable",
                   tipo="LECAP", vencimiento="2027-01-29", variable_licitada="precio", valor_corte=1060.0, tirea=0.2808),
    fd.Instrumento(nombre="BONCER 30/06/2028", ticker="TZX28", reapertura=True, familia="cer_cero_cupon",
                   tipo="BONCER", vencimiento="2028-06-30", variable_licitada="precio", valor_corte=3650.0, tirea=0.105),
    fd.Instrumento(nombre="Letra TAMAR 30/04/2027 (nueva)", familia="tamar_capitalizable", tipo="LETRA TAMAR",
                   emision="2026-11-13", vencimiento="2027-04-30", variable_licitada="margen", valor_corte=0.025,
                   tirea=0.2987, pendiente=["ticker: no figura en el resultado"]),
    # Inventado para la prueba: un documento que dice otro margen para un bono ya aprobado.
    fd.Instrumento(nombre="TAMAR 26/02/2027", ticker="TMF27", reapertura=True, familia="tamar_capitalizable",
                   tipo="BONO TAMAR", vencimiento="2027-02-26", margen=0.07),
    fd.Instrumento(nombre="TAMAR 31/08/2027", ticker="TMG27", reapertura=True, familia="tamar_capitalizable",
                   tipo="BONO TAMAR", vencimiento="2027-08-31", margen=0.05),
])


def test_resultado_y_cambios():
    original_carpeta, original_borradores = leer_fichas.CARPETA, fd.BORRADORES
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "fichas"
        shutil.copytree(original_carpeta, carpeta, ignore=shutil.ignore_patterns("borradores"))
        leer_fichas.CARPETA, fd.BORRADORES = carpeta, carpeta / "borradores" / "borradores.toml"
        documento = Path(tmp) / "resultado.txt"
        documento.write_text("Resultado de la licitación. " * 20, encoding="utf-8")
        hoy = date(2026, 11, 14)
        try:
            antes_s29e7 = leer_fichas.ficha("S29E7")
            r = fd.leer(str(documento), extractor=lambda texto: RESULTADO_NOV, hoy=hoy)
            assert {"S29E7", "TZX28", "TMF27", "TMG27"} <= set(r["ya_cargados"])
            assert any("S29E7: precio de corte 1.060,00, TIREA 28,08%" == c for c in r["cortes"]), r["cortes"]
            assert leer_fichas.ficha("S29E7") == antes_s29e7                     # un precio de corte no cambia la ficha
            # La letra TAMAR nueva: borrador con el margen de corte y el ticker pendiente.
            letra = next(b for b in fd.pendientes() if b["clave"] == "tamar_capitalizable-2027-04-30")
            assert letra["margen"] == 0.025 and letra["pendiente"] == ["ticker: no figura en el resultado"]
            # Datos distintos de fichas aprobadas: propuestos, sin tocar la ficha.
            assert sorted(r["cambios"]) == ["TMF27 margen: 0.065 → 0.07", "TMG27 margen: 0.06 → 0.05"]
            assert leer_fichas.ficha("TMF27")["margen"] == 0.065
            assert "TMF27 (tamar_capitalizable) margen: 0.065 → 0.07" in fd.describir_cambios()
            # Leer dos veces el mismo documento no duplica las propuestas.
            fd.leer(str(documento), extractor=lambda texto: RESULTADO_NOV, hoy=hoy)
            assert len(fd.cambios_propuestos()) == 2

            # Aplicar (desde el agente) y rechazar.
            salida = lector_fichas.aplicar_cambio("TMF27")
            assert "TMF27 (tamar_capitalizable): margen = 0.07" in salida, salida
            tmf27 = leer_fichas.ficha("TMF27")
            assert tmf27["margen"] == 0.07 and "aprobado por Agustin (vía agente de renta fija)" in tmf27["fuente"]
            assert tmf27["revisado"] is True and leer_fichas.ficha("TML27")["margen"] == 0.054   # el resto, igual
            assert "Rechazado: TMG27 margen" in fd.rechazar("TMG27")
            assert leer_fichas.ficha("TMG27")["margen"] == 0.06 and fd.cambios_propuestos() == []
            assert "No hay cambios" in _error(lambda: fd.aplicar("TMG27"))

            # Completar el ticker que no vino y aprobar.
            assert "ticker = M30A7" in lector_fichas.completar_borrador("tamar_capitalizable-2027-04-30", "ticker", "m30a7")
            letra = next(b for b in fd.pendientes() if b["clave"] == "M30A7")
            assert "pendiente" not in letra
            assert "M30A7 aprobado" in fd.aprobar("M30A7", hoy=hoy)
            assert leer_fichas.ficha("M30A7")["margen"] == 0.025
        finally:
            leer_fichas.CARPETA, fd.BORRADORES = original_carpeta, original_borradores


def test_reaperturas_duplicados_y_tickers():
    original_carpeta, original_borradores, original_buscador = leer_fichas.CARPETA, fd.BORRADORES, fd.BUSCADOR
    listados = {"S14Y7": "LECAP V14/05/27", "M30A7": "LETRA TAMAR V30/04/27", "TMA27": "BONO TAMAR V30/04/27"}
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "fichas"
        shutil.copytree(original_carpeta, carpeta, ignore=shutil.ignore_patterns("borradores"))
        leer_fichas.CARPETA, fd.BORRADORES = carpeta, carpeta / "borradores" / "borradores.toml"
        fd.BUSCADOR = lambda t: [{"ticker": t, "description": listados[t]}] if t in listados else []
        documento = Path(tmp) / "aviso.txt"
        documento.write_text("Aviso del Tesoro. " * 20, encoding="utf-8")
        hoy = date(2026, 11, 14)
        try:
            # 1. Reaperturas: el AO28 con la fecha de liquidación de esta licitación como "emisión" (lo que pasaba).
            llamado = fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2026-11-09", instrumentos=[
                fd.Instrumento(nombre="BONAR 2028", ticker="AO28", reapertura=True, familia="hard_dollar", tipo="BONAR",
                               ley="AR", emision="2026-11-13", vencimiento="2028-10-30"),
                fd.Instrumento(nombre="BONCER TZXD7", ticker="TZXD7", reapertura=True, familia="cer_cero_cupon",
                               tipo="BONCER", emision="2026-11-13", vencimiento="2027-12-15"),
                fd.Instrumento(nombre="LECAP 14/05/2027", familia="tasa_fija_capitalizable", tipo="LECAP",
                               emision="2026-11-13", vencimiento="2027-05-14", cupon=0.019,
                               pendiente=["ticker: no figura en el llamado"]),
                fd.Instrumento(nombre="Letra TAMAR 30/04/2027", familia="tamar_capitalizable", tipo="LETRA TAMAR",
                               emision="2026-11-13", vencimiento="2027-04-30", margen=0.025),
            ])
            r = fd.leer(str(documento), extractor=lambda texto: llamado, hoy=hoy)
            assert "TZXD7" in r["ya_cargados"]                                  # reapertura de un bono cargado: se ignora
            assert leer_fichas.ficha("TZXD7")["emision"] == date(2024, 3, 15)   # y su emisión original no se toca
            ao28 = next(b for b in fd.pendientes() if b["clave"] == "AO28")
            assert "emision" not in ao28 and ao28["reapertura"] is True and r["reaperturas"] == ["AO28"]
            assert any(p.startswith("emision: es una reapertura") for p in ao28["pendiente"])
            # Una reapertura que sí trae la emisión original (anterior al aviso) la conserva.
            assert fd.a_ficha(fd.Instrumento(nombre="x", ticker="AO27", reapertura=True, familia="hard_dollar",
                                             emision="2025-10-29", vencimiento="2027-10-29"),
                              "x", "llamado", "2026-11-09")["emision"] == date(2025, 10, 29)
            # El prospecto de la primera emisión completa la emisión original y saca el pendiente.
            prospecto = fd.Documento(tipo_documento="resolución de emisión", fecha_documento="2025-10-27", instrumentos=[
                fd.Instrumento(nombre="BONAR 2028", ticker="AO28", familia="hard_dollar", tipo="BONAR", ley="AR",
                               emision="2025-10-30", vencimiento="2028-10-30")])
            fd.leer(str(documento), extractor=lambda texto: prospecto, hoy=hoy)
            ao28 = next(b for b in fd.pendientes() if b["clave"] == "AO28")
            assert ao28["emision"] == date(2025, 10, 30)
            assert not any(p.startswith("emision") for p in ao28.get("pendiente", []))
            assert "reapertura" not in fd.a_toml({k: v for k, v in ao28.items() if k not in fd.SOLO_BORRADOR})

            # 2. Tickers por la convención de nombres: uno solo listado → se completa; dos → queda pendiente.
            lecap = next(b for b in fd.pendientes() if b.get("ticker") == "S14Y7")
            assert "verificalo antes de aprobar" in lecap["nota"] and "pendiente" not in lecap
            assert any("S14Y7: ticker encontrado en PPI (LECAP V14/05/27)" == a for a in r["avisos"])
            letra = next(b for b in fd.pendientes() if b["clave"] == "tamar_capitalizable-2027-04-30")
            assert any("M30A7, TMA27" in p for p in letra["pendiente"])
            assert fd.candidatos_ticker("cer_cero_cupon", date(2028, 6, 30)) == ["X30J8", "TZXJ8", "TZX28"]
            assert fd.candidatos_ticker("dolar_linked_bullet", date(2027, 3, 31)) == ["D31M7", "TZVM7"]

            # 3. Emisión vieja sin ticker con las condiciones de un bono cargado: es ese bono, no va al borrador
            #    (regla de Agustin, 26/11/2026).
            viejo = fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2024-03-11", instrumentos=[
                fd.Instrumento(nombre="BONCER cero cupón 15/12/2027", familia="cer_cero_cupon", tipo="BONCER",
                               emision="2024-03-15", vencimiento="2027-12-15"),
                fd.Instrumento(nombre="BONCAP 30/04/2027", familia="tasa_fija_capitalizable", tipo="BONCAP",
                               emision="2025-10-31", vencimiento="2027-04-30", cupon=0.0255)])
            r = fd.leer(str(documento), extractor=lambda texto: viejo, hoy=hoy)
            assert any(y.startswith("cer_cero_cupon-2027-12-15 = TZXD7") for y in r["ya_cargados"])
            assert any(y.startswith("tasa_fija_capitalizable-2027-04-30 = T30A7") for y in r["ya_cargados"])
            assert not r["nuevos"] and not {"cer_cero_cupon-2027-12-15", "tasa_fija_capitalizable-2027-04-30"} & {
                b["clave"] for b in fd.pendientes()}
            # Un ticker que ya está en la base con otra familia tampoco va al borrador (es ese bono)
            otra = fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2026-11-09", instrumentos=[
                fd.Instrumento(nombre="BONCER TZXD7", ticker="TZXD7", familia="cer_cupon", tipo="BONCER",
                               emision="2024-03-15", vencimiento="2027-12-15")])
            r = fd.leer(str(documento), extractor=lambda texto: otra, hoy=hoy)
            assert r["ya_cargados"] == ["TZXD7 (cargado como cer_cero_cupon)"] and not r["nuevos"]

            # 4. Con un ticker que no está en la base pero las mismas condiciones que otro: decide un humano.
            dudoso = fd.Documento(tipo_documento="resultado de licitación", fecha_documento="2026-11-12", instrumentos=[
                fd.Instrumento(nombre="BONCAP 30/04/2027", ticker="T30A7X", familia="tasa_fija_capitalizable",
                               tipo="BONCAP", emision="2025-10-31", vencimiento="2027-04-30", cupon=0.0255),
                fd.Instrumento(nombre="BONCER 15/12/2027", ticker="TZXD7B", familia="cer_cero_cupon", tipo="BONCER",
                               emision="2024-03-15", vencimiento="2027-12-15")])
            r = fd.leer(str(documento), extractor=lambda texto: dudoso, hoy=hoy)
            boncap = next(b for b in fd.pendientes() if b["clave"] == "T30A7X")
            assert boncap["posible_duplicado"] == ["T30A7"]
            assert any("parece el mismo bono que T30A7" in a for a in r["avisos"])
            error = _error(lambda: fd.aprobar("T30A7X", hoy=hoy))
            assert "parece el mismo bono que T30A7" in error and "--nuevo" in error
            assert "No se aprobó" in lector_fichas.aprobar_ficha("T30A7X")
            salida = fd.vincular("TZXD7B", "TZXD7")
            assert "vinculado a TZXD7" in salida and "coinciden" in salida
            assert "TZXD7B" not in [b["clave"] for b in fd.pendientes()]
            assert "T30A7X aprobado" in lector_fichas.aprobar_ficha("T30A7X", nuevo=True)    # el humano dice que es otro
            assert "confirmado como bono distinto de T30A7" in leer_fichas.ficha("T30A7X")["fuente"]
        finally:
            leer_fichas.CARPETA, fd.BORRADORES, fd.BUSCADOR = original_carpeta, original_borradores, original_buscador


def test_emision_original():
    """AO27: reapertura en el llamado de marzo; la primera emisión está en el aviso de febrero (sin ticker)."""
    original_carpeta, original_borradores, original_web = leer_fichas.CARPETA, fd.BORRADORES, fd.BUSCADOR_WEB
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "fichas"
        shutil.copytree(original_carpeta, carpeta, ignore=shutil.ignore_patterns("borradores"))
        leer_fichas.CARPETA, fd.BORRADORES = carpeta, carpeta / "borradores" / "borradores.toml"
        marzo, febrero, otro = Path(tmp) / "marzo.txt", Path(tmp) / "febrero.txt", Path(tmp) / "otro.txt"
        marzo.write_text("Llamado de marzo. BONAR con vencimiento 29/10/2027. " * 10 + "y del “Bono del Tesoro Nacional en "
                         "dólares estadounidenses 6% con vencimiento 29 de octubre de 2027”, emitido\noriginalmente mediante "
                         "el artículo 8° de la resolución conjunta 11 del 24 de febrero de 2026 de la Secretaría", encoding="utf-8")
        febrero.write_text("Llamado de febrero. BONO 6% CON VENCIMIENTO 29 DE OCTUBRE DE 2027. " * 10, encoding="utf-8")
        otro.write_text("Resolución sobre otro tema, sin bonos. " * 20, encoding="utf-8")
        cupones = [date(2026, m, d) for m, d in ((3, 31), (4, 30), (5, 29), (6, 30))] + [date(2027, 10, 29)]
        docs = {
            "marzo": fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2026-03-25", instrumentos=[
                fd.Instrumento(nombre="BONAR 2027 6% (AO27, reapertura)", ticker="AO27", reapertura=True,
                               familia="hard_dollar", tipo="BONAR", ley="AR", emision="2026-03-31", vencimiento="2027-10-29",
                               cita="BONO DEL TESORO NACIONAL EN DOLARES ESTADOUNIDENSES 6% CON VENCIMIENTO 29 DE OCTUBRE DE 2027"),
                fd.Instrumento(nombre="LECAP 17/07/2026", familia="tasa_fija_capitalizable", tipo="LECAP",
                               emision="2026-03-31", vencimiento="2026-07-17")]),
            "febrero": fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2026-02-23", instrumentos=[
                fd.Instrumento(nombre="BONAR 2027 (nuevo)", familia="hard_dollar", tipo="BONAR", ley="AR",
                               emision="2026-02-27", vencimiento="2027-10-29", base="30/360",
                               tramos=[fd.Tramo(desde="2026-02-27", tasa=0.06)],
                               pagos=[fd.Pago(fecha=d.isoformat(), amortizacion=100 if d.year == 2027 else 0) for d in cupones]),
                fd.Instrumento(nombre="Dollar linked 30/06/2028 (nuevo)", familia="dolar_linked_bullet", tipo="BONTE DL",
                               emision="2026-02-27", vencimiento="2028-06-30")]),
        }
        leidos = []
        extractor = lambda texto: leidos.append(texto[:20]) or docs["marzo" if "marzo" in texto else "febrero"]
        consultas = []
        # La búsqueda general no encuentra el aviso de febrero; sí la resolución que cita el de marzo
        fd.BUSCADOR_WEB = lambda consulta: consultas.append(consulta) or (
            [str(febrero)] if "Resolución Conjunta 11 del 24 de febrero de 2026" in consulta else [str(otro), str(marzo)])
        hoy = date(2026, 11, 15)
        try:
            assert not any(fd.leer(str(marzo), extractor=extractor, hoy=hoy)["avisos"])   # en pausa: no busca sola
            fd.descartar("AO27")
            r = fd.leer(str(marzo), extractor=extractor, hoy=hoy, buscar_emision=True)
            assert r["reaperturas"] == ["AO27"]
            assert 'site:argentina.gob.ar/noticias "llamado a licitación" "vencimiento 29 de octubre de 2027"' in consultas[0]
            assert "PRIMERA emisión" in consultas[0] and "filetype" not in consultas[0]
            assert "anterior al 25 de marzo de 2026" in consultas[0]          # antes del aviso en que ya era reapertura
            assert not any("otro tema" in l for l in leidos) and len(leidos) == 4   # el que no nombra la fecha, sin modelo
            assert "RESFC-2026-11-APN-SH#MEC" in consultas[1] and len(consultas) == 2   # siguió la resolución citada
            assert 'site:boletinoficial.gob.ar "Resolución Conjunta 11/2026"' in consultas[1]
            assert fd.menciona_vencimiento("CON VENCIMIENTO EL 29 DE OCTUBRE  DE 2027", date(2027, 10, 29))
            assert fd.menciona_vencimiento("vto. 09/07/2030", date(2030, 7, 9))
            assert not fd.menciona_vencimiento("vence el 29 de octubre de 2028", date(2027, 10, 29))
            aviso = next(a for a in r["avisos"] if a.startswith("AO27"))
            assert "encontré la primera emisión en" in aviso and "febrero.txt" in aviso, aviso
            ao27 = next(b for b in fd.pendientes() if b["clave"] == "AO27")
            assert ao27["emision"] == date(2026, 2, 27) and ao27["base"] == "30/360" and len(ao27["pagos"]) == 5
            assert not any(p.startswith("emision") for p in ao27.get("pendiente", []))
            # Del aviso de febrero no se cargó nada más (el dollar linked 2028 no aparece como borrador nuevo)
            assert not any(b.get("familia") == "dolar_linked_bullet" for b in fd.pendientes())
            # Con la emisión original, se aprueba
            assert "AO27 aprobado" in fd.aprobar("AO27", hoy=hoy)
            assert leer_fichas.ficha("AO27")["emision"] == date(2026, 2, 27)

            # Si la búsqueda no encuentra nada, queda anotado y se indica cómo pasar el link
            fd.BUSCADOR_WEB = lambda consulta: []
            fd._guardar_borradores(fd.pendientes() + [{"ticker": "AO28", "tipo": "BONAR", "familia": "hard_dollar",
                                                         "vencimiento": date(2028, 10, 31), "revisado": False,
                                                         "fuente": "x", "pendiente": ["emision", "precio"], "clave": "AO28"}])
            salida = lector_fichas.buscar_emision_original("AO28")
            assert "no encontré la primera emisión" in salida and "--solo AO28" in salida
            assert next(b for b in fd.pendientes() if b["clave"] == "AO28")["emision_buscada"] == date.today()   # la herramienta usa hoy
        finally:
            leer_fichas.CARPETA, fd.BORRADORES, fd.BUSCADOR_WEB = original_carpeta, original_borradores, original_web


def _error(funcion) -> str:
    try:
        funcion()
    except (ValueError, leer_fichas.ErrorFicha) as e:
        return str(e)
    return ""


def test_dual_un_borrador_por_pata():
    """Un dual (TAMAR o dollar linked) deja un borrador por pata, cada uno con sus datos, y se aprueban por separado."""
    original_carpeta, original_borradores = leer_fichas.CARPETA, fd.BORRADORES
    dual = fd.Documento(tipo_documento="llamado a licitación", fecha_documento="2026-11-20", instrumentos=[
        fd.Instrumento(nombre="Bono dual TAMAR / dólar linked vencimiento 31 de mayo de 2028", ticker="TMVE8",
                       familia="tamar_capitalizable", familia_dual="dolar_linked_bullet", tipo="DUAL TAMAR/DL",
                       emision="2026-11-24", vencimiento="2028-05-31", margen=0.0,
                       tipo_cambio_pago="A3500 del 3.er día hábil anterior al pago",
                       pendiente=["margen: se define en la licitación"])])
    with tempfile.TemporaryDirectory() as tmp:
        carpeta = Path(tmp) / "fichas"
        shutil.copytree(original_carpeta, carpeta, ignore=shutil.ignore_patterns("borradores"))
        leer_fichas.CARPETA, fd.BORRADORES = carpeta, carpeta / "borradores" / "borradores.toml"
        documento = Path(tmp) / "llamado.txt"
        documento.write_text("Llamado a licitación del Tesoro. " * 20, encoding="utf-8")
        try:
            r = fd.leer(str(documento), extractor=lambda texto: dual, hoy=date(2026, 11, 20))
            assert sorted(r["nuevos"]) == ["TMVE8-DL", "TMVE8-TAMAR"], r["nuevos"]
            patas = {b["clave"]: b for b in fd.pendientes()}
            tamar, dl = patas["TMVE8-TAMAR"], patas["TMVE8-DL"]
            assert tamar["familia"] == "tamar_capitalizable" and "margen" in tamar and "tipo_cambio_pago" not in tamar
            assert dl["familia"] == "dolar_linked_bullet" and "margen" not in dl and "tipo_cambio_pago" in dl
            assert "pendiente" not in dl and tamar["pendiente"] == ["margen: se define en la licitación"]
            assert tamar["dual_con"] == "dolar_linked_bullet" and "DUAL" in dl["tipo"]
            # Leer de nuevo no duplica: completa cada pata
            fd.leer(str(documento), extractor=lambda texto: dual, hoy=date(2026, 11, 20))
            assert sorted(b["clave"] for b in fd.pendientes()) == ["TMVE8-DL", "TMVE8-TAMAR"]
            fd.aprobar("TMVE8-DL", hoy=date(2026, 11, 20))
            fd.aprobar("TMVE8-TAMAR", hoy=date(2026, 11, 20))
            familias = sorted(f["familia"] for f in leer_fichas.fichas_de("TMVE8"))
            assert familias == ["dolar_linked_bullet", "tamar_capitalizable"], familias
            assert all("dual_con" not in f and "DUAL" in f["tipo"] for f in leer_fichas.fichas_de("TMVE8"))
            assert not fd.pendientes()
        finally:
            leer_fichas.CARPETA, fd.BORRADORES = original_carpeta, original_borradores
            leer_fichas.leer_todas.cache_clear() if hasattr(leer_fichas.leer_todas, "cache_clear") else None


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
    for prueba in (test_borradores_aprobacion, test_resultado_y_cambios, test_reaperturas_duplicados_y_tickers, test_emision_original, test_dual_un_borrador_por_pata, test_texto_html, test_toml_ida_y_vuelta):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas del lector de fichas pasaron.")
