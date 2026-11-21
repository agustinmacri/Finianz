"""Curvas de mercado de renta fija: TEA, TNA y duration de cada bono a su precio de mercado, por curva (tasa fija,
CER, TAMAR, dollar linked y Bonares). Las usan los breakevens (tools/breakevens.py), la curva de tasa fija y el
panel web.
"""
from datetime import date

from conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas, mercado, metricas


def armar(operacion: date, liquidacion: date, fecha_precios: date | None,
            familias: set[str] | None = None) -> tuple[dict, dict, list[str]]:
    """TEA y duration (en días) de cada bono a precio de mercado, por curva (solo 'familias', si se indica)."""
    curvas = {"tasa_fija": [], "cer": [], "dl": [], "tamar": [], "hd": []}
    contexto, errores = {}, []
    for f in fichas.todas():
        familia, ticker = f["familia"], f["ticker"].upper()
        if familias is not None and familia not in familias:
            continue
        if liquidacion >= f["vencimiento"] or "DUAL" in f.get("tipo", "").upper():
            continue                                         # vencidos, y duales (tienen opcionalidad)
        if familia == "hard_dollar" and f["ley"] != "AR":
            continue                                         # la brecha se mide con Bonares
        if familia not in metricas.FAMILIAS_CURVA:
            continue
        try:
            precio, _ = mercado.precio(ticker + ("D" if familia == "hard_dollar" else ""), fecha_precios)
            m = metricas.calculadora(f, liquidacion, operacion, contexto)(precio)
            punto = {"ticker": ticker, "vencimiento": f["vencimiento"], "precio": precio, **m["extra"]}
            curvas[m["curva"]].append(dict(punto, tea=m["tea"], tna=m["tna"], x=m["duration"] * 365))
        except (ErrorAPI, ValueError) as e:
            errores.append(f"{ticker}: {e}")
    return curvas, contexto, errores
