"""Calculadora de bonos propia (CER, tasa fija y TAMAR), con las definiciones de Agustin (docs/convenciones-renta-fija.md).

Arma el cálculo con piezas de cada capa:
- la ficha técnica del bono (renta_fija/fichas/*.toml, vía renta_fija/leer_fichas.py);
- el precio (PPI en vivo, o el cierre guardado en la base propia para una fecha pasada);
- el CER y la TAMAR (base propia de series, cargada desde el BCRA), la inflación del BCRA y los días hábiles (base de feriados);
- la calculadora de la familia (renta_fija/calculadoras/).
Ningún número sale de cálculos externos: de afuera vienen solo datos.
"""
from datetime import date, timedelta

from conexiones import fred
from conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas, mercado, metricas
from renta_fija.calculadoras import breakeven, cer, dolar_linked, hard_dollar, motor, tasa_fija
from tools.caminos import pct as _pct

# Los números salen de renta_fija/metricas.py (la misma calculadora de las curvas, el panel y las carteras, con las
# reglas de pago conocido); acá se arma el texto. Los datos de mercado vienen de renta_fija/mercado.py.


def calcular_bono(ticker: str, precio: float | None = None, fecha: str | None = None,
                  inflacion_mensual: float | None = None, fuente_inflacion: str | None = None,
                  fuente_tamar: str = "actual") -> str:
    try:
        lista = fichas.fichas_de(ticker)
        if not lista and ticker.upper()[-1:] in ("D", "C"):     # AL30D / GD30C: el bono en dólares
            lista = [f for f in fichas.fichas_de(ticker[:-1]) if f["familia"] == "hard_dollar"]
        if not lista:
            disponibles = ", ".join(sorted(fichas.leer_todas()))
            return f"No hay ficha técnica de {ticker.upper()}. Bonos con ficha: {disponibles}."
    except fichas.ErrorFicha as e:
        return f"Error en las fichas técnicas: {e}"
    f = lista[0]

    # Datos comunes a todos los bonos: liquidación y precio
    try:
        operacion = date.fromisoformat(fecha) if fecha else date.today()
        mercado.asegurar_feriados(operacion, f["vencimiento"])
        liquidacion = mercado.feriados.sumar_dias_habiles(operacion, mercado.PLAZO_LIQUIDACION, "BYMA")
        if liquidacion >= f["vencimiento"]:
            return f"{ticker.upper()} vence el {f['vencimiento']}: no quedan flujos para la liquidación del {liquidacion}."
        if f["familia"] == "hard_dollar":
            return _hard_dollar(f, precio, date.fromisoformat(fecha) if fecha else None, liquidacion, operacion)
        if precio is None:
            precio, origen = mercado.precio(ticker, date.fromisoformat(fecha) if fecha else None)
        else:
            origen = "precio indicado"
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"

    encabezado = (
        f"{ticker.upper()} ({f['tipo']}, vence {f['vencimiento']}) – calculadora de Finianz\n"
        f"Precio: {precio:,.2f} por 100 VN ({origen}) | liquidación {liquidacion} (T+{mercado.PLAZO_LIQUIDACION})\n"
    )
    secciones, avisos = [], ""
    for f in lista:                       # un dual tiene una ficha por cada forma de calcularlo
        try:
            texto = _calcular_ficha(f, precio, liquidacion, operacion, inflacion_mensual)
        except ErrorAPI as e:
            texto = f"Error: {e}"
        except ValueError as e:
            texto = f"Error en el cálculo: {e}"
        if len(lista) > 1:
            texto = f"\n— Calculado como {NOMBRE_FAMILIA[f['familia']]} —\n" + texto
        secciones.append(texto)
        if not f.get("revisado"):
            avisos += (f"\nAVISO: la ficha {NOMBRE_FAMILIA[f['familia']]} todavía no fue revisada por Agustin; "
                       "tomá ese resultado como preliminar.")
        if f.get("nota") and f["nota"] not in avisos:
            avisos += f"\nNOTA: {f['nota']}"
    familias = {f["familia"] for f in lista}
    if {"tasa_fija_capitalizable", "tamar_capitalizable"} <= familias:
        secciones.append(_dual_tasa_fija_tamar(lista, precio, liquidacion, operacion, fuente_tamar))
    if {"dolar_linked_bullet", "tamar_capitalizable"} <= familias:
        secciones.append(_dual_dl_tamar(lista, precio, liquidacion, operacion, fuente_tamar,
                                        date.fromisoformat(fecha) if fecha else None))
    if "cer_cero_cupon" in familias and "tamar_capitalizable" in familias:
        if fuente_inflacion is None:
            from admin_datos import rem as db_rem
            fuente_inflacion = "rem" if db_rem.ultimo() else "breakeven"
        secciones.append(_dual_cer_tamar(lista, precio, liquidacion, operacion, fuente_inflacion, fuente_tamar,
                                         date.fromisoformat(fecha) if fecha else None))
    return encabezado + "\n".join(secciones) + avisos


