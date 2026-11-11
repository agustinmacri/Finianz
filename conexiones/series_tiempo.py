"""Client de la API de Series de Tiempo de datos.gob.ar (IPC INDEC, EMAE, salarios, etc.).

Solo sabe hablar con la API y devolver datos limpios de Python. No sabe nada de IA.

Hay miles de series: se encuentran con buscar_series(). Las más usadas se pueden
guardar en SERIES_CONOCIDAS con un nombre corto, para no tener que buscarlas cada vez.
"""
from datetime import date, timedelta

import config
from conexiones.http import ErrorAPI, get_json

# Nombre corto -> id de la serie. Agregá acá las que uses seguido (los ids salen de buscar_series).
SERIES_CONOCIDAS = {}

# Cómo pedir los datos. La API calcula las variaciones por nosotros.
# Las variaciones vienen como fracción: 0.021 significa 2,1%.
MODOS = {
    "valor": "value",                                           # el nivel de la serie
    "variacion": "percent_change",                              # contra el período anterior (ej. inflación mensual)
    "variacion_interanual": "percent_change_a_year_ago",        # contra el mismo período del año anterior
    "variacion_acumulada_anio": "percent_change_since_beginning_of_year",  # acumulada en el año
}

LIMITE_API = 1000  # máximo de valores que la API devuelve por consulta


def buscar_series(texto: str, limite: int = 10) -> list[dict]:
    """Busca series por texto. Devuelve id, título, unidad, frecuencia y rango de fechas de cada una."""
    datos = get_json(config.SERIES_BUSQUEDA_URL, params={"q": texto, "limit": limite})
    resultados = []
    for r in datos.get("data", []):
        campo, dataset = r.get("field", {}), r.get("dataset", {})
        resultados.append({
            "id": campo.get("id"),
            "descripcion": campo.get("description") or campo.get("title"),
            "unidad": campo.get("units"),
            "frecuencia": campo.get("frequency"),
            "desde": campo.get("time_index_start"),
            "hasta": campo.get("time_index_end"),
            "fuente": dataset.get("source") or dataset.get("publisher", {}).get("name"),
        })
    return resultados


def obtener_serie(
    serie: str,
    desde: str | None = None,
    hasta: str | None = None,
    modo: str = "valor",
    ultimos: int | None = None,
) -> list[dict]:
    """Valores de una serie, ordenados del más viejo al más nuevo.

    serie:  un id de la API o un nombre de SERIES_CONOCIDAS (ej. "ipc").
    desde / hasta: fechas 'AAAA-MM-DD'. Si no se indican, trae el último año.
    modo:   "valor", "variacion", "variacion_interanual" o "variacion_acumulada_anio".
    ultimos: si se indica, trae solo los últimos N valores (ignora desde/hasta).

    Devuelve [{'fecha': '2026-09-01', 'valor': 0.021}, ...]
    """
    if modo not in MODOS:
        raise ErrorAPI(f"Modo '{modo}' inválido. Opciones: {', '.join(MODOS)}.")
    id_serie = SERIES_CONOCIDAS.get(serie.lower(), serie)

    params = {"ids": id_serie, "representation_mode": MODOS[modo], "metadata": "none"}
    if ultimos:
        params["last"] = ultimos
    else:
        hasta = hasta or date.today().isoformat()
        desde = desde or (date.fromisoformat(hasta) - timedelta(days=365)).isoformat()
        params.update(start_date=desde, end_date=hasta, limit=LIMITE_API)

    datos = get_json(config.SERIES_TIEMPO_URL, params=params)
    # La API devuelve filas [fecha, valor]; los valores faltantes vienen como None
    serie_limpia = [{"fecha": f, "valor": v} for f, v in datos.get("data", []) if v is not None]
    if not serie_limpia:
        raise ErrorAPI(f"No hay datos para la serie '{serie}' en el período pedido.")
    return sorted(serie_limpia, key=lambda d: d["fecha"])