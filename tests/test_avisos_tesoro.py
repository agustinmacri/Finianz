"""Pruebas de la revisión periódica de avisos del Tesoro (listado de noticias de Finanzas), sin internet ni modelo.
Correr con:
    python -m tests.test_avisos_tesoro
"""
import tempfile
from datetime import date
from pathlib import Path

from carga_datos import avisos_tesoro as at
from carga_datos import fichas_documentos as fd
from carga_datos import novedades

# Las pruebas nunca escriben las novedades reales ni mandan notificaciones
novedades.REGISTRO = Path(tempfile.gettempdir()) / "finianz_prueba_novedades.json"
novedades.notificar = lambda titulo, texto: "notificación de prueba"

BASE = "https://www.argentina.gob.ar/noticias/"


def _tarjeta(slug, fecha, titulo, absoluta=True):
    href = (BASE if absoluta else "/noticias/") + slug
    return (f'<div class="col-xs-12 col-sm-6"><a href="{href}" class="panel panel-default"><div class="panel-body">'
            f'<time>{fecha}</time><h3>{titulo}</h3></div></a></div>')


def _pagina(*tarjetas):
    return ('<html><body><nav><a href="/economia">Economía</a><a href="/noticias">Noticias</a></nav>'
            + "".join(tarjetas) + '<ul class="pagination"><a href="/node/77983/noticias?page=1">2</a></ul></body></html>')


PAGINA_1 = _pagina(
    _tarjeta("resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-18",
             "26 de noviembre de 2026", "Resultado de la licitación por efectivo de instrumentos del Tesoro Nacional"),
    _tarjeta("llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-17",
             "24 de noviembre de 2026", "Llamado a licitación de instrumentos del Tesoro Nacional denominados en pesos"),
    _tarjeta("resultado-de-la-licitacion-para-la-conversion-de-la-lelink-d30n6-en-el-marco-del-articulo",
             "17 de noviembre de 2026", "Resultado de la licitación para la conversión de la LELINK D30N6", absoluta=False),
    _tarjeta("comunicacion-del-precio-de-la-lelink-d30n6-para-su-conversion-en-el-marco-del-articulo-2",
             "17 de noviembre de 2026", "Comunicación del precio de la LELINK D30N6 para su conversión"),
    _tarjeta("conversion-de-la-lelink-d30n6-en-el-marco-del-articulo-2deg-del-decreto-84624",
             "13 de noviembre de 2026", "Conversión de la LELINK D30N6 en el marco del artículo 2° del decreto 846/24"),
    _tarjeta("resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-17",
             "11 de noviembre de 2026", "Resultado de la licitación por efectivo de instrumentos del Tesoro Nacional"),
    _tarjeta("llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-16",
             "05 de noviembre de 2026", "Llamado a licitación de instrumentos del Tesoro Nacional denominados en pesos"),
    _tarjeta("federico-furiase-el-momento-de-invertir-es-ahora", "22 de octubre de 2026",
             "Federico Furiase: “El momento de invertir es ahora”"))
PAGINA_2 = _pagina(_tarjeta("llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-15",
                            "26 de octubre de 2026", "Llamado a licitación de instrumentos del Tesoro Nacional"))


def _descargar(paginas):
    return lambda direccion: paginas[1] if "page=1" in direccion else paginas[0]


def _resumen(direccion, nuevos=()):
    return {"documento": "llamado a licitación" if "llamado" in direccion else "resultado de licitación",
            "fecha": "2026-11-24", "ya_cargados": ["TZXD7"], "vencidos": [], "nuevos": list(nuevos), "completados": [],
            "sin_familia": [], "descartados": []}


def _con_registro(prueba):
    def envoltura():
        original_registro, original_borradores, original_novedades = at.REGISTRO, fd.BORRADORES, novedades.REGISTRO
        with tempfile.TemporaryDirectory() as tmp:
            at.REGISTRO = Path(tmp) / "avisos_tesoro.json"
            fd.BORRADORES = Path(tmp) / "borradores" / "borradores.toml"
            novedades.REGISTRO = Path(tmp) / "novedades.json"
            try:
                prueba()
            finally:
                at.REGISTRO, fd.BORRADORES, novedades.REGISTRO = original_registro, original_borradores, original_novedades
    envoltura.__name__ = prueba.__name__
    return envoltura


def test_listado():
    noticias = at.leer_listado(PAGINA_1)
    assert [n["url"] for n in noticias][:2] == [
        BASE + "resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-18",
        BASE + "llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-17"]
    assert noticias[0]["fecha"] == date(2026, 11, 26) and noticias[0]["titulo"].startswith("Resultado de la licitación")
    assert noticias[2]["url"].startswith(BASE)                      # dirección relativa → absoluta
    avisos = [n["titulo"] for n in noticias if at.es_aviso(n["titulo"])]
    assert len(avisos) == 6 and not any("Comunicación" in t or "Furiase" in t for t in avisos)
    assert len(at.listar(descargar=_descargar((PAGINA_1, PAGINA_2)))) == 9


