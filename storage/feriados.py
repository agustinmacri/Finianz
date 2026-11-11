"""Consultas de feriados y días hábiles sobre la base local.

Estas funciones las usan las herramientas de los agentes y, más adelante,
los cálculos de renta fija (liquidación T+2, días de devengamiento, pagos de cupón).
"""
from datetime import date, timedelta

from storage.db import conectar, leer_metadato

BASE = "feriados"

# Qué calendario define los días sin operación de cada mercado
MERCADOS = {
    "BYMA": "BYMA",            # mercado de capitales argentino
    "BANCOS": "AR_BANCOS",     # bancos argentinos (incluye el Día del Bancario)
    "AR": "AR",                # feriados nacionales
    "NYSE": "NYSE",            # bolsa de Nueva York
    "US_BONOS": "US_BONOS",    # mercado de Treasuries
    "US": "US",                # feriados federales de EE. UU.
}

NOMBRES_CALENDARIO = {
    "AR": "Argentina", "AR_BANCOS": "Bancos AR", "BYMA": "BYMA",
    "US": "EE. UU.", "NYSE": "NYSE", "US_BONOS": "Bonos EE. UU.",
}


class FueraDeRango(Exception):
    """La fecha pedida está fuera de los años cargados en la base."""


def rango_cargado() -> tuple[int, int] | None:
    desde, hasta = leer_metadato(BASE, "feriados_desde"), leer_metadato(BASE, "feriados_hasta")
    return (int(desde), int(hasta)) if desde and hasta else None


def feriados_entre(desde: date, hasta: date, calendarios: list[str] | None = None) -> list[dict]:
    """Feriados entre dos fechas (inclusive), ordenados por fecha. Sin calendarios: todos."""
    _verificar_rango(desde, hasta)
    consulta = "SELECT fecha, calendario, nombre, fuente FROM feriados WHERE fecha BETWEEN ? AND ?"
    parametros = [desde.isoformat(), hasta.isoformat()]
    if calendarios:
        consulta += f" AND calendario IN ({', '.join('?' * len(calendarios))})"
        parametros += calendarios
    with conectar(BASE) as con:
        return [dict(f) for f in con.execute(consulta + " ORDER BY fecha, calendario", parametros)]


def es_dia_habil(fecha: date, mercado: str = "BYMA") -> bool:
    """Hábil = de lunes a viernes y sin feriado en el calendario de ese mercado."""
    return fecha.weekday() < 5 and fecha not in _dias_cerrados(fecha, fecha, mercado)


def sumar_dias_habiles(fecha: date, dias: int, mercado: str = "BYMA") -> date:
    """Suma (o resta, si dias < 0) días hábiles. Ej.: liquidación T+2 = sumar_dias_habiles(t, 2)."""
    paso = 1 if dias >= 0 else -1
    # margen amplio para cubrir fines de semana y feriados largos
    ventana = (fecha, fecha + timedelta(days=abs(dias) * 3 + 15)) if paso > 0 else (fecha - timedelta(days=abs(dias) * 3 + 15), fecha)
    cerrados = _dias_cerrados(*ventana, mercado)
    actual, restantes = fecha, abs(dias)
    while restantes:
        actual += timedelta(days=paso)
        if actual.weekday() < 5 and actual not in cerrados:
            restantes -= 1
    return actual


def proximo_dia_habil(fecha: date, mercado: str = "BYMA") -> date:
    """La misma fecha si es hábil; si no, el siguiente día hábil."""
    return fecha if es_dia_habil(fecha, mercado) else sumar_dias_habiles(fecha, 1, mercado)


# --- auxiliares ---

def _dias_cerrados(desde: date, hasta: date, mercado: str) -> set[date]:
    if mercado not in MERCADOS:
        raise ValueError(f"Mercado '{mercado}' desconocido. Opciones: {', '.join(MERCADOS)}.")
    return {date.fromisoformat(f["fecha"]) for f in feriados_entre(desde, hasta, [MERCADOS[mercado]])}


def _verificar_rango(desde: date, hasta: date):
    rango = rango_cargado()
    if not rango:
        raise FueraDeRango("La base de feriados está vacía. Corré: python actualizar.py")
    if desde.year < rango[0] or hasta.year > rango[1]:
        raise FueraDeRango(f"Hay feriados cargados de {rango[0]} a {rango[1]}; la fecha pedida está fuera de ese rango.")
