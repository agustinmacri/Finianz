"""Configuración central del proyecto.

Regla: lo que es secreto (claves) va en .env; lo que es configuración
(URLs, límites, tiempos) va acá, con un valor por defecto que se puede
sobrescribir desde .env si hace falta.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
# El código que escribe el agente (ejecutar_python) corre con FINIANZ_SUBPROCESO=1: no relee el .env,
# así no accede a las claves que se le quitaron a propósito (por ejemplo, las del broker).
if not os.getenv("FINIANZ_SUBPROCESO"):
    load_dotenv(BASE_DIR / ".env")


def _int(nombre: str, defecto: int) -> int:
    return int(os.getenv(nombre, defecto))


def _bool(nombre: str, defecto: bool) -> bool:
    return os.getenv(nombre, str(defecto)).strip().lower() in ("true", "1", "si", "sí")


# ---------------------------------------------------------------------------
# Modelo de IA
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")
# Modelos a usar si el principal está saturado, separados por coma (vacío = sin respaldo)
GEMINI_MODELOS_RESPALDO = [m.strip() for m in os.getenv("GEMINI_MODELOS_RESPALDO", "").split(",") if m.strip()]

# ---------------------------------------------------------------------------
# Comportamiento del agente
# ---------------------------------------------------------------------------
# Tope de vueltas del loop, para que nunca quede girando indefinidamente
MAX_ITERACIONES = _int("MAX_ITERACIONES", 15)

# Si es True, te pide confirmación antes de ejecutar código Python en tu máquina
CONFIRMAR_CODIGO = _bool("CONFIRMAR_CODIGO", True)

# ---------------------------------------------------------------------------
# Conexiones HTTP (las usa conexiones/http.py para todas las APIs)
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = _int("HTTP_TIMEOUT", 15)          # segundos máximos de espera por pedido
HTTP_REINTENTOS = _int("HTTP_REINTENTOS", 3)     # reintentos si la API falla momentáneamente
CACHE_MINUTOS = _int("CACHE_MINUTOS", 60)        # cuánto tiempo reutilizar una respuesta ya pedida

# ---------------------------------------------------------------------------
# APIs de datos (gratuitas)
# ---------------------------------------------------------------------------
# BCRA – Principales Variables (reservas, tipo de cambio, tasas, CER, UVA...)
BCRA_URL = os.getenv("BCRA_URL", "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias")

# datos.gob.ar – Series de Tiempo (IPC INDEC, EMAE, salarios...)
SERIES_TIEMPO_URL = os.getenv("SERIES_TIEMPO_URL", "https://apis.datos.gob.ar/series/api/series/")
SERIES_BUSQUEDA_URL = os.getenv("SERIES_BUSQUEDA_URL", "https://apis.datos.gob.ar/series/api/search/")

# FRED (Reserva Federal de St. Louis) – calendario de publicaciones de EE. UU.
# Requiere una clave gratuita: FRED_API_KEY en el .env (https://fredaccount.stlouisfed.org/apikeys)
FRED_API_KEY = os.getenv("FRED_API_KEY")
FRED_URL = os.getenv("FRED_URL", "https://api.stlouisfed.org/fred")

# PPI (Portfolio Personal Inversiones) – precios de mercado. Solo lectura: el proyecto no envía órdenes.
# Las claves se generan en PPI: Gestiones → Gestión de servicio API.
PPI_API_KEY = os.getenv("PPI_API_KEY")          # clave pública
PPI_API_SECRET = os.getenv("PPI_API_SECRET")    # clave privada
PPI_SANDBOX = _bool("PPI_SANDBOX", False)       # true = ambiente de prueba de PPI
# Identificación de la aplicación que pide la API (valores públicos de la librería oficial de PPI)
PPI_AUTHORIZED_CLIENT = os.getenv("PPI_AUTHORIZED_CLIENT", "API_CLI_PYTHON")
PPI_CLIENT_KEY = os.getenv("PPI_CLIENT_KEY", "ppPYTHONSb" if PPI_SANDBOX else "pp19PythonApp12")
PPI_URL = os.getenv("PPI_URL", "https://clientapisbx.portfoliopersonal.com/api/1.0" if PPI_SANDBOX
                    else "https://clientapi.portfoliopersonal.com/api/1.0")
PPI_PLAZO = os.getenv("PPI_PLAZO", "A-24HS")    # plazo de liquidación por defecto para los precios

# ---------------------------------------------------------------------------
# Noticias (fuentes gratuitas por RSS)
# ---------------------------------------------------------------------------
# Búsqueda por tema en Google News, limitada a Argentina y en español
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_REGION = {"hl": "es-419", "gl": "AR", "ceid": "AR:es-419"}

# Feeds de medios para titulares del día: nombre -> URL. Agregá los que quieras.
FUENTES_RSS = {
    "Ámbito Economía": "https://www.ambito.com/rss/pages/economia.xml",
    "Ámbito Finanzas": "https://www.ambito.com/rss/pages/finanzas.xml",
}

# Las noticias cambian rápido: se guardan menos tiempo que los datos económicos
CACHE_NOTICIAS_MINUTOS = _int("CACHE_NOTICIAS_MINUTOS", 15)

# ---------------------------------------------------------------------------
# Base de datos local y calendarios
# ---------------------------------------------------------------------------
DATOS_DIR = BASE_DIR / "datos"               # bases SQLite (no se suben a git): feriados, publicaciones, cartera
CALENDARIOS_DIR = BASE_DIR / "calendarios"   # sí se sube a git: correcciones manuales

# Feriados: se cargan desde este año hasta el año próximo
FERIADOS_DESDE = _int("FERIADOS_DESDE", 2016)

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
PROMPTS_DIR = BASE_DIR / "prompts"
CACHE_DIR = BASE_DIR / ".cache"