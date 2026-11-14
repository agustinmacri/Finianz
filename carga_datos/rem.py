"""Carga del Relevamiento de Expectativas de Mercado (REM) del BCRA en datos/rem.db.

El BCRA publica cada mes un Excel con las tablas del REM ("relevamiento-expectativas-mercado-tablas-
AAAA-MM.xlsx"). La API solo trae la inflación esperada a 12 meses; el Excel trae, para cada variable,
los próximos meses uno por uno y los próximos años, con la mediana, el promedio y los percentiles.

Cómo funciona:
- Se guardan los Excel en fuentes/rem/ (se suben a git, como los calendarios del INDEC).
- `python actualizar.py` lee todos y los carga; un relevamiento ya cargado se reemplaza.
- Se lee la hoja "Cuadros de resultados": cada bloque empieza con el nombre de la variable y una fila
  de encabezados ("Período", "Referencia", "Mediana"...).
"""
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import config
from admin_datos.db import conectar

CARPETA = config.FUENTES_DIR / "rem"
HOJA = "Cuadros de resultados"
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
         "septiembre": 9, "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12}
VARIABLES = [                     # (texto en el título del bloque, nombre en la base); el primero que coincide
    ("ipc nucleo", "IPC_NUCLEO"), ("ipc nivel general", "IPC"), ("tamar", "TAMAR"),
    ("tipo de cambio", "TIPO_CAMBIO"), ("exportaciones", "EXPORTACIONES"), ("importaciones", "IMPORTACIONES"),
    ("resultado primario", "RESULTADO_PRIMARIO"), ("desocupacion", "DESOCUPACION"), ("pib", "PIB"),
]
COLUMNAS = ["mediana", "promedio", "desvio", "maximo", "minimo", "p90", "p75", "p25", "p10", "participantes"]


def _normalizar(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", sin_tildes.lower()).strip()


def _variable(titulo: str) -> str:
    t = _normalizar(titulo)
    for clave, nombre in VARIABLES:
        if clave in t:
            return nombre
    return re.sub(r"[^a-z0-9]+", "_", t).strip("_").upper()


def _periodo(valor) -> str:
    if isinstance(valor, datetime):
        return f"{valor.year}-{valor.month:02d}"
    t = _normalizar(valor)
    if re.fullmatch(r"\d{4}", t):
        return t
    m = re.fullmatch(r"prox\. (\d+) meses", t)
    if m:
        return f"prox{m.group(1)}"
    return str(valor).strip()


def leer_excel(ruta: Path) -> tuple[str, list[dict]]:
    """(relevamiento AAAA-MM, filas) de un Excel de tablas del REM."""
    import openpyxl
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                  # el Excel trae imágenes que openpyxl no lee
        libro = openpyxl.load_workbook(ruta, data_only=True, read_only=True)
    if HOJA not in libro.sheetnames:
        raise ValueError(f"{ruta.name}: no tiene la hoja '{HOJA}'.")
    filas_hoja = [list(f) for f in libro[HOJA].iter_rows(min_col=2, max_col=13, values_only=True)]
    libro.close()

    relevamiento = None
    for fila in filas_hoja[:5]:
        m = re.search(r"(" + "|".join(MESES) + r")\s+(\d{4})", _normalizar(fila[0] or ""))
        if m:
            relevamiento = f"{m.group(2)}-{MESES[m.group(1)]:02d}"
            break
    if relevamiento is None:
        m = re.search(r"(\d{4})-(\d{2})", ruta.name)
        if not m:
            raise ValueError(f"{ruta.name}: no se encontró el mes del relevamiento.")
        relevamiento = f"{m.group(1)}-{m.group(2)}"

    salida, variable = [], None
    for i, fila in enumerate(filas_hoja):
        periodo, referencia, *valores = fila
        if periodo is None:
            continue
        siguiente = filas_hoja[i + 1][0] if i + 1 < len(filas_hoja) else None
        if _normalizar(siguiente or "") == "periodo":            # título de un bloque
            variable = _variable(periodo)
            continue
        if variable is None or _normalizar(periodo) == "periodo" or _normalizar(periodo).startswith("fuente"):
            continue
        if valores[0] is None:
            continue
        datos = dict(zip(COLUMNAS, valores))
        salida.append({"relevamiento": relevamiento, "variable": variable, "periodo": _periodo(periodo),
                       "referencia": referencia, **datos})
    if not any(f["variable"] == "IPC" for f in salida):
        raise ValueError(f"{ruta.name}: no se encontró el bloque de inflación (IPC nivel general).")
    return relevamiento, salida


def cargar(carpeta: Path = CARPETA) -> dict[str, int]:
    """Carga todos los Excel de la carpeta. Devuelve {relevamiento: filas guardadas}."""
    resumen = {}
    for ruta in sorted(carpeta.glob("*.xlsx")):
        relevamiento, filas = leer_excel(ruta)
        with conectar("rem") as con:
            con.execute("DELETE FROM rem WHERE relevamiento = ?", (relevamiento,))
            con.executemany(
                f"INSERT OR REPLACE INTO rem (relevamiento, variable, periodo, referencia, {', '.join(COLUMNAS)}, archivo) "
                f"VALUES ({', '.join('?' * (len(COLUMNAS) + 5))})",
                [(f["relevamiento"], f["variable"], f["periodo"], f["referencia"], *[f[c] for c in COLUMNAS], ruta.name)
                 for f in filas])
        resumen[relevamiento] = len(filas)
    return resumen
