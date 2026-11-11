"""API de FRED (Reserva Federal de St. Louis): calendario de publicaciones de EE. UU.

Documentación: https://fred.stlouisfed.org/docs/api/fred/
Requiere una clave gratuita en el .env (FRED_API_KEY). La clave viaja como parámetro
y nunca aparece en los mensajes de error ni en los nombres de la caché.
"""
import config
from conexiones.http import ErrorAPI, get_json

# El calendario cambia poco: se reutiliza la respuesta durante 12 horas
CACHE_FRED_MINUTOS = 12 * 60


def _pedir(ruta: str, **params) -> dict:
    if not config.FRED_API_KEY:
        raise ErrorAPI("Falta FRED_API_KEY en el .env (clave gratuita en https://fredaccount.stlouisfed.org/apikeys).")
    params |= {"api_key": config.FRED_API_KEY, "file_type": "json"}
    try:
        return get_json(f"{config.FRED_URL}/{ruta}", params, cache_minutos=CACHE_FRED_MINUTOS)
    except ErrorAPI as e:
        if "error 400" in str(e) or "error 403" in str(e):
            raise ErrorAPI(f"{e} Revisá que FRED_API_KEY del .env sea correcta.") from None
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
