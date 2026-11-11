"""Herramientas de datos macro para el agente: lo que el modelo ve y puede usar.

Toman las conexiones (bcra, series_tiempo) y presentan los datos en texto corto:
siempre con la fecha del último dato, y resumidos si la serie es larga,
para gastar pocos tokens.
"""
import math
from datetime import date

from conexiones import bcra, series_tiempo 
from conexiones.http import ErrorAPI

MAX_PUNTOS = 40      # si la serie tiene más valores, se resume
PUNTOS_RESUMEN = 15  # cuántos de los últimos valores se muestran al resumir
ANIOS_VIGENCIA = 8   # las series de datos.gob.ar sin datos en este plazo se descartan por viejas
# Códigos de periodicidad del BCRA, en palabras
_FRECUENCIAS = {"D": "diaria", "S": "semanal", "M": "mensual", "T": "trimestral", "A": "anual"}

# ---------------------------------------------------------------------------
# 1. Buscar indicadores
# ---------------------------------------------------------------------------
def buscar_indicador(texto: str) -> str:
    lineas = []

    try:
        variables = bcra.buscar_variables(texto)[:6]  # vienen ordenadas: las más relevantes primero
        if variables:
            lineas.append("BCRA (usar consultar_bcra con el id). Hay variables con el mismo nombre: "
                          "distinguilas por unidad y frecuencia:")
            for v in variables:
                detalle = " | ".join(x for x in (v["unidad"], _FRECUENCIAS.get(v["periodicidad"], v["periodicidad"])) if x)
                lineas.append(
                    f"  id={v['id']} | {v['descripcion'].strip()} | {detalle or 's/d'} | "
                    f"último: {_num(v['ultimo_valor'])} ({v['ultima_fecha']})"
                )
    except ErrorAPI as e:
        lineas.append(f"BCRA: no disponible ({e})")

    try:
        corte = str(date.today().year - ANIOS_VIGENCIA)
        series = [s for s in series_tiempo.buscar_series(texto, limite=15) if (s["hasta"] or "") >= corte][:6]
        if series:
            lineas.append("datos.gob.ar (usar consultar_serie con el id):")
            for s in series:
                lineas.append(
                    f"  id={s['id']} | {s['descripcion']} | {s['unidad']} | "
                    f"datos hasta {s['hasta']} | fuente: {s['fuente']}"
                )
    except ErrorAPI as e:
        lineas.append(f"datos.gob.ar: no disponible ({e})")

    return "\n".join(lineas) or f"No se encontraron indicadores para '{texto}'. Probá con otras palabras."


BUSCAR_INDICADOR = {
    "name": "buscar_indicador",
    "description": (
        "Busca indicadores económicos de Argentina por palabras clave en el BCRA "
        "(reservas, tipo de cambio, tasas, inflación, CER, UVA, base monetaria) y en "
        "datos.gob.ar (EMAE, salarios, actividad y otras series oficiales). "
        "Devuelve el id de cada indicador y, para el BCRA, su último valor con fecha. "
        "Usala primero para encontrar el id; si el último valor alcanza, no hace falta consultar más. "
        "Para inflación, preferí siempre la del BCRA."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "texto": {"type": "string", "description": "Palabras clave, ej: 'reservas', 'inflacion mensual', 'emae'"},
        },
        "required": ["texto"],
    },
}


# ---------------------------------------------------------------------------
# 2. Serie histórica del BCRA
# ---------------------------------------------------------------------------
def consultar_bcra(id_variable: int, desde: str | None = None, hasta: str | None = None) -> str:
    try:
        serie = bcra.obtener_serie(int(id_variable), desde, hasta)
    except ErrorAPI as e:
        return f"Error: {e}"
    return _formatear(serie, titulo=f"BCRA variable {id_variable}")


CONSULTAR_BCRA = {
    "name": "consultar_bcra",
    "description": (
        "Devuelve la serie histórica de una variable del BCRA (el id sale de buscar_indicador). "
        "Si no se indican fechas, trae el último año. Las series largas vienen resumidas: "
        "para más detalle, pedí un rango de fechas más corto."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id_variable": {"type": "integer", "description": "Id de la variable del BCRA"},
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (opcional)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (opcional)"},
        },
        "required": ["id_variable"],
    },
}


# ---------------------------------------------------------------------------
# 3. Serie de datos.gob.ar
# ---------------------------------------------------------------------------
def consultar_serie(id_serie: str, modo: str = "valor", desde: str | None = None, hasta: str | None = None) -> str:
    try:
        serie = series_tiempo.obtener_serie(id_serie, desde, hasta, modo=modo)
    except ErrorAPI as e:
        return f"Error: {e}"
    # La API devuelve las variaciones como fracción (0.021): se muestran en porcentaje
    es_variacion = modo != "valor"
    if es_variacion:
        serie = [{"fecha": d["fecha"], "valor": d["valor"] * 100} for d in serie]
    return _formatear(serie, titulo=f"Serie {id_serie} ({modo})", sufijo="%" if es_variacion else "")