def _dual_tasa_fija_tamar(lista: list[dict], precio: float, liquidacion: date, operacion: date,
                          fuente_tamar: str = "actual") -> str:
    """Qué pata paga un dual tasa fija / TAMAR: la de mayor pago final (la TAMAR, con la parte por publicar proyectada)."""
    from tools import proyecciones
    try:
        fija = next(f for f in lista if f["familia"] == "tasa_fija_capitalizable")
        pata_tamar = next(f for f in lista if f["familia"] == "tamar_capitalizable")
        pf_fija = tasa_fija.pago_final(fija["cupon"], fija["emision"], fija["vencimiento"])
        camino, desc_tamar = proyecciones.camino_tamar(fuente_tamar, operacion)
        r, d, _, _ = proyecciones.tamar_proyectada(pata_tamar, precio, liquidacion, operacion, camino)
    except (ErrorAPI, ValueError, StopIteration) as e:
        return f"\n— Qué pata paga —\nSin dato: {e}"
    gana = "tasa fija" if pf_fija >= r["pago_final"] else "TAMAR"
    pago = max(pf_fija, r["pago_final"])
    tna = (pago / precio - 1) * 365 / r["plazo_residual"]
    tea = (pago / precio) ** (365 / r["plazo_residual"]) - 1
    # TAMAR de los días por publicar con la que la pata TAMAR iguala a la fija
    plazo, d360 = r["plazo_residual"], motor.dias_30_360(pata_tamar["emision"], pata_tamar["vencimiento"])
    tea_fija = (pf_fija / precio) ** (365 / plazo) - 1
    umbral = breakeven.tamar_implicita(tea_fija, precio, plazo, d360, pata_tamar["margen"], d["conocidas"], d["a_estimar"])
    linea_umbral = (f"\nLas dos patas pagan lo mismo si la TAMAR de los {d['a_estimar']} días hábiles que faltan publicar promedia "
                    f"{_pct(umbral)} TNA: por encima paga la TAMAR, por debajo la tasa fija (hoy, últimos 5 días: "
                    f"{_pct(d['referencia'])})." if umbral is not None else
                    "\nLa ventana de la TAMAR ya está completa: el resultado es definitivo.")
    return (
        f"\n— Qué pata paga (al vencimiento, la de mayor pago final) —\n"
        f"Pata tasa fija: pago final {pf_fija:.4f} | TNA {_pct((pf_fija / precio - 1) * 365 / plazo)} | TEA {_pct(tea_fija)}\n"
        f"Pata TAMAR: pago final {r['pago_final']:.4f} | TNA {_pct(r['tna'])} | TEA {_pct(r['tea'])} "
        f"({d['a_estimar']} días por publicar con {desc_tamar})\n"
        f"→ Con estos supuestos paga la pata {gana}. Rendimiento del dual: TNA {_pct(tna)} | TEA (TIR) {_pct(tea)}" + linea_umbral
    )


