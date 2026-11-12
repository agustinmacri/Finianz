"""Herramientas de precios de mercado (bonos, letras, ONs, acciones, CEDEARs) desde PPI.

Solo lectura: consultan precios y la calculadora de bonos de PPI; no hay nada que opere.
Las respuestas son cortas y siempre con la fecha del precio.
"""
import json

import config
from conexiones import ppi
from conexiones.http import ErrorAPI

PUNTOS_HISTORICO = 15   # cuántos precios diarios se muestran del histórico


def _tipo(ticker: str) -> str:
    """Tipo de instrumento según PPI (BONOS, ACCIONES, CEDEARS...). Prefiere el que cotiza en BYMA."""
    encontrados = ppi.buscar_instrumento(ticker)
    exactos = [i for i in encontrados if str(i.get("ticker", "")).upper() == ticker.upper()] or encontrados
    if not exactos:
        raise ValueError(f"PPI no encontró el ticker '{ticker}'.")
    en_byma = [i for i in exactos if str(i.get("market", "")).upper() == "BYMA"]
    return (en_byma or exactos)[0]["type"]


def _n(valor) -> str:
    """Números con separador de miles; hasta 4 decimales para los chicos (TIR, duration)."""
    if not isinstance(valor, (int, float)):
        return str(valor)
    return f"{valor:,.2f}" if abs(valor) >= 1000 else f"{valor:,.4f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# 1. Precio actual o histórico
# ---------------------------------------------------------------------------
def consultar_precio(ticker: str, desde: str | None = None, hasta: str | None = None,
                     plazo: str | None = None) -> str:
    try:
        tipo = _tipo(ticker)
        plazo = plazo or config.PPI_PLAZO
        if not desde:
            p = ppi.precio_actual(ticker, tipo, plazo)
            return (f"{ticker.upper()} ({tipo}, {plazo}) – PPI. Fecha del precio: {p.get('date')}\n"
                    f"Último: {_n(p.get('price'))} | apertura {_n(p.get('openingPrice'))} | "
                    f"máx {_n(p.get('max'))} | mín {_n(p.get('min'))} | volumen {_n(p.get('volume'))}")
        datos = sorted(ppi.historico(ticker, tipo, desde, hasta, plazo), key=lambda d: d.get("date", ""))
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"

    if not datos:
        return f"{ticker.upper()}: PPI no tiene precios entre {desde} y {hasta or 'hoy'}."
    precios = [d["price"] for d in datos if isinstance(d.get("price"), (int, float))]
    lineas = [f"{d.get('date', '')[:10]}: {_n(d.get('price'))} (vol. {_n(d.get('volume'))})"
              for d in datos[-PUNTOS_HISTORICO:]]
    return (f"{ticker.upper()} ({tipo}, {plazo}) – PPI: {len(datos)} precios entre {datos[0].get('date', '')[:10]} "
            f"y {datos[-1].get('date', '')[:10]}.\n"
            f"ÚLTIMO: {datos[-1].get('date', '')[:10]} = {_n(datos[-1].get('price'))} | "
            f"mín {_n(min(precios))} | máx {_n(max(precios))}\n"
            + (f"Últimos {PUNTOS_HISTORICO}:\n" if len(datos) > PUNTOS_HISTORICO else "") + "\n".join(lineas))


CONSULTAR_PRECIO = {
    "name": "consultar_precio",
    "description": (
        "Precio de mercado de un instrumento argentino (bonos, letras, ONs, acciones, CEDEARs) desde PPI, con su fecha. "
        "Sin 'desde', devuelve el último precio; con 'desde', los precios diarios del período. "
        "Los bonos cotizan por cada 100 de valor nominal y en la moneda del ticker (ej.: AL30 en pesos, AL30D en dólares MEP)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Ticker, ej.: AL30, GD30D, TX26, S30E7, GGAL"},
            "desde": {"type": "string", "description": "Fecha inicial AAAA-MM-DD para el histórico (opcional)"},
            "hasta": {"type": "string", "description": "Fecha final AAAA-MM-DD (opcional, por defecto hoy)"},
            "plazo": {"type": "string", "enum": list(ppi.PLAZOS), "description": "Plazo de liquidación (por defecto A-24HS)"},
        },
        "required": ["ticker"],
    },
}


# ---------------------------------------------------------------------------
# 2. Calculadora de bonos de PPI
# ---------------------------------------------------------------------------
_CAMPOS_BONO = {"tir": "TIR", "md": "duration modificada", "parity": "paridad", "technicalValue": "valor técnico",
                "interestAccrued": "interés corrido", "currentCoupon": "cupón vigente", "total": "total"}


def calcular_bono(ticker: str, precio: float | None = None) -> str:
    try:
        if precio is None:
            precio = ppi.precio_actual(ticker, _tipo(ticker)).get("price")
        resultado = ppi.estimar_bono(ticker, precio)
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    datos = resultado[0] if isinstance(resultado, list) and resultado else resultado
    if not isinstance(datos, dict):
        return f"Respuesta inesperada de PPI: {json.dumps(resultado, ensure_ascii=False)[:500]}"
    lineas = [f"{ticker.upper()} a precio {_n(precio)} (por 100 VN) – calculadora de PPI:"]
    lineas += [f"  {nombre}: {_n(datos[c])}" for c, nombre in _CAMPOS_BONO.items() if c in datos]
    flujos = datos.get("flows") or []
    if flujos:
        lineas.append(f"  Próximos flujos ({min(4, len(flujos))} de {len(flujos)}):")
        lineas += [f"    {json.dumps(f, ensure_ascii=False)}" for f in flujos[:4]]
    return "\n".join(lineas)


CALCULAR_BONO = {
    "name": "calcular_bono",
    "description": (
        "Calculadora de bonos de PPI: TIR, duration modificada, paridad, valor técnico, interés corrido y próximos flujos "
        "de un bono o letra. Sin precio, usa el último precio de mercado."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Ticker del bono o letra, ej.: AL30, TX26"},
            "precio": {"type": "number", "description": "Precio por cada 100 de valor nominal (opcional)"},
        },
        "required": ["ticker"],
    },
}


HERRAMIENTAS = [
    (CONSULTAR_PRECIO, consultar_precio),
    (CALCULAR_BONO, calcular_bono),
]
