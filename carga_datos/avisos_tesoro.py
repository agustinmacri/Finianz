"""Revisa si la Secretaría de Finanzas publicó avisos de licitación nuevos y los lee con el lector de fichas
(carga_datos/fichas_documentos.py): borradores de los bonos nuevos, valores de corte y cambios propuestos. Nada se
aprueba solo.

Cómo encuentra los avisos (decisión de Agustin, 26/11/2026): lee el listado oficial de noticias de la Secretaría de
Finanzas (https://www.argentina.gob.ar/economia/finanzas/noticias, las primeras páginas) y toma las noticias cuyo
título empieza con "Llamado", "Resultado", "Anuncio complementario" o "Conversión" (no las "Comunicación del precio").
Guarda en datos/avisos_tesoro.json las direcciones ya leídas; las que faltan se leen de la más vieja a la más nueva.
No depende del título ni de los números de las direcciones.

El lector descarta los bonos que ya están en la base (por ticker, o por condiciones si el aviso no trae el ticker):
solo quedan como borrador los que no tenemos.

Uso:
    python -m carga_datos.avisos_tesoro                # revisa y lee los nuevos
    python -m carga_datos.avisos_tesoro estado         # qué se leyó último
    python -m carga_datos.avisos_tesoro listado        # los avisos del listado y si ya se leyeron
    python -m carga_datos.avisos_tesoro marcar <URL>   # dar un aviso por leído sin leerlo
    python -m carga_datos.avisos_tesoro olvidar <URL>  # que la próxima revisión lo vuelva a leer

Para que corra solo, programalo en tu compu (ver README, "Avisos del Tesoro").
"""
import html as html_lib
import json
import re
import sys
import unicodedata
from datetime import date, datetime

import config
from carga_datos import fichas_documentos as fd
from carga_datos import novedades

SITIO = "https://www.argentina.gob.ar"
LISTADO = SITIO + "/economia/finanzas/noticias"
PORTADA = SITIO + "/economia/finanzas"    # muestra los avisos del día antes que el listado (que tarda en actualizarse)
PAGINAS = 2                     # páginas del listado que se revisan (unas 15 noticias cada una)
RELEVANTES = ("llamado", "resultado", "anuncio complementario", "conversion")
EXCLUIDOS = ("comunicacion del precio",)
MESES = {m: i for i, m in enumerate(["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
                                     "septiembre", "octubre", "noviembre", "diciembre"], 1)}
# Sistema anterior (por número en la dirección): sirve para pasar el registro viejo al nuevo sin releer nada
SERIES = {
    "llamado": "llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares",
    "resultado": "resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados",
}
INICIAL = {"llamado": 16, "resultado": 17}
INICIO_SEGUIMIENTO = date(2026, 11, 15)   # lo publicado antes ya se leyó a mano (Agustin, 15/11/2026)
REGISTRO = None                            # se resuelve en tiempo de ejecución: datos/avisos_tesoro.json


def _ruta():
    return REGISTRO or config.DATOS_DIR / "avisos_tesoro.json"


