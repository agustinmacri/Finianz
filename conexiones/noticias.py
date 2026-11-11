"""Client de noticias por RSS: búsqueda en Google News y feeds de medios.

Solo trae y limpia titulares, sin IA. Nunca descarga los artículos completos:
título, medio, fecha y un resumen corto alcanzan para que el agente sepa qué pasó
y cite la fuente.
"""
import html
import re
from datetime import datetime, timedelta, timezone

import feedparser

import config
from conexiones.http import ErrorAPI, get_texto

LARGO_RESUMEN = 280  # caracteres máximos del resumen de cada noticia


def buscar(tema: str, dias: int = 7, limite: int = 15) -> list[dict]:
    """Noticias de medios argentinos sobre un tema, de los últimos `dias` días, más nuevas primero.

    Usa la búsqueda de Google News por RSS. Acepta la sintaxis de búsqueda de Google:
    comillas para frases exactas ("licitación del Tesoro"), OR para alternativas.
    """
    params = {"q": f"{tema} when:{dias}d", **config.GOOGLE_NEWS_REGION}
    xml = get_texto(config.GOOGLE_NEWS_URL, params, cache_minutos=config.CACHE_NOTICIAS_MINUTOS)
    noticias = _procesar(xml, medio_por_defecto="Google News")
    return _filtrar_y_ordenar(noticias, horas=dias * 24, limite=limite)


def titulares(horas: int = 24, limite: int = 25) -> list[dict]:
    """Titulares recientes de todos los medios configurados en FUENTES_RSS, más nuevos primero.

    Si un medio no responde, se informa y se sigue con los demás.
    """
    noticias, errores = [], []
    for medio, url in config.FUENTES_RSS.items():
        try:
            xml = get_texto(url, cache_minutos=config.CACHE_NOTICIAS_MINUTOS)
            noticias += _procesar(xml, medio_por_defecto=medio)
        except ErrorAPI as e:
            errores.append(f"{medio}: {e}")
    if not noticias and errores:
        raise ErrorAPI("Ningún medio respondió. " + " | ".join(errores))
    return _filtrar_y_ordenar(noticias, horas=horas, limite=limite)


# --- procesamiento ---

def _procesar(xml: str, medio_por_defecto: str) -> list[dict]:
    feed = feedparser.parse(xml)
    if feed.bozo and not feed.entries:
        raise ErrorAPI(f"El feed de {medio_por_defecto} no tiene un formato válido.")

    noticias = []
    for e in feed.entries:
        medio = (e.get("source") or {}).get("title") or medio_por_defecto
        titulo = _limpiar(e.get("title", ""))
        # Google News agrega " - Medio" al final del título: se quita porque ya está en "medio"
        if titulo.endswith(f" - {medio}"):
            titulo = titulo[: -len(f" - {medio}")]
        resumen = _limpiar(e.get("summary", ""))
        noticias.append({
            "titulo": titulo,
            "medio": medio,
            "fecha": _fecha(e),
            "resumen": "" if resumen.startswith(titulo) else resumen[:LARGO_RESUMEN],
            "link": e.get("link", ""),
        })
    return noticias


def _filtrar_y_ordenar(noticias: list[dict], horas: int, limite: int) -> list[dict]:
    desde = datetime.now(timezone.utc) - timedelta(hours=horas)
    vistos, resultado = set(), []
    for n in sorted(noticias, key=lambda n: n["fecha"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True):
        clave = n["titulo"].lower()[:80]
        if clave in vistos or (n["fecha"] and n["fecha"] < desde):
            continue  # repetida (mismo título en varios medios o feeds) o vieja
        vistos.add(clave)
        resultado.append(n)
    return resultado[:limite]


def _fecha(entrada) -> datetime | None:
    estructura = entrada.get("published_parsed") or entrada.get("updated_parsed")
    return datetime(*estructura[:6], tzinfo=timezone.utc) if estructura else None


def _limpiar(texto: str) -> str:
    """Quita etiquetas HTML, entidades y espacios de más."""
    sin_html = re.sub(r"<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html.unescape(sin_html)).strip()