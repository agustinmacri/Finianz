"""Configuración central del proyecto.

Regla: lo que es secreto (claves) va en .env; lo que es configuración
(URLs, límites, tiempos) va acá, con un valor por defecto que se puede
sobrescribir desde .env si hace falta.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
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
# Conexiones HTTP (las usa clients/http.py para todas las APIs)
# ---------------------------------------------------------------------------
HTTP_TIMEOUT = _int("HTTP_TIMEOUT", 15)          # segundos máximos de espera por pedido
HTTP_REINTENTOS = _int("HTTP_REINTENTOS", 3)     # reintentos si la API falla momentáneamente
CACHE_MINUTOS = _int("CACHE_MINUTOS", 60)        # cuánto tiempo reutilizar una respuesta ya pedida

# ---------------------------------------------------------------------------
# APIs de datos (gratuitas, sin clave)
# ---------------------------------------------------------------------------
# BCRA – Principales Variables (reservas, tipo de cambio, tasas, CER, UVA...)
BCRA_URL = os.getenv("BCRA_URL", "https://api.bcra.gob.ar/estadisticas/v4.0/Monetarias")

# datos.gob.ar – Series de Tiempo (IPC INDEC, EMAE, salarios...)
SERIES_TIEMPO_URL = os.getenv("SERIES_TIEMPO_URL", "https://apis.datos.gob.ar/series/api/series/")
SERIES_BUSQUEDA_URL = os.getenv("SERIES_BUSQUEDA_URL", "https://apis.datos.gob.ar/series/api/search/")

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
# Rutas
# ---------------------------------------------------------------------------
PROMPTS_DIR = BASE_DIR / "prompts"
CACHE_DIR = BASE_DIR / ".cache"