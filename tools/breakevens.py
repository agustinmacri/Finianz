"""Herramienta de breakevens entre curvas de bonos en pesos y en dólares.

Arma las curvas con la calculadora propia (tools/bonos.py) a precios de mercado y las cruza con
renta_fija/calculadoras/breakeven.py. Definiciones en docs/convenciones-renta-fija.md.
"""
from datetime import date, timedelta

from admin_datos import rem as db_rem
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


def _curvas(operacion: date, liquidacion: date, fecha_precios: date | None,
            familias: set[str] | None = None) -> tuple[dict, dict, list[str]]:
    """TEA y duration (en días) de cada bono a precio de mercado, por curva (solo 'familias', si se indica)."""
    curvas = {"tasa_fija": [], "cer": [], "dl": [], "tamar": [], "hd": []}
    contexto, errores = {}, []
    ajustar = lambda d: bonos.feriados.proximo_dia_habil(d, bonos.CALENDARIO_HABILES)
    for f in fichas.todas():
        familia, ticker = f["familia"], f["ticker"].upper()
        if familias is not None and familia not in familias:
            continue
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
                             plazo=r["plazo_residual"], dias_30_360=motor.dias_30_360(f["emision"], f["vencimiento"]),
                             emision=f["emision"], desde_estimar=d["desde_estimar"], fin_ventana=d["fin"])
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


def _tabla(filas: list[dict], nombre_base: str, nombre_otra: str, extras=()) -> str:
    """extras: columnas adicionales [(título, función fila -> texto)]."""
    lineas = [f"Bono | vence | días | TEA {nombre_base} | TEA {nombre_otra} (interp.) | anual | mensual | acumulado"
              + "".join(f" | {titulo}" for titulo, _ in extras)]
    for f in filas:
        if f["anual"] is None:
            lineas.append(f"{f['ticker']} | {f['vencimiento']} | {f['x']:.0f} | {bonos._pct(f['tea'])} | fuera del rango de la otra curva")
            continue
        extra = "".join(f" | {_seguro(funcion, f)}" for _, funcion in extras)
        lineas.append(f"{f['ticker']} | {f['vencimiento']} | {f['x']:.0f} | {bonos._pct(f['tea'])} | {bonos._pct(f['tea_otra'])} | "
                      f"{bonos._pct(f['anual'])} | {bonos._pct(f['mensual'])} | {bonos._pct(f['acumulado'])}{extra}")
    tramos = be.forwards(filas)
    if tramos:
        lineas.append("Forwards (entre vencimientos consecutivos): " + "; ".join(
            f"{t['desde']}→{t['hasta']} ({t['dias']:.0f} d): {bonos._pct(t['mensual'])} mensual, {bonos._pct(t['anual'])} anual"
            for t in tramos))
    return "\n".join(lineas)


def _seguro(funcion, fila) -> str:
    try:
        return funcion(fila)
    except (ValueError, KeyError, TypeError, ZeroDivisionError):
        return "sin dato"


