"""Herramienta de breakevens entre curvas de bonos en pesos y en dólares.

Arma las curvas con la calculadora propia (tools/bonos.py) a precios de mercado y las cruza con
renta_fija/calculadoras/breakeven.py. Definiciones en docs/convenciones-renta-fija.md.
"""
from datetime import date

from conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas
from renta_fija.calculadoras import (breakeven as be, cer, cer_cupon, dolar_linked, hard_dollar, motor, tamar,
                                     tasa_fija)
from tools import bonos

TIPOS = ("inflacion", "devaluacion", "tipo_cambio_real", "brecha", "tamar")
NOMBRES = {"inflacion": "Inflación implícita (CER vs tasa fija)",
           "devaluacion": "Devaluación implícita del A3500 (dollar linked vs tasa fija)",
           "tipo_cambio_real": "Variación implícita del tipo de cambio real (dollar linked vs CER)",
           "brecha": "Variación implícita de la brecha MEP / A3500 (dollar linked vs Bonares en MEP)",
           "tamar": "TAMAR implícita (Bonos TAMAR vs tasa fija)"}


def _curvas(operacion: date, liquidacion: date, fecha_precios: date | None) -> tuple[dict, dict, list[str]]:
    """TEA y duration (en días) de cada bono a precio de mercado, por curva."""
    curvas = {"tasa_fija": [], "cer": [], "dl": [], "tamar": [], "hd": []}
    contexto, errores = {}, []
    ajustar = lambda d: bonos.feriados.proximo_dia_habil(d, bonos.CALENDARIO_HABILES)
    for f in fichas.todas():
        familia, ticker = f["familia"], f["ticker"].upper()
        if liquidacion >= f["vencimiento"] or "DUAL" in f.get("tipo", "").upper():
            continue                                         # vencidos, y duales (tienen opcionalidad)
        if familia == "hard_dollar" and f["ley"] != "AR":
            continue                                         # la brecha se mide con Bonares
        try:
            precio, _ = bonos._precio(ticker + ("D" if familia == "hard_dollar" else ""), fecha_precios)
            punto = {"ticker": ticker, "vencimiento": f["vencimiento"], "precio": precio}
            if familia == "tasa_fija_capitalizable":
                r = tasa_fija.calcular_capitalizable(precio, tasa_fija.pago_final(f["tem"], f["emision"], f["vencimiento"]),
                                                     liquidacion, f["vencimiento"])
                curva, tea, dur = "tasa_fija", r["tea"], r["duration"]
            elif familia == "tasa_fija_cupon":
                r = tasa_fija.calcular_cupon(precio, liquidacion, f["pagos"], f["cupon"], f["frecuencia"], f["emision"], ajustar)
                curva, tea, dur = "tasa_fija", r["tir_real"], r["duration"]
            elif familia == "cer_cero_cupon":
                _, f2, cer_corriente = bonos._datos_cer(f, liquidacion)
                r = cer.calcular(precio, f2["cer_inicial"], cer_corriente, liquidacion, f["vencimiento"])
                curva, tea, dur = "cer", r["tea_real"], r["duration"]
            elif familia == "cer_cupon":
                _, f2, cer_corriente = bonos._datos_cer(f, liquidacion)
                r = cer_cupon.calcular(precio, f2["cer_inicial"], cer_corriente, liquidacion, f["pagos"], f["cupon"],
                                       f["frecuencia"], f["emision"], ajustar)
                curva, tea, dur = "cer", r["tir_real"], r["duration"]
            elif familia == "dolar_linked_bullet":
                tc, fecha_tc, estimado = bonos._a3500(operacion)
                contexto["a3500"] = (tc, fecha_tc, estimado)
                r = dolar_linked.calcular_bullet(precio, tc, liquidacion, f["vencimiento"])
                curva, tea, dur = "dl", r["tea"], r["duration"]
            elif familia == "tamar_capitalizable":
                d = bonos._datos_tamar(f, operacion)
                r = tamar.calcular(precio, d["tamar_bono"], f["margen"], f["emision"], f["vencimiento"], liquidacion,
                                   d["referencia"])
                contexto["tamar_referencia"] = d["referencia"]
                punto.update(margen=f["margen"], conocidas=d["conocidas"], a_estimar=d["a_estimar"],
                             plazo=r["plazo_residual"], dias_30_360=motor.dias_30_360(f["emision"], f["vencimiento"]))
                curva, tea, dur = "tamar", r["tea"], r["duration"]
            elif familia == "hard_dollar":
                r = hard_dollar.calcular(precio, liquidacion, f["pagos"], f["tramos"], f["emision"], ajustar)
                curva, tea, dur = "hd", r["tea"], r["duration"]
            else:
                continue
            curvas[curva].append(dict(punto, tea=tea, x=dur * 365))
        except (ErrorAPI, ValueError) as e:
            errores.append(f"{ticker}: {e}")
    return curvas, contexto, errores


def _brecha_actual(fecha_precios: date | None, a3500: float) -> float | None:
    try:
        pesos, _ = bonos._precio("AL30", fecha_precios)
        mep, _ = bonos._precio("AL30D", fecha_precios)
        return pesos / mep / a3500
    except (ErrorAPI, ValueError):
        return None


