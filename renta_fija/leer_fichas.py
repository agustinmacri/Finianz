"""Lectura y validación de las fichas técnicas de bonos (carpeta renta_fija/fichas/).

Cada archivo .toml de renta_fija/fichas/ tiene una lista [[bono]]. El formato de cada familia está
explicado al principio de su archivo (por ejemplo, renta_fija/fichas/cer.toml).
"""
import tomllib
from datetime import date

import config

CARPETA = config.BASE_DIR / "renta_fija" / "fichas"
CAMPOS = {
    "cer_cero_cupon": ("ticker", "tipo", "familia", "vencimiento", "cer_inicial"),
}


class ErrorFicha(Exception):
    """Error en una ficha técnica, con un mensaje que indica qué corregir."""


def leer_todas() -> dict[str, dict]:
    """Todas las fichas, por ticker (en mayúsculas)."""
    fichas = {}
    for archivo in sorted(CARPETA.glob("*.toml")):
        try:
            datos = tomllib.loads(archivo.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            raise ErrorFicha(f"{archivo.name} tiene un error de formato: {e}") from None
        for i, bono in enumerate(datos.get("bono", []), start=1):
            donde = f"{archivo.name}, bono n.º {i} ({bono.get('ticker', 'sin ticker')})"
            familia = bono.get("familia")
            if familia not in CAMPOS:
                raise ErrorFicha(f"{donde}: familia '{familia}' desconocida. Opciones: {', '.join(CAMPOS)}.")
            for campo in CAMPOS[familia]:
                if bono.get(campo) in (None, ""):
                    raise ErrorFicha(f"{donde}: falta el campo '{campo}'.")
            if not isinstance(bono["vencimiento"], date):
                raise ErrorFicha(f"{donde}: 'vencimiento' tiene que ser una fecha AAAA-MM-DD sin comillas.")
            ticker = bono["ticker"].upper()
            if ticker in fichas:
                raise ErrorFicha(f"{donde}: el ticker {ticker} está repetido.")
            fichas[ticker] = bono
    return fichas


def ficha(ticker: str) -> dict | None:
    return leer_todas().get(ticker.upper())
