"""leer_documento_bonos: arma borradores de fichas técnicas desde un documento oficial (URL o archivo).

El agente solo crea o completa borradores: la aprobación la hace Agustin desde la terminal, después de revisarlos.
"""
from carga_datos import fichas_documentos


def leer_documento_bonos(fuente: str) -> str:
    try:
        return fichas_documentos.describir(fichas_documentos.leer(fuente))
    except Exception as e:
        return f"Error al leer el documento: {e}"


LEER_DOCUMENTO_BONOS = {
    "name": "leer_documento_bonos",
    "description": (
        "Lee un documento oficial (llamado a licitación del Tesoro, su resultado, una resolución o un prospecto), por URL "
        "o ruta de archivo, y arma BORRADORES de fichas técnicas de los bonos nuevos (los que ya tienen ficha se informan y "
        "no se tocan). Si ya había un borrador del mismo bono, completa lo que faltaba. No aprueba nada: los borradores "
        "los revisa y aprueba el usuario desde la terminal."
    ),
    "parameters": {"type": "object", "properties": {
        "fuente": {"type": "string", "description": "URL del documento o ruta del archivo (PDF, HTML o TXT)"},
    }, "required": ["fuente"]},
}

HERRAMIENTAS = [(LEER_DOCUMENTO_BONOS, leer_documento_bonos)]