CONSULTAR_SERIE = {
    "name": "consultar_serie",
    "description": (
        "Devuelve una serie de datos.gob.ar (el id sale de buscar_indicador). "
        "Puede calcular variaciones directamente con el parámetro modo. "
        "Si no se indican fechas, trae el último año."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id_serie": {"type": "string", "description": "Id de la serie en datos.gob.ar"},
            "modo": {
                "type": "string",
                "enum": list(series_tiempo.MODOS),
                "description": (
                    "valor: el nivel de la serie; variacion: contra el período anterior; "
                    "variacion_interanual: contra un año antes; variacion_acumulada_anio: acumulada en el año"
                ),
            },
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (opcional)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (opcional)"},
        },
        "required": ["id_serie"],
    },
}


# ---------------------------------------------------------------------------
# 4. Inflación acumulada (calculada en código, no por el modelo)
# ---------------------------------------------------------------------------
def inflacion_acumulada(desde: str | None = None, hasta: str | None = None) -> str:
    try:
        candidatas = [v for v in bcra.buscar_variables("inflacion mensual")
                      if "inflacion mensual" in bcra.normalizar(v["descripcion"])]
        if not candidatas:
            return "Error: no se encontró la variable de inflación mensual en el BCRA."
        hoy = date.today()
        desde = desde or f"{hoy.year}-01-01"
        serie = bcra.obtener_serie(candidatas[0]["id"], desde, hasta or hoy.isoformat())
    except ErrorAPI as e:
        return f"Error: {e}"

    acumulado = (math.prod(1 + d["valor"] / 100 for d in serie) - 1) * 100
    meses = "\n".join(f"{d['fecha'][:7]}: {_num(d['valor'])}%" for d in serie)
    return (
        f"Inflación mensual (BCRA) desde {serie[0]['fecha'][:7]} hasta {serie[-1]['fecha'][:7]} "
        f"({len(serie)} meses):\n{meses}\n"
        f"INFLACIÓN ACUMULADA (compuesta): {acumulado:.2f}%\n"
        f"ÚLTIMO DATO DISPONIBLE: {serie[-1]['fecha'][:7]}"
    )


INFLACION_ACUMULADA = {
    "name": "inflacion_acumulada",
    "description": (
        "Calcula la inflación acumulada (compuesta) entre dos fechas con los datos mensuales del BCRA, "
        "y devuelve también la inflación de cada mes. Sin fechas, calcula lo que va del año. "
        "Usala para cualquier pregunta de inflación acumulada, en el año o en un período."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (opcional; por defecto, 1 de enero de este año)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (opcional; por defecto, hoy)"},
        },
    },
}


# ---------------------------------------------------------------------------
# Registro: (definición, función) de cada herramienta de este archivo
# ---------------------------------------------------------------------------
HERRAMIENTAS = [
    (BUSCAR_INDICADOR, buscar_indicador),
    (CONSULTAR_BCRA, consultar_bcra),
    (CONSULTAR_SERIE, consultar_serie),
    (INFLACION_ACUMULADA, inflacion_acumulada),
]


# --- formato de salida ---

def _num(valor) -> str:
    if valor is None:
        return "s/d"
    return f"{valor:,.4f}".rstrip("0").rstrip(".") if isinstance(valor, float) else f"{valor:,}"


def _formatear(serie: list[dict], titulo: str, sufijo: str = "") -> str:
    ultimo = serie[-1]
    valores = [d["valor"] for d in serie]
    encabezado = (
        f"{titulo}: {len(serie)} valores entre {serie[0]['fecha']} y {ultimo['fecha']}.\n"
        f"ÚLTIMO DATO DISPONIBLE: {ultimo['fecha']} = {_num(ultimo['valor'])}{sufijo}"
    )
    if len(serie) <= MAX_PUNTOS:
        detalle = "\n".join(f"{d['fecha']}: {_num(d['valor'])}{sufijo}" for d in serie)
        return f"{encabezado}\n{detalle}"

    resumen = (
        f"Resumen del período: primero {serie[0]['fecha']} = {_num(valores[0])}{sufijo}, "
        f"mínimo {_num(min(valores))}{sufijo}, máximo {_num(max(valores))}{sufijo}, "
        f"promedio {_num(sum(valores) / len(valores))}{sufijo}"
    )
    recientes = "\n".join(f"{d['fecha']}: {_num(d['valor'])}{sufijo}" for d in serie[-PUNTOS_RESUMEN:])
    return f"{encabezado}\n{resumen}\nÚltimos {PUNTOS_RESUMEN} valores:\n{recientes}"