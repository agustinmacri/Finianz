"""Precios de emisión de los bonos nuevos, del resultado de cada licitación del Tesoro (datos/licitaciones.json).

Entre el resultado y la liquidación un bono nuevo todavía no cotiza: las curvas y la calculadora lo toman a su precio
de corte, con la liquidación en la fecha de emisión (decisión de Agustin, 27/11/2026). Precio por 100 VN: el de corte
del resultado (que viene por 1.000 VNO) o, si se licitó por tasa o margen, a la par.
"""
import json
from datetime import date

import config

REGISTRO = None     # las pruebas lo cambian por un archivo temporal


def _ruta():
    return REGISTRO or config.DATOS_DIR / "licitaciones.json"


def _cargar() -> dict:
    try:
        return json.loads(_ruta().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def guardar(ticker: str, emision: date, precio: float | None, a_la_par: bool, origen: str, resultado: str | None = None):
    """precio: por 100 VN (None si se licitó por tasa o margen: a la par). a_la_par: 100 por 100 VN; en un dual con VN
    en dólares, por el tipo de cambio inicial."""
    registro = _cargar()
    registro[ticker.upper()] = {"emision": emision.isoformat(), "precio": precio, "a_la_par": a_la_par,
                                "origen": origen, "resultado": resultado}
    _ruta().parent.mkdir(parents=True, exist_ok=True)
    _ruta().write_text(json.dumps(registro, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


def de(ticker: str) -> dict | None:
    dato = _cargar().get(ticker.upper())
    if dato:
        dato = dict(dato, emision=date.fromisoformat(dato["emision"]))
    return dato
