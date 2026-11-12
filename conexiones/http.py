"""Conexión HTTP común a todas las fuentes externas.

Todas las conexiones (bcra.py, series_tiempo.py, noticias.py, ...) piden datos a través de
get_json() o get_texto(). Así, el tiempo máximo de espera, los reintentos y la caché
se resuelven una sola vez.
"""
import hashlib
import json
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config


class ErrorAPI(Exception):
    """Error al consultar una fuente externa, con un mensaje entendible para el usuario y el modelo.

    estado: código HTTP de la respuesta, si lo hubo (ej.: 401 = sesión vencida).
    """

    def __init__(self, mensaje: str, estado: int | None = None):
        super().__init__(mensaje)
        self.estado = estado


def _crear_sesion() -> requests.Session:
    reintentos = Retry(
        total=config.HTTP_REINTENTOS,
        read=0,  # si la API ya tardó demasiado, no se insiste (evita esperas largas)
        backoff_factor=1,  # espera creciente entre intentos: 1s, 2s, 4s...
        status_forcelist=(429, 500, 502, 503, 504),  # errores momentáneos que vale la pena reintentar
        allowed_methods=("GET",),
    )
    sesion = requests.Session()
    sesion.mount("https://", HTTPAdapter(max_retries=reintentos))
    sesion.mount("http://", HTTPAdapter(max_retries=reintentos))
    sesion.headers["User-Agent"] = "Finianz/0.1"
    return sesion


# Una sola sesión para todo el programa: reutiliza conexiones y es más rápido
_sesion = _crear_sesion()


def get_json(url: str, params: dict | None = None, usar_cache: bool = True, cache_minutos: int | None = None,
             encabezados: dict | None = None):
    """GET que devuelve la respuesta JSON ya convertida a dict/list de Python.

    encabezados: headers extra (ej.: el token de una API). No forman parte de la clave de la caché.
    """
    return _get(url, params, usar_cache, cache_minutos, como_json=True, encabezados=encabezados)


def get_texto(url: str, params: dict | None = None, usar_cache: bool = True, cache_minutos: int | None = None) -> str:
    """GET que devuelve el contenido como texto (por ejemplo, un feed RSS en XML)."""
    return _get(url, params, usar_cache, cache_minutos, como_json=False)


def _get(url, params, usar_cache, cache_minutos, como_json, encabezados=None):
    """Si la misma consulta se hizo hace menos de cache_minutos (por defecto CACHE_MINUTOS),
    devuelve la copia guardada sin volver a llamar. Ante cualquier problema lanza ErrorAPI."""
    minutos = config.CACHE_MINUTOS if cache_minutos is None else cache_minutos
    clave = _clave_cache(url, params, como_json)
    if usar_cache:
        guardado = _leer_cache(clave, minutos)
        if guardado is not None:
            return guardado

    try:
        resp = _sesion.get(url, params=params, headers=encabezados, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        datos = resp.json() if como_json else resp.text
    except ValueError:  # va primero: el error de JSON de requests también es un RequestException
        raise ErrorAPI(f"La API no devolvió un JSON válido ({url}).") from None
    except requests.exceptions.Timeout:
        raise ErrorAPI(f"La API tardó más de {config.HTTP_TIMEOUT} segundos en responder ({url}).") from None
    except requests.exceptions.HTTPError as e:
        raise ErrorAPI(f"La API respondió con error {e.response.status_code} ({url}).", e.response.status_code) from None
    except requests.exceptions.RetryError:
        raise ErrorAPI(f"La API falló {config.HTTP_REINTENTOS + 1} veces seguidas; probablemente esté caída ({url}).") from None
    except requests.exceptions.RequestException as e:
        if "timed out" in str(e).lower():  # timeout de lectura que urllib3 informa como error de conexión
            raise ErrorAPI(f"La API tardó más de {config.HTTP_TIMEOUT} segundos en responder ({url}).") from None
        raise ErrorAPI(f"No se pudo conectar con la API ({url}). Revisá tu conexión a internet.") from None

    if usar_cache:
        _guardar_cache(clave, datos, minutos)
    return datos


def post_json(url: str, encabezados: dict | None = None, datos: dict | None = None):
    """POST sin caché (ej.: iniciar sesión en una API). Devuelve el JSON de la respuesta."""
    try:
        resp = _sesion.post(url, json=datos, headers=encabezados, timeout=config.HTTP_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except ValueError:
        raise ErrorAPI(f"La API no devolvió un JSON válido ({url}).") from None
    except requests.exceptions.HTTPError as e:
        raise ErrorAPI(f"La API respondió con error {e.response.status_code} ({url}).", e.response.status_code) from None
    except requests.exceptions.RequestException:
        raise ErrorAPI(f"No se pudo conectar con la API ({url}). Revisá tu conexión a internet.") from None


def limpiar_cache():
    """Borra todas las respuestas guardadas."""
    for archivo in config.CACHE_DIR.glob("*.json"):
        archivo.unlink(missing_ok=True)


# --- caché en disco: un archivo .json por consulta ---

def _clave_cache(url: str, params: dict | None, como_json: bool = True) -> str:
    texto = url + json.dumps(params or {}, sort_keys=True) + ("" if como_json else "|texto")
    return hashlib.sha256(texto.encode()).hexdigest()


def _leer_cache(clave: str, minutos: int):
    if minutos <= 0:
        return None
    archivo = config.CACHE_DIR / f"{clave}.json"
    if not archivo.exists():
        return None
    if time.time() - archivo.stat().st_mtime > minutos * 60:
        return None  # vencida
    try:
        return json.loads(archivo.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # archivo dañado: se ignora y se vuelve a pedir


def _guardar_cache(clave: str, datos, minutos: int):
    if minutos <= 0:
        return
    try:
        config.CACHE_DIR.mkdir(exist_ok=True)
        (config.CACHE_DIR / f"{clave}.json").write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass  # si no se puede guardar la caché, el programa sigue igual