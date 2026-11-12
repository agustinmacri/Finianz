"""API de PPI (Portfolio Personal Inversiones): precios de bonos, letras, ONs, acciones y CEDEARs.

SOLO LECTURA, a propósito: este archivo implementa únicamente consultas de precios y
datos de instrumentos. No incluye órdenes, transferencias ni datos de la cuenta, así que
nada en el proyecto puede operar con tu dinero. No se usa la librería oficial (ppi-client)
porque incluye todas esas funciones y suma dependencias de más; los endpoints son los mismos.

Documentación: https://itatppi.github.io/ppi-official-api-docs/
Claves en el .env: PPI_API_KEY (pública) y PPI_API_SECRET (privada). Nunca se imprimen
ni se guardan: el token de sesión vive solo en memoria mientras corre el programa.

Diagnóstico (muestra las respuestas reales de la API, sin claves):
    python -m conexiones.ppi AL30
"""
import json
import sys
from datetime import date, timedelta

import config
from conexiones.http import ErrorAPI, get_json, post_json

# Tipos de instrumento y plazos que acepta PPI (ver Configuration/InstrumentTypes y /Settlements)
PLAZOS = ("INMEDIATA", "A-24HS", "A-48HS", "A-72HS")
CACHE_PRECIO_MINUTOS = 1         # el precio actual se reutiliza un minuto como máximo

_sesion = {"token": None}        # token de acceso: solo en memoria


def _aplicacion() -> dict:
    return {"AuthorizedClient": config.PPI_AUTHORIZED_CLIENT, "ClientKey": config.PPI_CLIENT_KEY}


def _iniciar_sesion() -> str:
    if not (config.PPI_API_KEY and config.PPI_API_SECRET):
        raise ErrorAPI("Faltan PPI_API_KEY y PPI_API_SECRET en el .env (se generan en PPI: Gestiones → "
                       "Gestión de servicio API).")
    encabezados = _aplicacion() | {"ApiKey": config.PPI_API_KEY, "ApiSecret": config.PPI_API_SECRET}
    try:
        respuesta = post_json(f"{config.PPI_URL}/Account/LoginApi", encabezados)
    except ErrorAPI as e:
        if e.estado in (400, 401, 403):
            raise ErrorAPI(f"PPI rechazó el inicio de sesión (error {e.estado}). Revisá PPI_API_KEY y "
                           "PPI_API_SECRET en el .env, y que el servicio API esté activo en tu cuenta.") from None
        raise
    _sesion["token"] = respuesta["accessToken"]
    return _sesion["token"]


def _pedir(ruta: str, params: dict, cache_minutos: int | None = None):
    """GET autenticado. Si el token venció (401), inicia sesión de nuevo una vez."""
    for intento in (1, 2):
        token = _sesion["token"] or _iniciar_sesion()
        try:
            return get_json(f"{config.PPI_URL}/{ruta}", params, cache_minutos=cache_minutos,
                            encabezados=_aplicacion() | {"Authorization": f"Bearer {token}"})
        except ErrorAPI as e:
            if e.estado == 401 and intento == 1:
                _sesion["token"] = None
                continue
            raise


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------
def buscar_instrumento(ticker: str, tipo: str = "", mercado: str = "") -> list[dict]:
    """Instrumentos que coinciden con el ticker: [{'ticker', 'description', 'currency', 'type', 'market'}]."""
    return _pedir("MarketData/SearchInstrument",
                  {"ticker": ticker.upper(), "name": "", "market": mercado, "type": tipo}) or []


def precio_actual(ticker: str, tipo: str, plazo: str | None = None) -> dict:
    """Último precio: {'date', 'price', 'volume', 'openingPrice', 'max', 'min'}."""
    return _pedir("MarketData/Current", {"ticker": ticker.upper(), "type": tipo, "settlement": plazo or config.PPI_PLAZO},
                  cache_minutos=CACHE_PRECIO_MINUTOS)


def historico(ticker: str, tipo: str, desde: str | None = None, hasta: str | None = None,
              plazo: str | None = None) -> list[dict]:
    """Precios diarios entre dos fechas (AAAA-MM-DD; por defecto, el último año)."""
    desde = desde or (date.today() - timedelta(days=365)).isoformat()
    hasta = hasta or date.today().isoformat()
    return _pedir("MarketData/Search", {"ticker": ticker.upper(), "type": tipo, "dateFrom": desde, "dateTo": hasta,
                                        "settlement": plazo or config.PPI_PLAZO}) or []


def estimar_bono(ticker: str, precio: float, cantidad: float = 100, fecha: str | None = None) -> dict | list:
    """Calculadora de bonos de PPI: TIR, duration modificada, paridad, valor técnico y flujos.

    precio: precio por cada 100 de valor nominal; cantidad: valor nominal (100 por defecto).
    """
    return _pedir("MarketData/Bonds/Estimate", {
        "ticker": ticker.upper(), "date": fecha or date.today().isoformat(), "quantityType": "PAPELES",
        "quantity": cantidad, "price": precio})


def configuracion(tema: str) -> list:
    """Listas de referencia de PPI: InstrumentTypes, Settlements o Markets."""
    return _pedir(f"Configuration/{tema}", {}, cache_minutos=24 * 60)


# ---------------------------------------------------------------------------
# Diagnóstico: python -m conexiones.ppi TICKER
# ---------------------------------------------------------------------------
def _diagnostico(ticker: str):
    def mostrar(titulo, funcion):
        print(f"\n=== {titulo} ===")
        try:
            resultado = funcion()
            texto = json.dumps(resultado, ensure_ascii=False, indent=1)
            print(texto if len(texto) < 3000 else texto[:3000] + "\n... (recortado)")
            return resultado
        except ErrorAPI as e:
            print(f"Error: {e}")

    print(f"Ambiente: {'SANDBOX' if config.PPI_SANDBOX else 'producción'} | plazo por defecto: {config.PPI_PLAZO}")
    mostrar("Tipos de instrumento", lambda: configuracion("InstrumentTypes"))
    mostrar("Plazos", lambda: configuracion("Settlements"))
    encontrados = mostrar(f"Buscar {ticker}", lambda: buscar_instrumento(ticker))
    tipo = encontrados[0]["type"] if encontrados else "BONOS"
    actual = mostrar(f"Precio actual de {ticker} ({tipo})", lambda: precio_actual(ticker, tipo))
    mostrar(f"Histórico de {ticker}, últimos 10 días",
            lambda: historico(ticker, tipo, (date.today() - timedelta(days=10)).isoformat()))
    if tipo.upper() in ("BONOS", "LETRAS", "ON", "OBLIGACIONES NEGOCIABLES") and actual and actual.get("price"):
        mostrar(f"Calculadora de bonos para {ticker} a {actual['price']}", lambda: estimar_bono(ticker, actual["price"]))


if __name__ == "__main__":
    _diagnostico(sys.argv[1] if len(sys.argv) > 1 else "AL30")
