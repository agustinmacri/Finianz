"""Lectura y validación de las fichas técnicas de bonos (carpeta renta_fija/fichas/).

Cada archivo .toml de renta_fija/fichas/ tiene una lista [[bono]]. El formato de cada familia está
explicado al principio de su archivo (por ejemplo, renta_fija/fichas/cer.toml).
Un mismo ticker puede tener varias fichas de familias distintas (los duales: los TXM se calculan
como CER y como TAMAR). Las fichas tienen solo condiciones de emisión: ningún valor de mercado ni de índices (el CER
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
    "tamar_capitalizable": ("ticker", "tipo", "familia", "emision", "vencimiento", "margen"),
    "dolar_linked_bullet": ("ticker", "tipo", "familia", "emision", "vencimiento"),
    "hard_dollar": ("ticker", "tipo", "familia", "ley", "emision", "vencimiento", "tramos", "pagos"),  # par opcional
}


class ErrorFicha(Exception):
    """Error en una ficha técnica, con un mensaje que indica qué corregir."""


def leer_todas() -> dict[str, list[dict]]:
    """Todas las fichas, por ticker (en mayúsculas). Cada ticker tiene una ficha, o varias si es dual."""
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
            if familia in ("cer_cupon", "tasa_fija_cupon", "hard_dollar"):
                _validar_pagos(bono, donde)
            if familia == "hard_dollar":
                _validar_tramos(bono, donde)
            ticker = bono["ticker"].upper()
            if any(otra["familia"] == familia for otra in fichas.get(ticker, [])):
                raise ErrorFicha(f"{donde}: el ticker {ticker} está repetido en la familia {familia}.")
            fichas.setdefault(ticker, []).append(bono)
    return fichas


def todas() -> list[dict]:
    """Todas las fichas en una lista (un dual aparece una vez por familia)."""
    return [f for lista in leer_todas().values() for f in lista]


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


def _validar_tramos(bono: dict, donde: str):
    """El step-up tiene fechas en orden, el primer tramo arranca en la emisión y las tasas son fracciones."""
    tramos = bono["tramos"]
    if not tramos or not all(isinstance(t.get("desde"), date) and isinstance(t.get("tasa"), (int, float)) for t in tramos):
        raise ErrorFicha(f"{donde}: cada tramo necesita 'desde' (fecha AAAA-MM-DD) y 'tasa' (ej.: 0.0075 = 0,75%).")
    desdes = [t["desde"] for t in tramos]
    if desdes != sorted(desdes) or desdes[0] != bono["emision"]:
        raise ErrorFicha(f"{donde}: los tramos tienen que estar en orden y el primero empezar en la emisión.")
    if any(not 0 <= t["tasa"] < 1 for t in tramos):
        raise ErrorFicha(f"{donde}: las tasas van en fracción (0.0175 = 1,75%).")


def fichas_de(ticker: str) -> list[dict]:
    """Las fichas de un ticker: una, o varias si es dual. Lista vacía si no tiene."""
    return leer_todas().get(ticker.upper(), [])


def ficha(ticker: str, familia: str | None = None) -> dict | None:
    """La ficha de un ticker (de una familia, si se indica; si no, la primera)."""
    candidatas = [f for f in fichas_de(ticker) if familia is None or f["familia"] == familia]
    return candidatas[0] if candidatas else None
