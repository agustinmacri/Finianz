"""Bases de datos locales (SQLite): un archivo por tema en la carpeta datos/.

    datos/
    ├── feriados.db        feriados de Argentina y EE. UU. por calendario   (regenerable)
    ├── publicaciones.db   fechas de publicación: INDEC, FRED, licitaciones  (regenerable)
    ├── precios.db         precios diarios de los activos consultados       (NO regenerable del todo: respaldar)
    └── cartera.db         posiciones, operaciones y pronósticos propios     (NO regenerable: respaldar)

Acá se definen las tablas de cada base y la forma de conectarse. Las consultas de cada
tema viven en su propio archivo de esta carpeta (por ejemplo, feriados.py).
"""
import sqlite3
from contextlib import contextmanager

import config

# Todas las bases tienen esta tabla: guarda cuándo y desde dónde se actualizaron
METADATOS = """
CREATE TABLE IF NOT EXISTS metadatos (
    clave       TEXT PRIMARY KEY,
    valor       TEXT,
    actualizado TEXT
);
"""

# Base -> tablas propias. Las que todavía están vacías se completan en su etapa.
ESQUEMAS = {
    "feriados": """
        CREATE TABLE IF NOT EXISTS feriados (
            fecha       TEXT NOT NULL,   -- AAAA-MM-DD
            calendario  TEXT NOT NULL,   -- AR, AR_BANCOS, BYMA, US, NYSE, US_BONOS
            nombre      TEXT NOT NULL,
            fuente      TEXT NOT NULL,   -- 'holidays', 'aproximado' o 'ajuste'
            PRIMARY KEY (fecha, calendario)
        );
        CREATE INDEX IF NOT EXISTS idx_feriados_calendario ON feriados (calendario, fecha);
    """,
    "publicaciones": """
        CREATE TABLE IF NOT EXISTS publicaciones (
            fecha        TEXT NOT NULL,   -- AAAA-MM-DD
            hora         TEXT,            -- HH:MM, hora de Argentina (si se conoce)
            pais         TEXT NOT NULL,   -- AR, US
            organismo    TEXT NOT NULL,   -- INDEC, BCRA, BLS, BEA, Fed...
            codigo       TEXT,            -- código del catálogo (IPC, CPI...); vacío si no se sigue
            titulo       TEXT NOT NULL,   -- título tal como lo publica la fuente
            periodo      TEXT,            -- período al que se refiere el dato ("Octubre de 2026")
            importancia  TEXT NOT NULL,   -- alta, media o baja
            fuente       TEXT NOT NULL,   -- indec_pdf, fred, manual o regla
            PRIMARY KEY (fecha, organismo, titulo)
        );
        CREATE INDEX IF NOT EXISTS idx_publicaciones_fecha ON publicaciones (fecha, importancia);
        CREATE INDEX IF NOT EXISTS idx_publicaciones_codigo ON publicaciones (codigo, fecha);
    """,
          "precios": """
          CREATE TABLE IF NOT EXISTS instrumentos (
              ticker          TEXT PRIMARY KEY,   -- AL30, AL30D, TX26, GGAL...
              tipo            TEXT NOT NULL,      -- BONOS, LETRAS, ON, ACCIONES, CEDEARS... (según la fuente)
              moneda          TEXT,               -- moneda en la que cotiza ese ticker
              descripcion     TEXT,
              isin            TEXT,               -- une las versiones en distintas monedas (AL30, AL30D, AL30C)
              mercado         TEXT,               -- BYMA, ROFEX...
              fuente          TEXT NOT NULL,      -- de dónde se bajan sus precios (ppi)
              seguido_desde   TEXT NOT NULL       -- cuándo se consultó por primera vez
          );
          CREATE TABLE IF NOT EXISTS precios (
              ticker    TEXT NOT NULL,
              plazo     TEXT NOT NULL,            -- plazo de liquidación: INMEDIATA, A-24HS...
              fecha     TEXT NOT NULL,            -- AAAA-MM-DD
              apertura  REAL,
              maximo    REAL,
              minimo    REAL,
              cierre    REAL NOT NULL,
              volumen   REAL,
              fuente    TEXT NOT NULL,            -- ppi, data912, manual...
              PRIMARY KEY (ticker, plazo, fecha)
          );
      """,
    "cartera": "",         # fase B: posiciones, operaciones y registro de pronósticos
}


def ruta(base: str):
    if base not in ESQUEMAS:
        raise ValueError(f"Base '{base}' desconocida. Opciones: {', '.join(ESQUEMAS)}.")
    return config.DATOS_DIR / f"{base}.db"


@contextmanager
def conectar(base: str):
    """Abre una base, crea sus tablas si no existen y confirma los cambios al terminar.

    Uso:
        with conectar("feriados") as con:
            con.execute(...)

    Si algo falla dentro del bloque, se deshacen todos los cambios (no queda a medias).
    """
    archivo = ruta(base)
    config.DATOS_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(archivo)
    con.row_factory = sqlite3.Row  # las filas se leen como diccionarios: fila["fecha"]
    try:
        con.executescript(METADATOS + ESQUEMAS[base])
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def leer_metadato(base: str, clave: str) -> str | None:
    if not ruta(base).exists():
        return None  # no se crea el archivo solo para leer: así una base vacía no aparece de la nada
    with conectar(base) as con:
        fila = con.execute("SELECT valor FROM metadatos WHERE clave = ?", (clave,)).fetchone()
    return fila["valor"] if fila else None