def _dual_dl_tamar(lista: list[dict], precio: float, liquidacion: date, operacion: date, fuente_tamar: str,
                   fecha_precios: date | None) -> str:
    """Qué pata paga un dual TAMAR / dollar linked (TMVE8): al vencimiento, el mayor entre el VN en dólares al A3500 de
    pago (3.er día hábil anterior) y el VN al tipo de cambio inicial capitalizado a TAMAR. Precio y pagos en pesos por
    100 VN en dólares. Devuelve el A3500 de indiferencia (y la devaluación que implica) y lo compara con el REM y con
    el breakeven del mercado."""
    from tools import proyecciones
    try:
        pata_dl = next(f for f in lista if f["familia"] == "dolar_linked_bullet")
        pata_tamar = next(f for f in lista if f["familia"] == "tamar_capitalizable")
        escala = mercado.tipo_cambio_inicial(pata_tamar)
        if escala == 1:
            return ("\n— Qué pata paga —\nFalta el tipo de cambio inicial de la pata TAMAR: agregá "
                    "fecha_tipo_cambio_inicial (A3500 del día hábil anterior a la licitación original) o "
                    "tipo_cambio_inicial a su ficha.")
        camino, desc_tamar = proyecciones.camino_tamar(fuente_tamar, operacion)
        r, d, _, _ = proyecciones.tamar_proyectada(pata_tamar, precio, liquidacion, operacion, camino)
        tc_hoy, fecha_tc, _ = mercado.a3500(operacion)
    except (ErrorAPI, ValueError, StopIteration, KeyError) as e:
        return f"\n— Qué pata paga —\nSin dato: {e}"
    vto = pata_dl["vencimiento"]
    fecha_pago_tc = mercado.feriados.sumar_dias_habiles(vto, -mercado.REZAGO_TC_PAGO_DL, mercado.CALENDARIO_HABILES)
    pago_tamar = r["pago_final"] * escala                      # pesos por 100 VN en dólares
    tc_indiferencia = pago_tamar / dolar_linked.PAGO_FINAL_USD
    dias_tc = max((fecha_pago_tc - operacion).days, 1)
    devaluacion = tc_indiferencia / tc_hoy - 1
    devaluacion_anual = (1 + devaluacion) ** (365 / dias_tc) - 1
    plazo = (vto - liquidacion).days
    tea = lambda pago: (pago / precio) ** (365 / plazo) - 1
    lineas = [
        "\n— Qué pata paga (al vencimiento, la de mayor pago; por 100 VN en dólares, en pesos) —",
        f"Pata TAMAR: VN al tipo de cambio inicial ({escala:,.2f}) capitalizado a TAMAR → pago final "
        f"${pago_tamar:,.2f} | TEA {_pct(r['tea'])} ({d['a_estimar']} días por publicar con {desc_tamar})",
        f"Pata dollar linked: USD 100 al A3500 del {fecha_pago_tc:%d/%m/%Y} (3.er día hábil anterior al pago). "
        f"Con el A3500 de hoy ({tc_hoy:,.2f}, {fecha_tc:%d/%m/%Y}) pagaría ${100 * tc_hoy:,.2f}.",
        f"Indiferencia: las dos patas pagan lo mismo con un A3500 de {tc_indiferencia:,.2f} al {fecha_pago_tc:%d/%m/%Y}, "
        f"una devaluación de {_pct(devaluacion)} desde hoy ({_pct(devaluacion_anual)} anual). Por encima paga la pata "
        "dollar linked; por debajo, la TAMAR."]
    for fuente, nombre in (("rem", "REM"), ("breakeven", "breakeven del mercado (dollar linked contra tasa fija)")):
        try:
            nivel, _, _, _ = proyecciones.camino_dolar("oficial", fuente, operacion, fecha_precios)
            tc_esperado = nivel(fecha_pago_tc)
        except (ErrorAPI, ValueError, KeyError, ZeroDivisionError) as e:
            lineas.append(f"Con el {nombre}: sin dato ({str(e).splitlines()[0][:100]}).")
            continue
        pago_dl = dolar_linked.PAGO_FINAL_USD * tc_esperado
        gana = "dollar linked" if pago_dl > pago_tamar else "TAMAR"
        dev = tc_esperado / tc_hoy - 1
        lineas.append(f"Con el {nombre}: A3500 {tc_esperado:,.2f} ({_pct(dev)} desde hoy, "
                      f"{_pct((1 + dev) ** (365 / dias_tc) - 1)} anual) → paga la pata {gana}; "
                      f"rendimiento del dual TEA {_pct(tea(max(pago_dl, pago_tamar)))}.")
    if d["a_estimar"] == 0:
        lineas.append("La ventana de la TAMAR ya está completa: el pago de la pata TAMAR es definitivo.")
    return "\n".join(lineas)


