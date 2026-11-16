"""Lector de fichas para el agente de renta fija: leer documentos, ver borradores, aprobarlos o descartarlos.

Aprobar solo cuando el usuario lo pide de forma explícita y nombra el bono (o pide "todos"). La validación es la
misma que la del comando: si al borrador le falta un dato o el bono ya venció, no se aprueba.
"""
from carga_datos import fichas_documentos
from renta_fija import leer_fichas


def leer_documento_bonos(fuente: str, solo: str | None = None) -> str:
    try:
        return fichas_documentos.describir(fichas_documentos.leer(fuente, solo=solo or None))
    except Exception as e:
        return f"Error al leer el documento: {e}"


def ver_borradores() -> str:
    try:
        avisos = fichas_documentos.actualizar_borradores()
        return ("\n".join(avisos) + "\n\n" if avisos else "") + fichas_documentos.describir_borradores()
    except Exception as e:
        return f"Error al leer los borradores: {e}"


def aprobar_ficha(ticker: str, nuevo: bool = False) -> str:
    try:
        return fichas_documentos.aprobar(ticker, por="Agustin (vía agente de renta fija)", nuevo=bool(nuevo))
    except (ValueError, leer_fichas.ErrorFicha) as e:
        return f"No se aprobó {ticker}: {e}"


def completar_borrador(ticker: str, campo: str, valor: str) -> str:
    try:
        return fichas_documentos.completar(ticker, campo, valor)
    except ValueError as e:
        return f"No se completó: {e}"


def aplicar_cambio(ticker: str, campo: str | None = None) -> str:
    try:
        return fichas_documentos.aplicar(ticker, campo or None, por="Agustin (vía agente de renta fija)")
    except (ValueError, leer_fichas.ErrorFicha) as e:
        return f"No se aplicó: {e}"


def rechazar_cambio(ticker: str, campo: str | None = None) -> str:
    try:
        return fichas_documentos.rechazar(ticker, campo or None)
    except ValueError as e:
        return f"No se rechazó: {e}"


def vincular_borrador(ticker: str, ticker_cargado: str) -> str:
    try:
        return fichas_documentos.vincular(ticker, ticker_cargado)
    except ValueError as e:
        return f"No se vinculó: {e}"


def buscar_emision_original(ticker: str) -> str:
    try:
        return fichas_documentos.buscar_emision_original(ticker)
    except ValueError as e:
        return f"No se buscó: {e}"


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
        "solo": {"type": "string", "description": ("Opcional: ticker o clave de un borrador. Del documento se toman solo "
                                                   "los datos de ese bono (para completarlo desde un aviso viejo)")},
    }, "required": ["fuente"]},
}
VER_BORRADORES = {
    "name": "ver_borradores",
    "description": ("Muestra los borradores de fichas pendientes de aprobación (con todos sus campos, lo pendiente y la "
                    "cita) y los cambios propuestos a fichas ya aprobadas."),
    "parameters": {"type": "object", "properties": {}},
}
APROBAR_FICHA = {
    "name": "aprobar_ficha",
    "description": (
        "Aprueba un borrador: lo valida y lo pasa a las fichas definitivas, donde lo usan las calculadoras. Usala SOLO si "
        "el usuario te pidió explícitamente aprobar ese bono (o todos) en este pedido; nunca por iniciativa propia."
    ),
    "parameters": {"type": "object", "properties": {
        "ticker": {"type": "string", "description": "Ticker del borrador"},
        "nuevo": {"type": "boolean", "description": (
            "true solo si el borrador parece un bono ya cargado (posible duplicado) y el usuario confirmó que es OTRO bono")},
    }, "required": ["ticker"]},
}
VINCULAR_BORRADOR = {
    "name": "vincular_borrador",
    "description": ("El borrador es un bono que ya tiene ficha (posible duplicado confirmado por el usuario): lo descarta y, "
                    "si algún dato difiere, lo deja como cambio propuesto. Usala SOLO si el usuario te lo pidió."),
    "parameters": {"type": "object", "properties": {
        "ticker": {"type": "string", "description": "Clave o ticker del borrador"},
        "ticker_cargado": {"type": "string", "description": "Ticker del bono ya cargado al que corresponde"},
    }, "required": ["ticker", "ticker_cargado"]},
}
BUSCAR_EMISION_ORIGINAL = {
    "name": "buscar_emision_original",
    "description": ("Para un borrador sin fecha de emisión (típicamente una reapertura de un bono que no teníamos): busca "
                    "en argentina.gob.ar o el Boletín Oficial el documento de la primera emisión y completa de ahí solo "
                    "los datos de ese bono (emisión, pagos, tramos, base). No aprueba nada."),
    "parameters": _TICKER,
}
DESCARTAR_BORRADOR = {
    "name": "descartar_borrador",
    "description": "Borra un borrador sin aprobarlo. Usala SOLO si el usuario te lo pidió explícitamente.",
    "parameters": _TICKER,
}

_TICKER_CAMPO = {"type": "object", "properties": {
    "ticker": {"type": "string", "description": "Ticker de la ficha aprobada"},
    "campo": {"type": "string", "description": "Opcional: solo ese campo (cupon, margen, emision...). Vacío = todos los de ese ticker"},
}, "required": ["ticker"]}
COMPLETAR_BORRADOR = {
    "name": "completar_borrador",
    "description": ("Completa o corrige un dato de un BORRADOR (no de una ficha aprobada), por ejemplo el ticker de un "
                    "instrumento nuevo que no venía en el resultado. Usala SOLO con un dato que te dio el usuario."),
    "parameters": {"type": "object", "properties": {
        "ticker": {"type": "string", "description": "Ticker o clave del borrador (ej.: tamar_capitalizable-2027-04-30)"},
        "campo": {"type": "string", "description": "ticker, emision, vencimiento, cupon, margen, frecuencia, base, ley, tipo..."},
        "valor": {"type": "string", "description": "Fechas AAAA-MM-DD; tasas en fracción (0.025 = 2,5%)"},
    }, "required": ["ticker", "campo", "valor"]},
}
APLICAR_CAMBIO = {
    "name": "aplicar_cambio",
    "description": ("Aplica a una ficha YA APROBADA un cambio propuesto por el lector (un dato de un documento que no "
                    "coincide con la ficha) y la valida. Usala SOLO si el usuario te pidió explícitamente aplicar ese cambio."),
    "parameters": _TICKER_CAMPO,
}
RECHAZAR_CAMBIO = {
    "name": "rechazar_cambio",
    "description": "Descarta un cambio propuesto sin tocar la ficha. Usala SOLO si el usuario te lo pidió.",
    "parameters": _TICKER_CAMPO,
}

HERRAMIENTAS = [(LEER_DOCUMENTO_BONOS, leer_documento_bonos), (VER_BORRADORES, ver_borradores),
                (APROBAR_FICHA, aprobar_ficha), (DESCARTAR_BORRADOR, descartar_borrador),
                (COMPLETAR_BORRADOR, completar_borrador), (VINCULAR_BORRADOR, vincular_borrador),
                (BUSCAR_EMISION_ORIGINAL, buscar_emision_original), (APLICAR_CAMBIO, aplicar_cambio), (RECHAZAR_CAMBIO, rechazar_cambio)]
