"""Lector de fichas para el agente de renta fija: leer documentos, ver borradores, aprobarlos o descartarlos.

Aprobar solo cuando el usuario lo pide de forma explícita y nombra el bono (o pide "todos"). La validación es la
misma que la del comando: si al borrador le falta un dato o el bono ya venció, no se aprueba.
"""
from carga_datos import fichas_documentos
from renta_fija import leer_fichas


def leer_documento_bonos(fuente: str) -> str:
    try:
        return fichas_documentos.describir(fichas_documentos.leer(fuente))
    except Exception as e:
        return f"Error al leer el documento: {e}"


def ver_borradores() -> str:
    try:
        return fichas_documentos.describir_borradores()
    except Exception as e:
        return f"Error al leer los borradores: {e}"


def aprobar_ficha(ticker: str) -> str:
    try:
        return fichas_documentos.aprobar(ticker, por="Agustin (vía agente de renta fija)")
    except (ValueError, leer_fichas.ErrorFicha) as e:
        return f"No se aprobó {ticker}: {e}"


def descartar_borrador(ticker: str) -> str:
    try:
        return fichas_documentos.descartar(ticker)
    except ValueError as e:
        return f"No se descartó: {e}"


_TICKER = {"type": "object", "properties": {
    "ticker": {"type": "string", "description": "Ticker del borrador (o su clave, si todavía no tiene ticker)"},
}, "required": ["ticker"]}

LEER_DOCUMENTO_BONOS = {
    "name": "leer_documento_bonos",
    "description": (
        "Lee un documento oficial (llamado a licitación del Tesoro, su resultado, una resolución o un prospecto), por URL "
        "o ruta de archivo, y arma BORRADORES de fichas técnicas de los bonos nuevos. Los que ya tienen ficha y los ya "
        "vencidos se informan y no se cargan. Si ya había un borrador del mismo bono, completa lo que faltaba."
    ),
    "parameters": {"type": "object", "properties": {
        "fuente": {"type": "string", "description": "URL del documento o ruta del archivo (PDF, HTML o TXT)"},
    }, "required": ["fuente"]},
}
VER_BORRADORES = {
    "name": "ver_borradores",
    "description": "Muestra los borradores de fichas pendientes de aprobación, con todos sus campos, lo pendiente y la cita.",
    "parameters": {"type": "object", "properties": {}},
}
APROBAR_FICHA = {
    "name": "aprobar_ficha",
    "description": (
        "Aprueba un borrador: lo valida y lo pasa a las fichas definitivas, donde lo usan las calculadoras. Usala SOLO si "
        "el usuario te pidió explícitamente aprobar ese bono (o todos) en este pedido; nunca por iniciativa propia."
    ),
    "parameters": _TICKER,
}
DESCARTAR_BORRADOR = {
    "name": "descartar_borrador",
    "description": "Borra un borrador sin aprobarlo. Usala SOLO si el usuario te lo pidió explícitamente.",
    "parameters": _TICKER,
}

HERRAMIENTAS = [(LEER_DOCUMENTO_BONOS, leer_documento_bonos), (VER_BORRADORES, ver_borradores),
                (APROBAR_FICHA, aprobar_ficha), (DESCARTAR_BORRADOR, descartar_borrador)]