@_con_registro
def test_migracion_y_lectura_en_orden():
    # Registro del sistema anterior: llamado 16 y resultado 17 ya leídos
    at.guardar_registro({"series": {"llamado": 16, "resultado": 17}, "leidos": []})
    leidos = []
    lector = lambda d: leidos.append(d) or _resumen(d)
    informe = at.revisar(lector=lector, descargar=_descargar((PAGINA_1, PAGINA_2)))
    # Se leen, de la más vieja a la más nueva, solo los posteriores: la conversión del 17/11, el llamado 17 y el
    # resultado 18 (la conversión del 13/11 es anterior al seguimiento y el llamado 15 ya se había leído)
    assert leidos == [BASE + "resultado-de-la-licitacion-para-la-conversion-de-la-lelink-d30n6-en-el-marco-del-articulo",
                      BASE + "llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-17",
                      BASE + "resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-18"]
    assert informe[0].startswith("[17/11/2026] Resultado de la licitación para la conversión")
    leidos.clear()
    informe = at.revisar(lector=lector, descargar=_descargar((PAGINA_1, PAGINA_2)))
    assert leidos == [] and informe[-1].startswith("No hay avisos nuevos")


@_con_registro
def test_reintentos_y_aviso():
    at.guardar_registro({"series": {"llamado": 17, "resultado": 17}, "leidos": []})
    enviados = []
    original = novedades.notificar
    novedades.notificar = lambda titulo, texto: enviados.append(texto) or "notificación enviada"
    try:
        def falla(d):
            raise RuntimeError("503 modelo saturado")
        informe = at.revisar(lector=falla, descargar=_descargar((PAGINA_1, PAGINA_2)))
        assert "Se reintenta" in informe[0] and enviados == []
        # Sin conexión al listado: no se da nada por leído
        def sin_red(d):
            raise ConnectionError("sin conexión")
        assert "No se pudo leer el listado" in at.revisar(lector=falla, descargar=sin_red)[0]
        informe = at.revisar(lector=lambda d: _resumen(d, nuevos=["S30J7", "TMVE8-DL"]),
                             descargar=_descargar((PAGINA_1, PAGINA_2)))
        # Tres avisos posteriores al 15/11 (la conversión, el llamado 17 y el resultado 18): una sola notificación
        assert len(enviados) == 1 and "6 borradores nuevos (S30J7, TMVE8-DL" in enviados[0], enviados
        assert informe[-1] == "Aviso: notificación enviada." and len(novedades.sin_ver()) == 3
        assert novedades.marcar_vistas() == 3 and novedades.sin_ver() == []
    finally:
        novedades.notificar = original


@_con_registro
def test_registro_de_la_primera_version():
    """Con el registro de la primera versión (que dio por leídos el llamado 17 y el resultado 18 por su número), se
    vuelven a leer: el lector descarta lo que ya esté en la base."""
    llamado_17 = BASE + "llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-17"
    conversion = BASE + "resultado-de-la-licitacion-para-la-conversion-de-la-lelink-d30n6-en-el-marco-del-articulo"
    at.guardar_registro({"series": {"llamado": 17, "resultado": 18}, "vistos": [llamado_17, conversion],
                         "leidos": [{"url": conversion, "titulo": "Resultado de la licitación para la conversión"}]})
    leidos = []
    at.revisar(lector=lambda d: leidos.append(d) or _resumen(d), descargar=_descargar((PAGINA_1, PAGINA_2)))
    assert leidos == [llamado_17,
                      BASE + "resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-18"]
    assert at.cargar_registro()["version"] == 2


def test_portada_primero():
    """El resultado del día está en la portada de Finanzas antes que en el listado."""
    hoy = _tarjeta("resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados-19",
                   "10 de diciembre de 2026", "Resultado de la licitación por efectivo de instrumentos del Tesoro Nacional")
    portada = _pagina(hoy)
    descargar = lambda d: portada if d == at.PORTADA else (PAGINA_2 if "page=1" in d else PAGINA_1)
    noticias = at.listar(descargar=descargar)
    assert noticias[0]["url"].endswith("denominados-19") and noticias[0]["fecha"] == date(2026, 12, 10)


@_con_registro
def test_marcar_y_olvidar():
    at.guardar_registro({"series": {"llamado": 17, "resultado": 18}, "leidos": [], "vistos": [], "version": 2})
    direccion = BASE + "llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares-17"
    at.main(["marcar", direccion])
    assert direccion in at.cargar_registro()["vistos"]
    at.main(["olvidar", direccion])
    assert direccion not in at.cargar_registro()["vistos"]


if __name__ == "__main__":
    for prueba in (test_listado, test_migracion_y_lectura_en_orden, test_reintentos_y_aviso, test_registro_de_la_primera_version,
                   test_portada_primero, test_marcar_y_olvidar):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de los avisos del Tesoro pasaron.")