def _dual_cer_tamar(lista: list[dict], precio: float, liquidacion: date, operacion: date, fuente_inflacion: str,
                    fuente_tamar: str, fecha_precios: date | None) -> str:
    """Qué pata paga un dual CER / TAMAR: la de mayor pago final, con el CER y la TAMAR proyectados."""
    from renta_fija.calculadoras import proyeccion_cer as pc
    from tools import proyeccion_cer, proyecciones
    try:
        pata_cer = next(f for f in lista if f["familia"] == "cer_cero_cupon")
        pata_tamar = next(f for f in lista if f["familia"] == "tamar_capitalizable")
        _, f2, _ = mercado.datos_cer(pata_cer, liquidacion)
        fecha_final = mercado.fecha_cer(pata_cer["vencimiento"])
        caminos, desc_inflacion, serie, publicadas = proyeccion_cer.camino_inflacion(
            fuente_inflacion, liquidacion, pc.mes_aplicado(fecha_final), None, operacion, fecha_precios)
        ultimo = max(serie)
        inflacion = {m: v for m, (v, _) in caminos.items()}
        cer_final = serie[fecha_final] if fecha_final <= ultimo else pc.proyectar(serie, inflacion, fecha_final)[fecha_final]
        pago_cer = 100 * cer_final / f2["cer_inicial"]
        camino, desc_tamar = proyecciones.camino_tamar(fuente_tamar, operacion)
        r, d, tamar_bono, _ = proyecciones.tamar_proyectada(pata_tamar, precio, liquidacion, operacion, camino)
    except (ErrorAPI, ValueError, StopIteration, KeyError) as e:
        return f"\n— Qué pata paga —\nSin dato: {e}"
    plazo = r["plazo_residual"]
    rinde = lambda pago: ((pago / precio - 1) * 365 / plazo, (pago / precio) ** (365 / plazo) - 1)
    tna_cer, tea_cer = rinde(pago_cer)
    gana = "CER" if pago_cer >= r["pago_final"] else "TAMAR"
    tna, tea = rinde(max(pago_cer, r["pago_final"]))
    # Inflación mensual plana (en los meses sin publicar) con la que las dos patas pagan lo mismo
    if fecha_final <= ultimo:
        linea = "\nEl CER final ya está publicado: la pata CER es definitiva."
    else:
        objetivo = r["pago_final"] * f2["cer_inicial"] / 100
        meses = list(caminos)
        cer_con = lambda x: pc.proyectar(serie, {m: x for m in meses}, fecha_final)[fecha_final]
        bajo, alto = -0.05, 0.5
        for _ in range(80):
            medio = (bajo + alto) / 2
            bajo, alto = (medio, alto) if cer_con(medio) < objetivo else (bajo, medio)
        linea = (f"\nLas dos patas pagan lo mismo con una inflación mensual plana de {_pct((bajo + alto) / 2)} desde "
                 f"{meses[0][1]:02d}/{meses[0][0]} (los meses sin publicar): por encima paga la CER, por debajo la TAMAR.")
    return (
        f"\n— Qué pata paga (al vencimiento, la de mayor pago final) —\n"
        f"Pata CER: CER final {cer_final:,.4f} al {fecha_final} ({'publicado' if fecha_final <= ultimo else 'proyectado: ' + desc_inflacion}) "
        f"→ pago final {pago_cer:.4f} | TNA {_pct(tna_cer)} | TEA {_pct(tea_cer)}\n"
        f"Pata TAMAR: TAMAR del bono {_pct(tamar_bono)} ({desc_tamar}) → pago final {r['pago_final']:.4f} | "
        f"TNA {_pct(r['tna'])} | TEA {_pct(r['tea'])}\n"
        f"→ Con estos supuestos paga la pata {gana}. Rendimiento del dual: TNA {_pct(tna)} | TEA (TIR) {_pct(tea)}" + linea
    )



NOMBRE_FAMILIA = {
    "cer_cero_cupon": "CER", "cer_cupon": "CER", "tasa_fija_capitalizable": "tasa fija",
    "tasa_fija_cupon": "tasa fija", "tamar_capitalizable": "TAMAR", "dolar_linked_bullet": "dollar linked",
    "dolar_linked_cupon": "dollar linked", "tasa_fija_descuento": "tasa fija",
}


def _calcular_ficha(f: dict, precio: float, liquidacion: date, operacion: date,
                    inflacion_mensual: float | None) -> str:
    """El texto de una ficha. Los números salen de metricas.calculadora; si el pago ya se conoce (CER, A3500 o TAMAR
    publicados), se agrega la línea de tasa fija."""
    contexto = {}
    m = metricas.calculadora(f, liquidacion, operacion, contexto)(precio)
    r = m.get("indexado") or m["detalle"]           # el cálculo como bono indexado, aunque el pago ya se conozca
    familia = f["familia"]
    if familia == "cer_cero_cupon":
        texto = contexto["datos_cer"][0] + _cer_cero_cupon(f, r, inflacion_mensual)
    elif familia == "cer_cupon":
        texto = contexto["datos_cer"][0] + _cer_cupon(r)
    elif familia == "tasa_fija_capitalizable":
        texto = _tasa_fija_capitalizable(f, r)
    elif familia == "tamar_capitalizable":
        texto = _tamar_capitalizable(f, r, contexto["datos_tamar"])
    elif familia == "dolar_linked_bullet":
        texto = _dolar_linked_bullet(f, r, operacion, contexto["a3500"])
    elif familia == "dolar_linked_cupon":
        texto = _dolar_linked_cupon(f, r, operacion, contexto["a3500"])
    elif familia == "tasa_fija_descuento":
        texto = _tasa_fija_descuento(r)
    else:
        texto = _tasa_fija_cupon(r)
    return texto + _pago_conocido(m)


