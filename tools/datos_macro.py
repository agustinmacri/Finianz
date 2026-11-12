"""Herramientas de datos macro para el agente: lo que el modelo ve y puede usar.

Toman las conexiones (bcra, series_tiempo y fred para EE. UU.) y presentan los datos en texto corto:
siempre con la fecha del último dato, y resumidos si la serie es larga,
para gastar pocos tokens.
"""
import math
from datetime import date, timedelta

from calculos import series as calc
from conexiones import bcra, fred, series_tiempo
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
def _con_modo(obtener, modo: str, desde: str | None, hasta: str | None) -> tuple[list[dict], str]:
    """Trae los niveles (con datos previos si hace falta) y calcula la variación en el proyecto.

    Devuelve (serie, aviso): el aviso lista las fechas con dato pero sin variación calculable.
    """
    hasta = hasta or date.today().isoformat()
    if modo == "valor":
        return obtener(desde, hasta), ""
    desde = desde or (date.fromisoformat(hasta) - timedelta(days=365)).isoformat()
    niveles = obtener(calc.desde_extendido(desde), hasta)
    serie = calc.transformar(niveles, modo)
    sin_calculo = calc.faltantes(niveles, serie, modo, desde)
    aviso = "".join(
        f"\nAVISO: no existe {modo.replace('_', ' ')} para {f['fecha']} porque la fuente no tiene el dato de "
        f"{f['base']} (no se publicó). No es una demora: esa variación no va a aparecer más adelante. Explicalo así."
        for f in sin_calculo)
    return calc.recortar(serie, desde, hasta), aviso


def consultar_serie(id_serie: str, modo: str = "valor", desde: str | None = None, hasta: str | None = None) -> str:
    try:
        serie, aviso = _con_modo(lambda d, h: series_tiempo.obtener_serie(id_serie, d, h), modo, desde, hasta)
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    if not serie:
        return f"Serie {id_serie}: no hay datos suficientes para calcular '{modo}' en ese período.{aviso}"
    calculo = "" if modo == "valor" else ", calculada por Finianz sobre los niveles"
    return _formatear(serie, titulo=f"Serie {id_serie} ({modo}{calculo})", sufijo="" if modo == "valor" else "%") + aviso