def _clave(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return " ".join(texto.split())


def cargar_registro() -> dict:
    ruta = _ruta()
    registro = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    registro.setdefault("series", dict(INICIAL))
    registro.setdefault("leidos", [])
    return registro


def guardar_registro(registro: dict):
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(registro, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def url(serie: str, numero: int) -> str:
    """Dirección del sistema anterior (solo para la migración del registro)."""
    return f"{SITIO}/noticias/{SERIES[serie]}-{numero}"


def _descargar(direccion: str) -> str:
    import requests
    respuesta = requests.get(direccion, timeout=30, headers=fd.NAVEGADOR)
    respuesta.raise_for_status()
    return respuesta.text


def _fecha(texto: str) -> date | None:
    m = re.search(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", _clave(texto))
    if m and m.group(2) in MESES:
        try:
            return date(int(m.group(3)), MESES[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    return None


def leer_listado(pagina: str) -> list[dict]:
    """Las noticias de una página del listado: [{"url", "titulo", "fecha"}], en el orden de la página."""
    enlaces = list(re.finditer(r'<a\s[^>]*href="([^"#?]*?/noticias/[^"#?]+)"[^>]*>(.*?)</a>', pagina, re.S | re.I))
    salida, vistas = [], set()
    for i, m in enumerate(enlaces):
        texto_enlace = " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", m.group(2))).split())
        # La tarjeta trae la fecha dentro del enlace, antes del título ("24 de noviembre de 2026 Llamado a ...")
        titulo = re.sub(r"^\s*\d{1,2}\s+de\s+[A-Za-záéíóú]+\s+de\s+\d{4}\s*[-–·|]?\s*", "", texto_enlace)
        direccion = m.group(1) if m.group(1).startswith("http") else SITIO + m.group(1)
        if len(titulo) < 12 or direccion in vistas or "/noticias/" not in direccion:
            continue
        fecha = _fecha(texto_enlace)
        if fecha is None:                        # si no, en la tarjeta: entre el enlace anterior y el siguiente
            desde = enlaces[i - 1].end() if i else max(0, m.start() - 600)
            hasta = enlaces[i + 1].start() if i + 1 < len(enlaces) else m.end() + 600
            fecha = _fecha(re.sub(r"<[^>]+>", " ", pagina[desde:m.start()]) + " " +
                           re.sub(r"<[^>]+>", " ", pagina[m.end():hasta]))
        vistas.add(direccion)
        salida.append({"url": direccion, "titulo": titulo, "fecha": fecha})
    return salida


def listar(paginas: int = PAGINAS, descargar=_descargar) -> list[dict]:
    """Las noticias de la portada de Finanzas y de las primeras páginas del listado, de la más nueva a la más vieja.
    La portada se suma porque el listado tarda en mostrar los avisos del día (el resultado de hoy puede estar en la
    portada y todavía no en el listado)."""
    salida, vistas = [], set()
    direcciones = [PORTADA] + [LISTADO if n == 0 else f"{LISTADO}?page={n}" for n in range(paginas)]
    for i, direccion in enumerate(direcciones):
        try:
            noticias = leer_listado(descargar(direccion))
        except Exception:
            if i == 0:
                continue                        # sin portada, igual sirve el listado
            raise
        for noticia in noticias:
            if noticia["url"] not in vistas:
                vistas.add(noticia["url"])
                salida.append(noticia)
    return sorted(salida, key=lambda n: n["fecha"] or date.min, reverse=True)


def es_aviso(titulo: str) -> bool:
    t = _clave(titulo)
    return t.startswith(RELEVANTES) and not any(x in t for x in EXCLUIDOS)


def _migrar(registro: dict, avisos: list[dict]):
    """Primera vez con el listado: da por leído solo lo publicado antes de que empezara el seguimiento (15/11/2026).
    Lo posterior se lee de nuevo aunque el sistema anterior lo haya leído: el lector descarta lo que ya está en la
    base, así que no duplica nada y completa lo que haya faltado."""
    registro["vistos"] = [a["url"] for a in avisos if a["fecha"] and a["fecha"] < INICIO_SEGUIMIENTO]


def _actualizar_version(registro: dict, avisos: list[dict]) -> bool:
    """Primera vez con el listado, o registro de la primera versión (que daba por leídos los avisos por su número
    aunque el sistema anterior no los hubiera procesado bien): se recalcula conservando lo leído con el listado.
    Devuelve True si cambió."""
    if registro.get("version") == 2:
        return False
    leidos_con_listado = {x["url"] for x in registro["leidos"] if x.get("titulo")}
    _migrar(registro, avisos)
    registro["vistos"] += [u for u in leidos_con_listado if u not in registro["vistos"]]
    registro["version"] = 2
    return True


def revisar(lector=None, descargar=_descargar, hoy: date | None = None, notificar: bool = True) -> list[str]:
    """Lee los avisos nuevos del listado. Devuelve el informe en renglones. Si dejaron algo para revisar
    (borradores nuevos o completados, valores de corte, cambios propuestos), lo anota en las novedades y manda una
    notificación de Windows."""
    lector = lector or fd.leer
    registro = cargar_registro()
    try:
        avisos = [a for a in listar(descargar=descargar) if es_aviso(a["titulo"])]
    except Exception as e:
        return [f"No se pudo leer el listado de noticias de Finanzas ({str(e).splitlines()[0][:150]}). "
                "Se reintenta la próxima vez."]
    if _actualizar_version(registro, avisos):
        guardar_registro(registro)
    vistos = set(registro["vistos"])
    pendientes = [a for a in reversed(avisos) if a["url"] not in vistos]          # de la más vieja a la más nueva
    pendientes.sort(key=lambda a: a["fecha"] or date.max)
    informe, de_esta_vez = [], []
    if avisos and len(pendientes) == len(avisos):
        informe.append(f"Ninguno de los {len(avisos)} avisos de las primeras {PAGINAS} páginas estaba leído: puede haber "
                       "más viejos sin leer (python -m carga_datos.fichas_documentos leer <URL> para leerlos a mano).")
    for a in pendientes:
        try:
            resumen = lector(a["url"], hoy=hoy) if hoy else lector(a["url"])
        except Exception as e:
            # No se avanza: la próxima revisión lo vuelve a intentar (y los posteriores esperan, para leer en orden)
            informe.append(f"{a['titulo']} ({a['url']}): no se pudo leer ({str(e).splitlines()[0][:150]}). "
                           "Se reintenta la próxima vez.")
            break
        fecha = f"[{a['fecha']:%d/%m/%Y}] " if a["fecha"] else ""
        informe.append(f"{fecha}{a['titulo']}\n{a['url']}\n" + fd.describir(resumen))
        registro["vistos"].append(a["url"])
        registro["leidos"].append({"url": a["url"], "titulo": a["titulo"], "publicado": a["fecha"],
                                   "leido": datetime.now().isoformat(timespec="minutes"),
                                   "documento": resumen.get("documento"), "fecha": resumen.get("fecha")})
        guardar_registro(registro)
        novedad = novedades.registrar(resumen, a["url"])
        if novedad:
            de_esta_vez.append(novedad)
    if de_esta_vez and notificar:
        informe.append(f"Aviso: {novedades.avisar(de_esta_vez)}.")
    if not pendientes and fd.pendientes():
        # Sin avisos nuevos igual se reintenta el ticker de los borradores que no lo tienen (sale cerca de la liquidación)
        informe += fd.actualizar_borradores()
    if not pendientes:
        ultimo = registro["leidos"][-1] if registro["leidos"] else None
        informe.append("No hay avisos nuevos del Tesoro"
                       + (f" (último leído: {ultimo.get('titulo') or ultimo['url']})." if ultimo else "."))
    return informe


def main(argv: list[str]):
    if argv and argv[0] == "estado":
        registro = cargar_registro()
        print(f"{len(registro.get('vistos', []))} avisos dados por leídos. Últimos leídos:")
        for leido in registro["leidos"][-8:]:
            print(f"  {leido['leido']}: {leido.get('titulo') or ''} {leido['url']}")
        return
    if argv and argv[0] == "listado":
        registro = cargar_registro()
        avisos = [a for a in listar() if es_aviso(a["titulo"])]
        if _actualizar_version(registro, avisos):
            guardar_registro(registro)
        vistos = set(registro.get("vistos", []))
        for a in avisos:
            if True:
                print(f"{'leído   ' if a['url'] in vistos else 'PENDIENTE'} {a['fecha'] or '':<10} {a['titulo']}\n          {a['url']}")
        return
    if argv and argv[0] in ("marcar", "olvidar") and len(argv) > 1:
        registro = cargar_registro()
        registro.setdefault("vistos", [])
        if argv[0] == "marcar" and argv[1] not in registro["vistos"]:
            registro["vistos"].append(argv[1])
        if argv[0] == "olvidar":
            registro["vistos"] = [u for u in registro["vistos"] if u != argv[1]]
        guardar_registro(registro)
        print(f"{argv[1]}: {'dado por leído' if argv[0] == 'marcar' else 'se vuelve a leer en la próxima revisión'}.")
        return
    if argv and argv[0] == "desde":
        print("Ya no hace falta: la revisión lee el listado de noticias de Finanzas. Usá marcar u olvidar <URL>.")
        return
    if argv:
        print(__doc__)
        return
    print("\n\n".join(revisar()))


if __name__ == "__main__":
    main(sys.argv[1:])