def _pago_conocido(m: dict) -> str:
    """La línea del bono que ya pasó a tasa fija (pago final conocido el día de la operación)."""
    if not m.get("pago_conocido"):
        return ""
    if m.get("cer_conocido"):
        return (f"\nCER final ya publicado ({m['extra']['cer_final']:,.4f}): el pago queda fijo en "
                f"${m['extra']['pago_final']:,.4f} por 100 VN y el bono se valúa como tasa fija. TIR nominal (TEA): "
                f"{_pct(m['tea'])}. Figura en la curva de tasa fija.")
    if "tipo_cambio_pago" in m["extra"]:
        return (f"\nA3500 de pago ya publicado ({m['extra']['tipo_cambio_pago']:,.4f}): el pago queda fijo en "
                f"${m['extra']['pago_final']:,.4f} por 100 VN y el bono se valúa como tasa fija. TNA: {_pct(m['tna'])} | "
                f"TIR nominal (TEA): {_pct(m['tea'])}. Figura en la curva de tasa fija.")
    return ("\nYa se publicó la TAMAR de toda la ventana: el pago final queda fijo en pesos y el bono se valúa como tasa "
            "fija (la TEA de arriba es nominal y definitiva). Figura en la curva de tasa fija.")


def _origen_a3500(operacion: date, a3500: tuple) -> tuple[float, str]:
    tc, fecha_tc, estimado = a3500
    return tc, (f"A3500 del {fecha_tc}, estimado: el del {operacion} todavía no se publicó" if estimado
                else f"A3500 del día de concertación, {fecha_tc}")


def _proximos(r: dict) -> str:
    return "; ".join(f"{fl.fecha}: {fl.renta:.4f} + {fl.amortizacion:g} = {fl.total:.4f}" for fl in r["flujos"][:4])


def _dolar_linked_bullet(f: dict, r: dict, operacion: date, a3500: tuple) -> str:
    tc, origen_tc = _origen_a3500(operacion, a3500)
    pago = f" | tipo de cambio de pago: {f['tipo_cambio_pago']}" if f.get("tipo_cambio_pago") else ""
    return (
        f"Precio en dólares: {r['precio_usd']:.4f} por 100 VN (precio en pesos / {tc:,.4f}, {origen_tc})\n"
        f"Paga 100 dólares por 100 VN al vencimiento, en pesos{pago}\n"
        f"Plazo residual: {r['plazo_residual']} días | duration: {r['duration']:.4f}\n"
        f"TNA: {_pct(r['tna'])} | TIR (TEA): {_pct(r['tea'])} | TEM (30 días): {_pct(r['tem'])} (en dólares, actual/365)"
    )


def _tamar_capitalizable(f: dict, r: dict, d: dict) -> str:
    return (
        f"TAMAR del bono: {_pct(r['tamar_bono'])} (promedio del {d['inicio']} al {d['fin']}: "
        f"{len(d['conocidas'])} días publicados y {d['a_estimar']} estimados) + margen {_pct(f['margen'])} → "
        f"TEM {_pct(r['tem_bono'])} (base 32 días)\n"
        f"Pago final teórico: {r['pago_final']:.4f} por 100 VN | plazo residual: {r['plazo_residual']} días | "
        f"duration: {r['duration']:.4f}\n"
        f"TNA: {_pct(r['tna'])} | TEA (TIR): {_pct(r['tea'])} | TEM (30 días): {_pct(r['tem_30'])} | "
        f"TNA semestral: {_pct(r['tna_semestral'])}\n"
        f"TNA 30 d: {_pct(r['tna_30'])} | TAMAR de referencia: {_pct(r['tamar_referencia'])} (últimos 5 días hábiles "
        f"publicados, {d['ultimas'][0]} a {d['ultimas'][1]}; estima los días que faltan) | "
        f"spread sobre TAMAR (TNA 30 d − referencia): {_pct(r['spread'])}"
    )


def _tasa_fija_capitalizable(f: dict, r: dict) -> str:
    return (
        f"Pago final: {r['pago_final']:.4f} por 100 VN (cupón de licitación {_pct(f['cupon'])} mensual capitalizable, emitida el {f['emision']})\n"
        f"Plazo residual: {r['plazo_residual']} días ({r['meses_al_vencimiento']:.2f} meses 30/360) | "
        f"duration: {r['duration']:.4f}\n"
        f"TNA: {_pct(r['tna'])} | TEA (TIR): {_pct(r['tea'])} | TEM (30 días): {_pct(r['tem'])}"
    )


