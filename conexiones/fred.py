"""API de FRED (Reserva Federal de St. Louis): series económicas y calendario de publicaciones de EE. UU.

Documentación: https://fred.stlouisfed.org/docs/api/fred/
Requiere una clave gratuita en el .env (FRED_API_KEY). La clave viaja como parámetro
y nunca aparece en los mensajes de error ni en los nombres de la caché.
"""
from datetime import date, timedelta

import config
from conexiones.http import ErrorAPI, get_json

# El calendario cambia poco: se reutiliza la respuesta durante 12 horas
CACHE_FRED_MINUTOS = 12 * 60


# Transformaciones que FRED calcula del lado del servidor (parámetro 'units')
UNIDADES = {
    "valor": "lin",                     # nivel, sin transformar
    "variacion": "pch",                 # % contra el período anterior (mes, trimestre...)
    "variacion_interanual": "pc1",      # % contra el mismo período del año anterior
    "variacion_anualizada": "pca",      # % contra el período anterior, anualizada (así se informa el PBI)
}


def _pedir(ruta: str, cache_minutos: int = CACHE_FRED_MINUTOS, **params) -> dict:
    if not config.FRED_API_KEY:
        raise ErrorAPI("Falta FRED_API_KEY en el .env (clave gratuita en https://fredaccount.stlouisfed.org/apikeys).")
    params |= {"api_key": config.FRED_API_KEY, "file_type": "json"}
    try:
        return get_json(f"{config.FRED_URL}/{ruta}", params, cache_minutos=cache_minutos)
    except ErrorAPI as e:
        if "error 400" in str(e) or "error 403" in str(e):
            raise ErrorAPI(f"{e} Revisá el id de la serie, o que FRED_API_KEY del .env sea correcta.") from None
        raise


def listar_publicaciones() -> dict[str, int]:
    """Todas las publicaciones (releases) de FRED: nombre -> id."""
    publicaciones, offset = {}, 0
    while True:
        datos = _pedir("releases", limit=1000, offset=offset)
        for r in datos.get("releases", []):
            publicaciones[r["name"]] = r["id"]
        offset += 1000
        if offset >= datos.get("count", 0):
            return publicaciones


def fechas_publicacion(release_id: int, desde: str) -> list[str]:
    """Fechas de una publicación desde 'desde' (AAAA-MM-DD), incluidas las futuras ya programadas."""
    datos = _pedir("release/dates", release_id=release_id, sort_order="desc", limit=500,
                   include_release_dates_with_no_data="true")   # sin esto, FRED omite las fechas futuras
    return sorted({d["date"] for d in datos.get("release_dates", []) if d["date"] >= desde})


def buscar_series(texto: str, limite: int = 8) -> list[dict]:
    """Series de FRED que coinciden con el texto, las más consultadas primero."""
    datos = _pedir("series/search", search_text=texto, order_by="popularity", sort_order="desc", limit=limite)
    return [{"id": s["id"], "titulo": s["title"], "unidad": s.get("units", ""), "frecuencia": s.get("frequency", ""),
             "ajuste": s.get("seasonal_adjustment_short", ""), "hasta": s.get("observation_end", "")}
            for s in datos.get("seriess", [])]


def info_serie(serie_id: str) -> dict:
    """Título, unidad, frecuencia y última actualización de una serie."""
    series = _pedir("series", series_id=serie_id.upper()).get("seriess", [])
    if not series:
        raise ErrorAPI(f"FRED no tiene la serie '{serie_id}'.")
    s = series[0]
    return {"id": s["id"], "titulo": s["title"], "unidad": s.get("units", ""), "frecuencia": s.get("frequency", ""),
            "ajuste": s.get("seasonal_adjustment", ""), "actualizada": s.get("last_updated", "")}


def obtener_serie(serie_id: str, desde: str | None = None, hasta: str | None = None, modo: str = "valor") -> list[dict]:
    """Serie de FRED como [{'fecha': 'AAAA-MM-DD', 'valor': float}], de la más vieja a la más nueva.

    Sin fechas, trae el último año. modo: valor, variacion, variacion_interanual o variacion_anualizada
    (las variaciones vienen en porcentaje: 0.3 = 0,3%). Los valores faltantes (".") se omiten.
    """
    if modo not in UNIDADES:
        raise ValueError(f"modo '{modo}' inválido. Opciones: {', '.join(UNIDADES)}.")
    params = {"series_id": serie_id.upper(), "units": UNIDADES[modo],
              "observation_start": desde or (date.today() - timedelta(days=365)).isoformat()}
    if hasta:
        params["observation_end"] = hasta
    datos = _pedir("series/observations", cache_minutos=config.CACHE_MINUTOS, **params)
    return [{"fecha": o["date"], "valor": float(o["value"])}
            for o in datos.get("observations", []) if o["value"] not in (".", "")]