CONSULTAR_SERIE = {
    "name": "consultar_serie",
    "description": (
        "Devuelve una serie de datos.gob.ar (el id sale de buscar_indicador). "
        "Con el parámetro modo, calcula variaciones (en %) sobre los niveles de la serie. "
        "Si no se indican fechas, trae el último año."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "id_serie": {"type": "string", "description": "Id de la serie en datos.gob.ar"},
            "modo": {
                "type": "string",
                "enum": list(calc.MODOS),
                "description": (
                    "valor: el nivel de la serie; variacion: contra el período anterior; "
                    "variacion_interanual: contra un año antes; variacion_anualizada: la del período llevada a un año; "
                    "variacion_acumulada_anio: acumulada en el año"
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
def _inflacion_mensual(desde: str, hasta: str) -> list[dict]:
    """Serie de inflación mensual del BCRA (en %, 2.1 = 2,1%). Lanza ErrorAPI si no la encuentra."""
    candidatas = [v for v in bcra.buscar_variables("inflacion mensual")
                  if "inflacion mensual" in bcra.normalizar(v["descripcion"])]
    if not candidatas:
        raise ErrorAPI("no se encontró la variable de inflación mensual en el BCRA.")
    serie = bcra.obtener_serie(candidatas[0]["id"], desde, hasta)
    if not serie:
        raise ErrorAPI(f"el BCRA no tiene inflación mensual entre {desde} y {hasta}.")
    return serie


def inflacion_acumulada(desde: str | None = None, hasta: str | None = None) -> str:
    try:
        hoy = date.today()
        serie = _inflacion_mensual(desde or f"{hoy.year}-01-01", hasta or hoy.isoformat())
    except ErrorAPI as e:
        return f"Error: {e}"

    acumulado = (math.prod(1 + d["valor"] / 100 for d in serie) - 1) * 100
    n = len(serie)
    # Anualización del período: ((1 + acumulada)^(12/n) − 1). Con 12 meses o más, no hace falta.
    anualizada = ((1 + acumulado / 100) ** (12 / n) - 1) * 100
    meses = "\n".join(f"{d['fecha'][:7]}: {_num(d['valor'])}%" for d in serie)
    return (
        f"Inflación mensual (BCRA) desde {serie[0]['fecha'][:7]} hasta {serie[-1]['fecha'][:7]} "
        f"({n} meses):\n{meses}\n"
        f"INFLACIÓN ACUMULADA (compuesta): {acumulado:.2f}%\n"
        + (f"ANUALIZADA (si el ritmo promedio de estos {n} meses se mantuviera un año, (1 + acumulada)^(12/{n}) − 1): "
           f"{anualizada:.1f}%\n" if n < 12 else "")
        + f"ÚLTIMO DATO DISPONIBLE: {serie[-1]['fecha'][:7]}"
    )


INFLACION_ACUMULADA = {
    "name": "inflacion_acumulada",
    "description": (
        "Solo Argentina. Calcula la inflación acumulada (compuesta) entre dos fechas con los datos mensuales del BCRA, "
        "y devuelve también la inflación de cada mes y la acumulada anualizada (si el período tiene menos de 12 meses). "
        "Sin fechas, calcula lo que va del año. Usala para cualquier pregunta de inflación acumulada, en el año o en un "
        "período, y para anualizar esa acumulada. Para EE. UU. usá consultar_fred con modo variacion_acumulada_anio."
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
# 4 bis. Inflación anualizada (el ritmo mensual llevado a un año)
# ---------------------------------------------------------------------------
FUENTES_INFLACION = {
    "AR": "INDEC vía BCRA",
    "US": "BLS vía FRED; CPI desestacionalizado, CPIAUCSL; variaciones calculadas por Finianz",
}


def _inflacion_mensual_us(desde: str, hasta: str) -> list[dict]:
    """Inflación mensual de EE. UU. (en %), calculada sobre los niveles del CPI desestacionalizado."""
    niveles = fred.obtener_serie("CPIAUCSL", calc.desde_extendido(desde), hasta)
    return calc.recortar(calc.transformar(niveles, "variacion"), desde, hasta)


def _meses_consecutivos(tramo: list[dict]) -> bool:
    """¿El tramo son meses seguidos? (falta un mes, por ejemplo, si la fuente no lo publicó)."""
    a, b = tramo[0]["fecha"], tramo[-1]["fecha"]
    return (int(b[:4]) - int(a[:4])) * 12 + int(b[5:7]) - int(a[5:7]) == len(tramo) - 1


def inflacion_anualizada(pais: str = "AR", hasta: str | None = None) -> str:
    pais = pais.upper()
    if pais not in FUENTES_INFLACION:
        return "Error: pais tiene que ser AR (Argentina) o US (Estados Unidos)."
    try:
        fin = date.fromisoformat(hasta) if hasta else date.today()
        desde = (fin - timedelta(days=400)).isoformat()
        serie = (_inflacion_mensual(desde, fin.isoformat()) if pais == "AR"
                 else _inflacion_mensual_us(desde, fin.isoformat()))
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    if not serie:
        return f"Error: no hay inflación mensual de {pais} hasta {fin}."

    lineas = []
    for n in (1, 3, 6):
        if len(serie) < n:
            continue
        tramo = serie[-n:]
        if not _meses_consecutivos(tramo):
            lineas.append(f"Promedio de los últimos {n} meses: no se calcula, falta algún mes en la fuente.")
            continue
        promedio = (math.prod(1 + d["valor"] / 100 for d in tramo) ** (1 / n) - 1) * 100   # promedio geométrico
        anualizada = ((1 + promedio / 100) ** 12 - 1) * 100
        nombre = "Último mes" if n == 1 else f"Promedio de los últimos {n} meses"
        lineas.append(f"{nombre} ({tramo[0]['fecha'][:7]} a {tramo[-1]['fecha'][:7]}): "
                      f"mensual {promedio:.2f}% → ANUALIZADA {anualizada:.1f}%")
    meses = ", ".join(f"{d['fecha'][:7]}: {_num(d['valor'])}%" for d in serie[-6:])
    return (f"Inflación anualizada de {'Argentina' if pais == 'AR' else 'EE. UU.'} ({FUENTES_INFLACION[pais]}). "
            f"Fórmula: (1 + mensual)^12 − 1; para varios meses, con el promedio geométrico de las mensuales.\n"
            + "\n".join(lineas) + f"\nMeses usados: {meses}\nÚLTIMO DATO DISPONIBLE: {serie[-1]['fecha'][:7]}")


INFLACION_ANUALIZADA = {
    "name": "inflacion_anualizada",
    "description": (
        "Inflación anualizada de Argentina (pais='AR') o de EE. UU. (pais='US'): lleva el ritmo mensual a un año, "
        "((1 + mensual)^12 − 1). Devuelve la del último mes y la del promedio de los últimos 3 y 6 meses, ya calculadas. "
        "Usala para preguntas de inflación anualizada o de ritmo de inflación, y para comparar la inflación mensual "
        "con el REM o con la interanual. No es lo mismo que la acumulada ni que la interanual."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "pais": {"type": "string", "enum": ["AR", "US"],
                     "description": "AR = Argentina (por defecto), US = Estados Unidos. Si la conversación venía "
                                    "hablando de EE. UU., usá US."},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (opcional; por defecto, el último dato)"},
        },
    },
}


# ---------------------------------------------------------------------------
# 5. Estados Unidos (FRED)
# ---------------------------------------------------------------------------
# Series más usadas: van en la descripción para que el modelo no tenga que buscarlas
SERIES_EEUU = {
    "CPIAUCSL": "CPI general, desestacionalizado (para la variación mensual)",
    "CPIAUCNS": "CPI general, sin desestacionalizar (para la interanual, como la informa el BLS)",
    "CPILFESL": "CPI núcleo, desestacionalizado (mensual)",
    "CPILFENS": "CPI núcleo, sin desestacionalizar (interanual)",
    "PCEPI": "PCE general",
    "PCEPILFE": "PCE núcleo (el que mira la Fed)",
    "PAYEMS": "empleo no agrícola, en miles de puestos",
    "UNRATE": "tasa de desempleo",
    "GDPC1": "PBI real (trimestral)",
    "DFEDTARU": "techo del rango de la tasa de la Fed",
    "DFEDTARL": "piso del rango de la tasa de la Fed",
    "EFFR": "tasa efectiva de fondos federales (diaria)",
    "DGS2": "rendimiento del Tesoro a 2 años",
    "DGS10": "rendimiento del Tesoro a 10 años",
    "RSAFS": "ventas minoristas",
    "PPIFIS": "PPI demanda final",
    "JTSJOL": "vacantes laborales (JOLTS)",
    "UMCSENT": "confianza del consumidor (U. de Michigan)",
    "INDPRO": "producción industrial",
}
def consultar_fred(serie: str, modo: str = "valor", desde: str | None = None, hasta: str | None = None) -> str:
    try:
        info = fred.info_serie(serie)
        datos, aviso = _con_modo(lambda d, h: fred.obtener_serie(serie, d, h), modo,
                                 desde or (date.today() - timedelta(days=730)).isoformat(), hasta)
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    if not datos:
        return f"FRED {info['id']}: sin datos suficientes para '{modo}' en ese período.{aviso}"
    unidad = (info["unidad"] if modo == "valor"
              else f"{modo.replace('_', ' ')} en %, calculada por Finianz (sobre: {info['unidad']})")
    titulo = (f"FRED {info['id']} – {info['titulo']} | {unidad} | {info['frecuencia']} | {info['ajuste']} | "
              f"actualizada {info['actualizada'][:10]}")
    return _formatear(datos, titulo=titulo, sufijo="" if modo == "valor" else "%") + aviso


CONSULTAR_FRED = {
    "name": "consultar_fred",
    "description": (
        "Serie económica de EE. UU. desde FRED (Reserva Federal de St. Louis), con su último dato y fecha. "
        "Con el parámetro modo, devuelve las variaciones ya calculadas (en %): no hace falta calcularlas. Series más usadas: "
        + "; ".join(f"{k}: {v}" for k, v in SERIES_EEUU.items())
        + ". Para otras, usá buscar_serie_fred."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "serie": {"type": "string", "description": "Id de la serie en FRED, ej.: CPIAUCSL"},
            "modo": {"type": "string", "enum": list(calc.MODOS),
                     "description": "valor (nivel), variacion (% contra el período anterior), variacion_interanual "
                                    "(% contra un año antes), variacion_anualizada (% anualizado, como se informa el PBI) "
                                    "o variacion_acumulada_anio"},
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD (por defecto, dos años atrás)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (opcional)"},
        },
        "required": ["serie"],
    },
}


def buscar_serie_fred(texto: str) -> str:
    try:
        series = fred.buscar_series(texto)
    except ErrorAPI as e:
        return f"Error: {e}"
    if not series:
        return f"No se encontraron series en FRED para '{texto}'. Probá con otras palabras, en inglés."
    return "FRED (usar consultar_fred con el id), las más consultadas primero:\n" + "\n".join(
        f"  id={s['id']} | {s['titulo']} | {s['unidad']} | {s['frecuencia']} {s['ajuste']} | datos hasta {s['hasta']}"
        for s in series)


BUSCAR_SERIE_FRED = {
    "name": "buscar_serie_fred",
    "description": "Busca series de EE. UU. (y de otros países) en FRED por palabras en inglés, ej.: 'housing starts', "
                   "'consumer credit'. Para las series más usadas no hace falta: ya están en consultar_fred.",
    "parameters": {
        "type": "object",
        "properties": {"texto": {"type": "string", "description": "Palabras clave en inglés"}},
        "required": ["texto"],
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
    (INFLACION_ANUALIZADA, inflacion_anualizada),
    (CONSULTAR_FRED, consultar_fred),
    (BUSCAR_SERIE_FRED, buscar_serie_fred),
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