def _tasa_fija_descuento(r: dict) -> str:
    return (
        f"Letra a descuento: paga 100 por 100 VN al vencimiento\n"
        f"Plazo residual: {r['plazo_residual']} días | duration: {r['duration']:.4f}\n"
        f"TNA: {_pct(r['tna'])} | TEA (TIR): {_pct(r['tea'])} | TEM (30 días): {_pct(r['tem'])} | "
        f"tasa de descuento: {_pct(r['tasa_descuento'])}"
    )


def _dolar_linked_cupon(f: dict, r: dict, operacion: date, a3500: tuple) -> str:
    tc, origen_tc = _origen_a3500(operacion, a3500)
    pago = f" | tipo de cambio de pago: {f['tipo_cambio_pago']}" if f.get("tipo_cambio_pago") else ""
    return (
        f"Precio en dólares: {r['precio_usd']:.4f} por 100 VN (precio en pesos / {tc:,.4f}, {origen_tc}){pago}\n"
        f"Residual: {r['residual']:g} | cupón {_pct(f['cupon'])} ({f['base']}) | interés corrido: {r['interes_corrido']:.4f} | "
        f"valor técnico: {r['valor_tecnico']:.4f} | paridad: {_pct(r['paridad'])}\n"
        f"TIR (TEA, en dólares): {_pct(r['tir'])} | TNA semestral: {_pct(r['tna_semestral'])} | TEM: {_pct(r['tem'])}\n"
        f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
        f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
        f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        f"Próximos flujos en dólares por 100 VN (renta + amortización, fechas corridas): {_proximos(r)}"
    )


def _tasa_fija_cupon(r: dict) -> str:
    return (
        f"Residual: {r['residual']:g} | interés corrido: {r['interes_corrido']:.4f} | "
        f"valor técnico: {r['valor_tecnico']:.4f}\n"
        f"Paridad: {_pct(r['paridad'])}\n"
        f"TIR: {_pct(r['tir_real'])} | TNA semestral: {_pct(r['tna_semestral'])} | TNA 30 d: {_pct(r['tna_30'])} | "
        f"TEM: {_pct(r['tem'])}\n"
        f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
        f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
        f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        f"Próximos flujos por 100 VN (renta + amortización, fechas corridas): {_proximos(r)}"
    )


def _cer_cero_cupon(f: dict, r: dict, inflacion_mensual: float | None) -> str:
    if inflacion_mensual is None:
        inflacion, mes_inflacion = mercado.ultima_inflacion()
        origen_inflacion = f"{mes_inflacion}, INDEC vía BCRA"
    else:
        inflacion, origen_inflacion = inflacion_mensual / 100, "indicada"
    return (
        f"Plazo residual: {r['plazo_residual']} días | ratio: {r['ratio']:,.4f} | valor técnico: {r['valor_tecnico']:,.4f} "
        f"(100 × ratio, en pesos) | paridad: {_pct(r['paridad'])}\n"
        f"Fecha CER final (10.º día hábil anterior al vencimiento): {mercado.fecha_cer(f['vencimiento'])}\n"
        f"TNA real: {_pct(r['tna_real'])} | TEA real (TIR): {_pct(r['tea_real'])}\n"
        f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
        f"convexidad: {r['convexidad']:.4f}\n"
        f"Carry mensual: {_pct(cer.carry_mensual(inflacion, r['tna_real']))} (inflación {_pct(inflacion)} "
        f"[{origen_inflacion}] + TNA / 12)"
    )


def _cer_cupon(r: dict) -> str:
    return (
        f"Ratio: {r['ratio']:,.4f} | residual: {r['residual']:g} | interés corrido: {r['interes_corrido']:.4f} | "
        f"valor técnico: {r['valor_tecnico']:.4f}\n"
        f"Precio real (precio / ratio): {r['precio_dirty_real']:.4f} | paridad: {_pct(r['paridad'])}\n"
        f"TIR real: {_pct(r['tir_real'])} | TNA semestral: {_pct(r['tna_semestral'])} | TNA 30 d: {_pct(r['tna_30'])} | "
        f"TEM: {_pct(r['tem'])}\n"
        f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
        f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
        f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        f"Próximos flujos reales por 100 VN (renta + amortización, fechas corridas): {_proximos(r)}"
    )


