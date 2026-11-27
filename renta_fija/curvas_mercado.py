"""Curvas de mercado de renta fija: TEA, TNA y duration de cada bono a su precio de mercado, por curva (tasa fija,
CER, TAMAR, dollar linked y hard dollar). Las usan los breakevens (tools/breakevens.py), la curva de tasa fija y el
panel web.

Por defecto, solo los bonos de cada curva sin opcionalidad: sin duales y, en hard dollar, los Bonares a precio MEP
(los breakevens miden la brecha con ellos). Con todas=True (el panel, decisiones de Agustin del 27/11/2026) se suman:
- los duales, cada pata en la curva de su familia, en una serie aparte por tipo de dual ("Duales CER/TAMAR"...);
- los Globales (ley NY), en una serie aparte de la de los Bonares;
- en hard dollar, el precio en dólares MEP (ticker D) o cable (ticker C), según 'dolar'.
Cada punto trae "serie": None en la curva principal, o el nombre de la serie aparte.
"""
from datetime import date

from fuentes_datos.conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas, metricas
from fuentes_datos import mercado

NOMBRE_FAMILIA = {"tasa_fija": "tasa fija", "cer": "CER", "tamar": "TAMAR", "dl": "dollar linked", "hd": "hard dollar"}
ORDEN = ("tasa_fija", "cer", "tamar", "dl", "hd")
SERIE_BONARES, SERIE_GLOBALES = "Bonares (ley AR)", "Globales (ley NY)"


def es_dual(f: dict) -> bool:
    return "DUAL" in f.get("tipo", "").upper()


def serie_dual(ticker: str) -> str:
    """Nombre de la serie de un dual, por las curvas de sus patas: "Duales CER/TAMAR", "Duales TAMAR/dollar linked"."""
    curvas = {metricas.FAMILIAS_CURVA.get(f["familia"]) for f in metricas.fichas_de(ticker)}
    return "Duales " + "/".join(NOMBRE_FAMILIA[c] for c in ORDEN if c in curvas)


def armar(operacion: date, liquidacion: date, fecha_precios: date | None,
          familias: set[str] | None = None, todas: bool = False, dolar: str = "mep") -> tuple[dict, dict, list[str]]:
    """TEA, TNA, duration (en días) y spread (TAMAR) de cada bono a precio de mercado, por curva (solo 'familias',
    si se indica). Un bono que todavía no se emitió va al precio de corte de su licitación (mercado.precio_bono)."""
    curvas = {"tasa_fija": [], "cer": [], "dl": [], "tamar": [], "hd": []}
    contexto, errores = {}, []
    sufijo_hd = "C" if dolar == "ccl" else "D"
    for f in fichas.todas():
        familia, ticker = f["familia"], f["ticker"].upper()
        if familias is not None and familia not in familias:
            continue
        if familia not in metricas.FAMILIAS_CURVA or liquidacion >= f["vencimiento"]:
            continue
        dual = es_dual(f)
        if dual and not todas:
            continue                                         # los duales tienen opcionalidad
        if familia == "hard_dollar" and f["ley"] != "AR" and not todas:
            continue                                         # la brecha se mide con Bonares
        try:
            precio, origen, liq = mercado.precio_bono(f, fecha_precios, liquidacion,
                                                      sufijo_hd if familia == "hard_dollar" else "")
            m = metricas.calculadora(f, liq, operacion, contexto)(precio)
            if dual:
                serie = serie_dual(ticker)
            elif familia == "hard_dollar" and todas:
                serie = SERIE_GLOBALES if f["ley"] != "AR" else SERIE_BONARES
            else:
                serie = None
            punto = {"ticker": ticker, "vencimiento": f["vencimiento"], "precio": precio, **m["extra"]}
            curvas[m["curva"]].append(dict(punto, tea=m["tea"], tna=m["tna"], x=m["duration"] * 365,
                                           spread=m.get("spread"), familia=familia, serie=serie,
                                           ley=f.get("ley"), liquidacion=liq,
                                           sin_emitir=liq != liquidacion, origen=origen))
        except (ErrorAPI, ValueError) as e:
            errores.append(f"{ticker}{' (' + familia.replace('_', ' ') + ')' if dual else ''}: {e}")
    return curvas, contexto, errores
