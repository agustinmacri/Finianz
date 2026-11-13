"""Lectura y validación de las fichas técnicas de bonos (carpeta renta_fija/fichas/).

Cada archivo .toml de renta_fija/fichas/ tiene una lista [[bono]]. El formato de cada familia está
explicado al principio de su archivo (por ejemplo, renta_fija/fichas/cer.toml).
Las fichas tienen solo condiciones de emisión: ningún valor de mercado ni de índices (el CER
inicial, por ejemplo, se toma de la base de series a partir de la fecha de emisión).
"""
import tomllib
from datetime import date

import config

CARPETA = config.BASE_DIR / "renta_fija" / "fichas"
CAMPOS = {
    "cer_cero_cupon": ("ticker", "tipo", "familia", "emision", "vencimiento"),
    "cer_cupon": ("ticker", "tipo", "familia", "emision", "vencimiento", "cupon", "frecuencia", "pagos"),
    "tasa_fija_capitalizable": ("ticker", "tipo", "familia", "emision", "vencimiento", "tem"),
    "tasa_fija_cupon": ("ticker", "tipo", "familia", "emision", "vencimiento", "cupon", "frecuencia", "pagos"),
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
            for campo in ("emision", "vencimiento"):
                if campo in bono and not isinstance(bono[campo], date):
                    raise ErrorFicha(f"{donde}: '{campo}' tiene que ser una fecha AAAA-MM-DD sin comillas.")
            if "cer_inicial" in bono:
                raise ErrorFicha(f"{donde}: 'cer_inicial' no va en la ficha. El CER inicial se toma de la base "
                                 "de series (10.º día hábil anterior a la emisión): borrá esa línea.")
            if familia in ("cer_cupon", "tasa_fija_cupon"):
                _validar_pagos(bono, donde)
            ticker = bono["ticker"].upper()
            if ticker in fichas:
                raise ErrorFicha(f"{donde}: el ticker {ticker} está repetido.")
            fichas[ticker] = bono
    return fichas


def _validar_pagos(bono: dict, donde: str):
    """El cronograma tiene fechas válidas, en orden, que terminan en el vencimiento, y amortiza el 100%."""
    pagos = bono["pagos"]
    if not all(isinstance(p.get("fecha"), date) for p in pagos):
        raise ErrorFicha(f"{donde}: cada pago necesita 'fecha' AAAA-MM-DD sin comillas.")
    fechas = [p["fecha"] for p in pagos]
    if fechas != sorted(fechas) or len(set(fechas)) != len(fechas):
        raise ErrorFicha(f"{donde}: las fechas de 'pagos' tienen que estar en orden y sin repetirse.")
    if fechas[-1] != bono["vencimiento"]:
        raise ErrorFicha(f"{donde}: el último pago ({fechas[-1]}) no coincide con el vencimiento ({bono['vencimiento']}).")
    total = sum(p.get("amortizacion", 0) for p in pagos)
    if abs(total - 100) > 1e-9:
        raise ErrorFicha(f"{donde}: las amortizaciones suman {total}, tienen que sumar 100.")
    if bono.get("base", "30/360") != "30/360":
        raise ErrorFicha(f"{donde}: base '{bono['base']}' todavía no implementada (hoy: 30/360).")


def ficha(ticker: str) -> dict | None:
    return leer_todas().get(ticker.upper())