# Treasuries de EE. UU. (constant maturity, FRED): serie -> plazo en años
TREASURIES = {"DGS1MO": 1 / 12, "DGS3MO": 0.25, "DGS6MO": 0.5, "DGS1": 1, "DGS2": 2, "DGS3": 3, "DGS5": 5,
              "DGS7": 7, "DGS10": 10, "DGS20": 20, "DGS30": 30}
SUFIJOS_USD = {"MEP": "D", "cable": "C"}


def _treasuries(fecha: date) -> tuple[list[tuple[float, float]], str]:
    """Curva de Treasuries al último dato disponible hasta 'fecha': [(años, tasa)] y la fecha del dato."""
    curva, fechas = [], []
    for serie, plazo in TREASURIES.items():
        datos = fred.obtener_serie(serie, (fecha - timedelta(days=15)).isoformat(), fecha.isoformat())
        if datos:
            curva.append((plazo, datos[-1]["valor"] / 100))
            fechas.append(datos[-1]["fecha"])
    if len(curva) < 2:
        raise ErrorAPI("FRED no devolvió la curva de Treasuries.")
    return curva, max(fechas)


def _hard_dollar(f: dict, precio: float | None, fecha: date | None, liquidacion: date, operacion: date) -> str:
    """Bono en dólares: TIR con precio MEP y cable, spreads contra Treasuries y entre leyes, dólar implícito."""
    base = f["ticker"].upper()

    def calcular(ficha_, p):
        return metricas.calculadora(ficha_, liquidacion, operacion)(p)["detalle"]

    precios, faltantes = {}, []
    if precio is not None:
        precios["MEP"] = (precio, "precio indicado")
    else:
        for nombre, sufijo in SUFIJOS_USD.items():
            try:
                precios[nombre] = mercado.precio(base + sufijo, fecha)
            except (ErrorAPI, ValueError) as e:
                faltantes.append(f"{nombre} ({base + sufijo}): {e}")
    if not precios:
        raise ErrorAPI("no hay precio en dólares. " + " | ".join(faltantes))
    resultados = {nombre: calcular(f, p) for nombre, (p, _) in precios.items()}

    try:
        curva, fecha_ust = _treasuries(fecha or date.today())
    except ErrorAPI as e:
        curva, fecha_ust = None, str(e)
    par = fichas.ficha(f["par"], "hard_dollar") if f.get("par") else None

    r0 = next(iter(resultados.values()))
    proximos = "; ".join(f"{fl.fecha}: {fl.renta:.4f} + {fl.amortizacion:g} = {fl.total:.4f}" for fl in r0["flujos"][:4])
    texto = (
        f"{base} ({f['tipo']}, ley {f['ley']}, vence {f['vencimiento']}) – calculadora de Finianz\n"
        f"Liquidación {liquidacion} (T+{mercado.PLAZO_LIQUIDACION}) | residual: {r0['residual']:g} | cupón vigente: "
        f"{_pct(r0['tasa_vigente'])} | interés corrido: {r0['interes_corrido']:.4f} | valor técnico: {r0['valor_tecnico']:.4f}\n"
        f"Próximos flujos por 100 VN en USD (renta + amortización, fechas corridas): {proximos}\n"
        f"TNA: nominal anual con capitalización semestral, base 30/360; TIR = TEA. Precios en dólares por 100 VN original "
        f"(el clean, por 100 de residual).\n"
    )
    for nombre, r in resultados.items():
        p, origen = precios[nombre]
        texto += (
            f"\n— Con precio {nombre} ({base + SUFIJOS_USD[nombre] if origen != 'precio indicado' else 'indicado'}): "
            f"{p:,.2f} ({origen}) —\n"
            f"Precio clean (por 100 de residual): {r['precio_clean_residual']:.4f} | paridad: {_pct(r['paridad'])}\n"
            f"TNA (semestral 30/360): {_pct(r['tir'])} | TIR (TEA): {_pct(r['tea'])}\n"
            f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
            f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
            f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        )
        if curva:
            ust = hard_dollar.interpolar(curva, r["duration"])
            texto += (f"Spread contra Treasuries (sobre la TNA semestral): {(r['tir'] - ust) * 10000:,.0f} pb (Treasury interpolado a "
                      f"{r['duration']:.2f} años: {_pct(ust)}, FRED al {fecha_ust})\n")
        if par and precio is None:
            try:
                p_par, _ = mercado.precio(par["ticker"].upper() + SUFIJOS_USD[nombre], fecha)
                tir_par = calcular(par, p_par)["tir"]
                ny, ar = (r["tir"], tir_par) if f["ley"] == "NY" else (tir_par, r["tir"])
                texto += (f"Spread ley NY − ley AR (sobre la TNA semestral): {(ny - ar) * 10000:,.0f} pb ({par['ticker'].upper()} a "
                          f"{p_par:,.2f}: TNA {_pct(tir_par)})\n")
            except (ErrorAPI, ValueError) as e:
                texto += f"Spread ley NY − ley AR: sin dato ({e})\n"
    if not curva:
        texto += f"\nSpread contra Treasuries: sin dato ({fecha_ust})\n"
    if precio is None:
        try:
            pesos, _ = mercado.precio(base, fecha)
            implicitos = " | ".join(f"{'MEP' if n == 'MEP' else 'CCL'}: {pesos / p:,.2f}" for n, (p, _) in precios.items())
            texto += f"\nDólar implícito ({base} en pesos a {pesos:,.2f} / precio en dólares): {implicitos}\n"
        except (ErrorAPI, ValueError) as e:
            texto += f"\nDólar implícito: sin dato ({e})\n"
    for faltante in faltantes:
        texto += f"\nSin precio {faltante}"
    if not f.get("revisado"):
        texto += "\nAVISO: la ficha técnica todavía no fue revisada por Agustin; tomá el resultado como preliminar."
    return texto.rstrip("\n")


