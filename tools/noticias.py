"""Herramientas de noticias para el agente: lo que el modelo ve y puede usar.

Devuelven titulares en texto compacto: fecha, medio, título y un resumen corto.
Sin links, para gastar pocos tokens (el medio y la fecha alcanzan para citar).
"""
from datetime import timezone, timedelta

from clients import noticias
from clients.http import ErrorAPI

HORA_ARGENTINA = timezone(timedelta(hours=-3))


# ---------------------------------------------------------------------------
# 1. Buscar noticias sobre un tema
# ---------------------------------------------------------------------------
def buscar_noticias(tema: str, dias: int = 7) -> str:
    try:
        resultados = noticias.buscar(tema, dias=int(dias))
    except ErrorAPI as e:
        return f"Error: {e}"
    if not resultados:
        return f"No se encontraron noticias sobre '{tema}' en los últimos {dias} días. Probá con otras palabras o más días."
    return f"Noticias sobre '{tema}' (últimos {dias} días, más nuevas primero):\n" + _formatear(resultados)


BUSCAR_NOTICIAS = {
    "name": "buscar_noticias",
    "description": (
        "Busca noticias de medios argentinos sobre un tema en los últimos días (Google News). "
        "Usala para eventos puntuales: licitaciones del Tesoro, medidas del BCRA, resoluciones de la CNV, "
        "datos del INDEC, declaraciones oficiales, empresas. "
        "Acepta comillas para frases exactas y OR para alternativas."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tema": {"type": "string", "description": "Tema a buscar, ej: 'licitación Tesoro', 'BCRA tasas', '\"bonos CER\"'"},
            "dias": {"type": "integer", "description": "Cuántos días hacia atrás buscar (por defecto 7)"},
        },
        "required": ["tema"],
    },
}


# ---------------------------------------------------------------------------
# 2. Titulares del día
# ---------------------------------------------------------------------------
def titulares_recientes(horas: int = 24) -> str:
    try:
        resultados = noticias.titulares(horas=int(horas))
    except ErrorAPI as e:
        return f"Error: {e}"
    if not resultados:
        return f"No hay titulares en las últimas {horas} horas."
    return f"Titulares de economía y finanzas (últimas {horas} horas):\n" + _formatear(resultados)


TITULARES_RECIENTES = {
    "name": "titulares_recientes",
    "description": (
        "Devuelve los titulares más recientes de economía y finanzas de los medios configurados. "
        "Usala para responder '¿qué pasó hoy?' o para armar un resumen del día, sin un tema específico."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "horas": {"type": "integer", "description": "Ventana en horas (por defecto 24)"},
        },
    },
}


# ---------------------------------------------------------------------------
# Registro
# ---------------------------------------------------------------------------
HERRAMIENTAS = [
    (BUSCAR_NOTICIAS, buscar_noticias),
    (TITULARES_RECIENTES, titulares_recientes),
]


def _formatear(resultados: list[dict]) -> str:
    lineas = []
    for n in resultados:
        fecha = n["fecha"].astimezone(HORA_ARGENTINA).strftime("%d/%m %H:%M") if n["fecha"] else "s/f"
        lineas.append(f"- {fecha} | {n['medio']} | {n['titulo']}")
        if n["resumen"]:
            lineas.append(f"  {n['resumen']}")
    return "\n".join(lineas)