def _rem(liquidacion: date) -> dict | None:
    """Lo que espera el último REM: inflación por mes (con la publicada), tipo de cambio y TAMAR."""
    from tools import proyeccion_cer
    relevamiento = db_rem.ultimo()
    if relevamiento is None:
        return None
    contexto = {"relevamiento": relevamiento}
    try:
        hasta = (liquidacion.year + 6, 12)
        contexto["inflacion"] = proyeccion_cer.inflacion_rem_por_mes(hasta)[1]
    except (ErrorAPI, ValueError):
        contexto["inflacion"] = None
    tc = db_rem.por_mes("TIPO_CAMBIO", relevamiento, incluir_proximos=True)
    contexto["tipo_cambio"] = [(date(a, m, 15), v) for (a, m), v in tc.items()]   # promedio del mes, a mitad de mes
    tamar_mensual = db_rem.por_mes("TAMAR", relevamiento, incluir_anuales=False)
    tamar_12m = db_rem.valores("TAMAR", relevamiento).get("prox12")
    contexto["tamar"] = (be.camino_con_resto({m: v / 100 for m, v in tamar_mensual.items()}, tamar_12m / 100)
                         if tamar_mensual and tamar_12m is not None else None)
    return contexto


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
    rem = _rem(liquidacion)
    texto = [f"Breakevens entre curvas – calculadora de Finianz (liquidación {liquidacion}, T+1)",
             "Cada bono contra la otra curva interpolada a su duration en días; TEA contra TEA; sin ajustar rezagos."]
    if rem:
        texto.append(f"Comparación con el REM del BCRA, relevamiento {rem['relevamiento']} (mediana).")

    def fin(f):                                   # fecha hasta la que mide cada breakeven
        return liquidacion + timedelta(days=round(f["x"]))
    for t in tipos:
        texto.append(f"\n{NOMBRES[t]}")
        if t == "inflacion":
            extras = []
            if rem and rem["inflacion"]:
                def rem_anual(f):
                    acum = be.inflacion_acumulada(rem["inflacion"], liquidacion, fin(f))
                    return (1 + acum) ** (365 / f["x"]) - 1
                extras = [("inflación REM anual (mismo plazo)", lambda f: bonos._pct(rem_anual(f))),
                          ("breakeven − REM", lambda f: f"{(f['anual'] - rem_anual(f)) * 100:+.2f} pp")]
            texto.append(_tabla(be.cruzar(curvas["cer"], curvas["tasa_fija"], be.inflacion), "CER (real)", "tasa fija", extras))
            if extras:
                texto.append("Breakeven por encima del REM: el mercado descuenta más inflación que la que espera el REM "
                             "(si se cumple el REM, conviene la tasa fija); por debajo, conviene el CER.")
        elif t == "devaluacion":
            tc = contexto.get("a3500")
            extras = [("A3500 implícito", lambda f: f"{tc[0] * (1 + f['acumulado']):,.2f}")] if tc else []
            if tc and rem and rem["tipo_cambio"]:
                puntos_rem = [(operacion, tc[0]), *rem["tipo_cambio"]]
                def tc_rem(f):
                    v = be.interpolar_log(puntos_rem, fin(f))
                    if v is None:
                        raise ValueError
                    return v
                extras += [("tipo de cambio REM", lambda f: f"{tc_rem(f):,.2f}"),
                           ("implícito / REM", lambda f: bonos._pct(tc[0] * (1 + f["acumulado"]) / tc_rem(f) - 1))]
            texto.append(_tabla(be.cruzar(curvas["dl"], curvas["tasa_fija"], be.devaluacion), "DL (USD)", "tasa fija", extras))
            if len(extras) > 1:
                texto.append("Tipo de cambio REM: interpolado entre hoy y los promedios mensuales que espera el REM (ubicados a mitad "
                             "de mes). Implícito por encima del REM: el mercado se cubre de más devaluación que la esperada "
                             "(si se cumple el REM, conviene la tasa fija); por debajo, conviene el dollar linked.")
            if tc:
                texto.append(f"A3500 de partida: {tc[0]:,.4f} ({tc[1]}{', estimado' if tc[2] else ''})")
        elif t == "tipo_cambio_real":
            texto.append(_tabla(be.cruzar(curvas["dl"], curvas["cer"], be.tipo_cambio_real), "DL (USD)", "CER (real)"))
            texto.append("Positivo: el mercado descuenta que el dólar oficial sube más que la inflación (depreciación real).")
        elif t == "brecha":
            tc = contexto.get("a3500")
            actual = _brecha_actual(fecha_precios, tc[0]) if tc else None
            extras = [("brecha implícita", lambda f: f"{bonos._pct(actual * (1 + f['acumulado']) - 1)}")] if actual else []
            texto.append(_tabla(be.cruzar(curvas["dl"], curvas["hd"], be.brecha), "DL (USD oficial)", "Bonares (USD MEP)", extras))
            if actual:
                texto.append(f"Brecha actual (MEP implícito AL30/AL30D sobre A3500): {bonos._pct(actual - 1)}. "
                             "Ojo: el Bonar suma riesgo de crédito en dólares que el dollar linked no tiene.")
        elif t == "tamar":
            puntos = [(p["x"], p["tea"]) for p in curvas["tasa_fija"]]
            ref = contexto.get("tamar_referencia")
            con_rem = bool(rem and rem["tamar"])
            lineas = ["Bono | vence | TEA bono | TEA tasa fija (interp.) | TAMAR implícita de los días por publicar"
                      + (" | TAMAR REM (mismos días) | TEA del bono con la TAMAR del REM" if con_rem else "")
                      + (f" | TAMAR actual {bonos._pct(ref)}" if ref else "")]
            for p in sorted(curvas["tamar"], key=lambda p: p["x"]):
                tf = be.interpolar(puntos, p["x"])
                if tf is None:
                    lineas.append(f"{p['ticker']} | {p['vencimiento']} | {bonos._pct(p['tea'])} | fuera del rango de la tasa fija")
                    continue
                imp = be.tamar_implicita(tf, p["precio"], p["plazo"], p["dias_30_360"], p["margen"], p["conocidas"], p["a_estimar"])
                fila = (f"{p['ticker']} | {p['vencimiento']} | {bonos._pct(p['tea'])} | {bonos._pct(tf)} | "
                        + (f"{bonos._pct(imp)} TNA" if imp is not None else "sin días por publicar"))
                if con_rem and p["a_estimar"]:
                    dias = bonos.feriados.dias_habiles_entre(p["desde_estimar"], p["fin_ventana"], bonos.CALENDARIO_HABILES)
                    valores = [rem["tamar"]((d.year, d.month)) for d in dias]
                    tamar_bono = (sum(p["conocidas"]) + sum(valores)) / (len(p["conocidas"]) + len(valores))
                    r = tamar.calcular(p["precio"], tamar_bono, p["margen"], p["emision"], p["vencimiento"], liquidacion,
                                       ref or 0)
                    fila += f" | {bonos._pct(sum(valores) / len(valores))} TNA | {bonos._pct(r['tea'])}"
                lineas.append(fila)
            texto.append("\n".join(lineas))
            if con_rem:
                texto.append("TAMAR REM: la mediana mensual del REM en los meses que trae y, para los demás, su valor a 12 meses sin cambios. "
                             "Si la TEA con el REM supera la tasa fija, el bono TAMAR conviene si se cumple el REM.")
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
        "vencimiento y forwards entre vencimientos. Si hay REM cargado, compara la inflación, el tipo de cambio y la TAMAR "
        "implícitos con lo que espera el REM. Excluye los duales."
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