def _tabla(filas: list[dict], nombre_base: str, nombre_otra: str, nivel=None) -> str:
    lineas = [f"Bono | vence | días | TEA {nombre_base} | TEA {nombre_otra} (interp.) | anual | mensual | acumulado"
              + (f" | {nivel[0]}" if nivel else "")]
    for f in filas:
        if f["anual"] is None:
            lineas.append(f"{f['ticker']} | {f['vencimiento']} | {f['x']:.0f} | {bonos._pct(f['tea'])} | fuera del rango de la otra curva")
            continue
        extra = f" | {nivel[1](f)}" if nivel else ""
        lineas.append(f"{f['ticker']} | {f['vencimiento']} | {f['x']:.0f} | {bonos._pct(f['tea'])} | {bonos._pct(f['tea_otra'])} | "
                      f"{bonos._pct(f['anual'])} | {bonos._pct(f['mensual'])} | {bonos._pct(f['acumulado'])}{extra}")
    tramos = be.forwards(filas)
    if tramos:
        lineas.append("Forwards (entre vencimientos consecutivos): " + "; ".join(
            f"{t['desde']}→{t['hasta']} ({t['dias']:.0f} d): {bonos._pct(t['mensual'])} mensual, {bonos._pct(t['anual'])} anual"
            for t in tramos))
    return "\n".join(lineas)


def calcular_breakevens(tipo: str = "todos", fecha: str | None = None) -> str:
    tipos = TIPOS if tipo == "todos" else (tipo,)
    if any(t not in TIPOS for t in tipos):
        return f"Tipo desconocido: {tipo}. Opciones: todos, {', '.join(TIPOS)}."
    try:
        operacion = date.fromisoformat(fecha) if fecha else date.today()
        bonos._asegurar_feriados(operacion)
        liquidacion = bonos.feriados.sumar_dias_habiles(operacion, bonos.PLAZO_LIQUIDACION, "BYMA")
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    fecha_precios = operacion if fecha else None
    curvas, contexto, errores = _curvas(operacion, liquidacion, fecha_precios)
    texto = [f"Breakevens entre curvas – calculadora de Finianz (liquidación {liquidacion}, T+1)",
             "Cada bono contra la otra curva interpolada a su duration en días; TEA contra TEA; sin ajustar rezagos."]
    for t in tipos:
        texto.append(f"\n{NOMBRES[t]}")
        if t == "inflacion":
            texto.append(_tabla(be.cruzar(curvas["cer"], curvas["tasa_fija"], be.inflacion), "CER (real)", "tasa fija"))
        elif t == "devaluacion":
            tc = contexto.get("a3500")
            nivel = ("A3500 implícito", lambda f: f"{tc[0] * (1 + f['acumulado']):,.2f}") if tc else None
            texto.append(_tabla(be.cruzar(curvas["dl"], curvas["tasa_fija"], be.devaluacion), "DL (USD)", "tasa fija", nivel))
            if tc:
                texto.append(f"A3500 de partida: {tc[0]:,.4f} ({tc[1]}{', estimado' if tc[2] else ''})")
        elif t == "tipo_cambio_real":
            texto.append(_tabla(be.cruzar(curvas["dl"], curvas["cer"], be.tipo_cambio_real), "DL (USD)", "CER (real)"))
            texto.append("Positivo: el mercado descuenta que el dólar oficial sube más que la inflación (depreciación real).")
        elif t == "brecha":
            tc = contexto.get("a3500")
            actual = _brecha_actual(fecha_precios, tc[0]) if tc else None
            nivel = ("brecha implícita", lambda f: f"{bonos._pct(actual * (1 + f['acumulado']) - 1)}") if actual else None
            texto.append(_tabla(be.cruzar(curvas["dl"], curvas["hd"], be.brecha), "DL (USD oficial)", "Bonares (USD MEP)", nivel))
            if actual:
                texto.append(f"Brecha actual (MEP implícito AL30/AL30D sobre A3500): {bonos._pct(actual - 1)}. "
                             "Ojo: el Bonar suma riesgo de crédito en dólares que el dollar linked no tiene.")
        elif t == "tamar":
            puntos = [(p["x"], p["tea"]) for p in curvas["tasa_fija"]]
            ref = contexto.get("tamar_referencia")
            lineas = ["Bono | vence | TEA bono | TEA tasa fija (interp.) | TAMAR implícita de los días por publicar"
                      + (f" | TAMAR actual {bonos._pct(ref)}" if ref else "")]
            for p in sorted(curvas["tamar"], key=lambda p: p["x"]):
                tf = be.interpolar(puntos, p["x"])
                if tf is None:
                    lineas.append(f"{p['ticker']} | {p['vencimiento']} | {bonos._pct(p['tea'])} | fuera del rango de la tasa fija")
                    continue
                imp = be.tamar_implicita(tf, p["precio"], p["plazo"], p["dias_30_360"], p["margen"], p["conocidas"], p["a_estimar"])
                lineas.append(f"{p['ticker']} | {p['vencimiento']} | {bonos._pct(p['tea'])} | {bonos._pct(tf)} | "
                              + (f"{bonos._pct(imp)} TNA" if imp is not None else "sin días por publicar"))
            texto.append("\n".join(lineas))
    if errores:
        texto.append("\nBonos que no se pudieron calcular: " + " | ".join(errores))
    return "\n".join(texto)


CALCULAR_BREAKEVENS = {
    "name": "calcular_breakevens",
    "description": (
        "Breakevens entre curvas de bonos, a precios de mercado, con la calculadora propia: inflación implícita "
        "(CER vs tasa fija), devaluación implícita del A3500 (dollar linked vs tasa fija) con el A3500 implícito por "
        "vencimiento, variación del tipo de cambio real (dollar linked vs CER), variación de la brecha MEP/A3500 "
        "(dollar linked vs Bonares) y TAMAR implícita (Bonos TAMAR vs tasa fija). Anual, mensual, acumulado al "
        "vencimiento y forwards entre vencimientos. Excluye los duales."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "tipo": {"type": "string", "enum": ["todos", *TIPOS], "description": "Qué breakeven calcular (por defecto, todos)"},
            "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD para usar los cierres de ese día (opcional)"},
        },
    },
}

HERRAMIENTAS = [(CALCULAR_BREAKEVENS, calcular_breakevens)]