CALCULAR_BONO = {
    "name": "calcular_bono",
    "description": (
        "Calculadora propia de bonos CER, tasa fija y TAMAR. CER cero cupón (Boncer TZX, LeCER X y la parte CER de los duales TXM): plazo "
        "residual, duration, ratio, TNA real, TEA real (TIR) y carry mensual. Con cupón (TX28, TX31): valor técnico, "
        "paridad, TIR real, TNA semestral y 30 d, TEM, duration, duration modificada, convexidad, PV01, current yield "
        "y cash yield. Tasa fija: Lecap/Boncap capitalizables (S30N6, T15E7, S29E7, T30A7, T31Y7, T30J7: pago final, "
        "TNA, TEA, TEM, duration) y Bonte con cupón (TY30P: como los CER con cupón, en pesos). Sin precio, usa el precio "
        "de mercado: en vivo, o el cierre de 'fecha' si se indica. Cálculos en T+1. TAMAR capitalizables (TMF27, TML27, TMG27, "
        "TMF28, TMG28 y el dual TTD26): TAMAR proyectada, TEM, pago final teórico, TNA, TEA, TNA 30 d y spread sobre TAMAR. "
        "Los duales CER/TAMAR (TXMJ8, TXMD8, TXMJ9, TXMD9, TXMJ0) se devuelven calculados como CER y como TAMAR. "
        "Dollar linked del Tesoro (D30N6, D15E7, D31M7, TZV27, TZV28, TZVD8): precio en dólares con el A3500 del día "
        "de concertación, TNA, TIR y TEM en dólares (actual/365), duration. Dollar linked con cupón (ONs, si hay fichas "
        "cargadas): TIR en dólares, paridad, duration. Letras a descuento (si hay fichas): TNA, TEA, TEM y tasa de descuento. "
        "Hard dollar (Bonares AL29, AL30, AL35, AE38, AL41 y Globales GD29, GD30, GD35, GD38, GD41, GD46; también "
        "con el ticker en dólares, ej.: AL30D, GD35C): TNA semestral 30/360 y TIR (TEA) con precio MEP y cable, precio clean por 100 de residual, duration, paridad, "
        "spread contra Treasuries, spread ley NY − ley AR y dólar implícito MEP y CCL; 'precio' es en dólares."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Ticker en pesos, ej.: TZX27, TZXD7, X29E7"},
            "precio": {"type": "number", "description": "Precio por 100 VN, si se quiere calcular con otro precio (opcional)"},
            "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD para usar el cierre de ese día (opcional)"},
            "inflacion_mensual": {"type": "number", "description": "Inflación mensual en % para el carry (opcional; por defecto, el último dato del INDEC)"},
            "fuente_inflacion": {"type": "string", "description": "Duales CER/TAMAR: con qué inflación proyectar la pata CER: rem, breakeven, escenario:<nombre>, mensual:<tasa> o camino:<meses> (por defecto, rem si está cargado)"},
            "fuente_tamar": {"type": "string", "description": "Duales: con qué TAMAR proyectar la pata TAMAR: actual, rem, tna:<tasa>, camino:<meses> o escenario:<nombre> (por defecto, actual)"},
        },
        "required": ["ticker"],
    },
}


HERRAMIENTAS = [
    (CALCULAR_BONO, calcular_bono),
]
