"""Herramientas de precios de mercado (bonos, letras, ONs, acciones, CEDEARs) desde PPI.

Solo traen precios (actuales e históricos): no operan y no usan cálculos de PPI.
Los cálculos (TIR, duration, etc.) los hace el proyecto: ver docs/arquitectura-multiagente.md.
Las respuestas son cortas y siempre con la fecha del precio.

El histórico sale de la base propia (datos/precios.db): cada activo consultado queda guardado
y a la API solo se le piden los días que faltan. El precio del momento se consulta en vivo.
"""
import config
from admin_datos import precios as db
from carga_datos import precios as carga
from conexiones import ppi
from conexiones.http import ErrorAPI

PUNTOS_HISTORICO = 15   # cuántos precios diarios se muestran del histórico


def _n(valor) -> str:
    """Números con separador de miles; hasta 4 decimales para los chicos."""
    if valor is None:
        return "s/d"
    if not isinstance(valor, (int, float)):
        return str(valor)
    return f"{valor:,.2f}" if abs(valor) >= 1000 else f"{valor:,.4f}".rstrip("0").rstrip(".")


# ---------------------------------------------------------------------------
# 1. Precio actual o histórico
# ---------------------------------------------------------------------------
def consultar_precio(ticker: str, desde: str | None = None, hasta: str | None = None,
                     plazo: str | None = None) -> str:
    plazo = plazo or config.PPI_PLAZO
    # 1. Guardar en la base lo que falte (todo el histórico si el activo es nuevo)
    aviso = ""
    try:
        carga.actualizar(ticker, plazo)
        instrumento = db.instrumento(ticker)
    except (ErrorAPI, ValueError) as e:
        instrumento = db.instrumento(ticker)
        if not instrumento:
            return f"Error: {e}"
        aviso = f"\n(No se pudo actualizar desde PPI: {e}. Se usan los precios guardados.)"
    titulo = (f"{ticker.upper()} – {instrumento.get('descripcion') or ''} ({instrumento['tipo']}, "
              f"en {instrumento.get('moneda') or 's/d'}, {plazo})")

    # 2. Precio del momento: en vivo, no se guarda
    if not desde:
        try:
            p = ppi.precio_actual(ticker, instrumento["tipo"], plazo)
        except ErrorAPI as e:
            ultimo = db.entre(ticker, plazo)[-1:] or [None]
            if not ultimo[0]:
                return f"Error: {e}"
            return (f"{titulo} – sin conexión con PPI ({e}). Último cierre guardado: "
                    f"{ultimo[0]['fecha']} = {_n(ultimo[0]['cierre'])}")
        return (f"{titulo} – PPI en vivo. Fecha y hora del precio: {str(p.get('date'))[:16]}\n"
                f"Último: {_n(p.get('price'))} | variación del día {p.get('marketChangePercent') or 's/d'} "
                f"(cierre anterior {_n(p.get('previousClose'))}) | apertura {_n(p.get('openingPrice'))} | "
                f"máx {_n(p.get('max'))} | mín {_n(p.get('min'))} | volumen {_n(p.get('volume'))}{aviso}")

    # 3. Histórico: desde la base propia
    datos = db.entre(ticker, plazo, desde, hasta)
    if not datos:
        guardado = db.rango(ticker, plazo)
        return (f"{ticker.upper()}: no hay precios guardados entre {desde} y {hasta or 'hoy'}"
                + (f" (la base tiene del {guardado[0]} al {guardado[1]})." if guardado else ".") + aviso)
    cierres = [d["cierre"] for d in datos]
    lineas = [f"{d['fecha']}: {_n(d['cierre'])} (vol. {_n(d['volumen'])})" for d in datos[-PUNTOS_HISTORICO:]]
    return (f"{titulo} – base propia (fuente: PPI): {len(datos)} cierres entre {datos[0]['fecha']} "
            f"y {datos[-1]['fecha']}.\n"
            f"ÚLTIMO: {datos[-1]['fecha']} = {_n(datos[-1]['cierre'])} | mín {_n(min(cierres))} | máx {_n(max(cierres))}\n"
            + (f"Últimos {PUNTOS_HISTORICO}:\n" if len(datos) > PUNTOS_HISTORICO else "") + "\n".join(lineas) + aviso)

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

HERRAMIENTAS = [
    (CONSULTAR_PRECIO, consultar_precio),
]


