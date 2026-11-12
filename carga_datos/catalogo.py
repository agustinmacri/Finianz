"""Lectura y validación del catálogo de publicaciones (calendarios/publicaciones.toml)."""
import tomllib

import config
from admin_datos.feriados import MERCADOS

ARCHIVO = config.CALENDARIOS_DIR / "publicaciones.toml"
CAMPOS = ("codigo", "nombre", "pais", "organismo", "importancia", "fuente")
VALORES = {
    "pais": ("AR", "US"),
    "importancia": ("alta", "media", "baja"),
    "fuente": ("indec_pdf", "fred", "manual", "regla"),
}


class ErrorCatalogo(Exception):
    """Error en calendarios/publicaciones.toml, con un mensaje que indica qué corregir."""


def leer() -> list[dict]:
    try:
        datos = tomllib.loads(ARCHIVO.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErrorCatalogo(f"No existe {ARCHIVO.name} en la carpeta calendarios/.") from None
    except tomllib.TOMLDecodeError as e:
        raise ErrorCatalogo(f"{ARCHIVO.name} tiene un error de formato: {e}") from None

    publicaciones, codigos = [], set()
    for i, p in enumerate(datos.get("publicacion", []), start=1):
        donde = f"{ARCHIVO.name}, publicación n.º {i} ({p.get('codigo', 'sin código')})"
        for campo in CAMPOS:
            if not p.get(campo):
                raise ErrorCatalogo(f"{donde}: falta el campo '{campo}'.")
        for campo, opciones in VALORES.items():
            if p[campo] not in opciones:
                raise ErrorCatalogo(f"{donde}: {campo} '{p[campo]}' inválido. Opciones: {', '.join(opciones)}.")
        if p["fuente"] == "indec_pdf" and not p.get("patron"):
            raise ErrorCatalogo(f"{donde}: las publicaciones del INDEC necesitan 'patron'.")
        if p["fuente"] == "fred" and not p.get("fred_release"):
            raise ErrorCatalogo(f"{donde}: las publicaciones de FRED necesitan 'fred_release'.")
        if p["fuente"] == "regla":
            if not isinstance(p.get("dia_habil"), int) or not 1 <= p["dia_habil"] <= 15:
                raise ErrorCatalogo(f"{donde}: las reglas necesitan 'dia_habil' (número entre 1 y 15).")
            if p.get("calendario") not in MERCADOS:
                raise ErrorCatalogo(f"{donde}: 'calendario' inválido. Opciones: {', '.join(MERCADOS)}.")
            if p.get("periodo") not in (None, "mes_anterior"):
                raise ErrorCatalogo(f"{donde}: 'periodo' solo puede ser \"mes_anterior\".")
        if p["codigo"] in codigos:
            raise ErrorCatalogo(f"{donde}: el código '{p['codigo']}' está repetido.")
        codigos.add(p["codigo"])
        publicaciones.append(p)
    return publicaciones
