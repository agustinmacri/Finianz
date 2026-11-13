"""Calculadora de bonos propia (CER, tasa fija y TAMAR), con las definiciones de Agustin (docs/convenciones-renta-fija.md).

Arma el cálculo con piezas de cada capa:
- la ficha técnica del bono (renta_fija/fichas/*.toml, vía renta_fija/leer_fichas.py);
- el precio (PPI en vivo, o el cierre guardado en la base propia para una fecha pasada);
- el CER y la TAMAR (base propia de series, cargada desde el BCRA), la inflación del BCRA y los días hábiles (base de feriados);
- la calculadora de la familia (renta_fija/calculadoras/).
Ningún número sale de cálculos externos: de afuera vienen solo datos.
"""
from datetime import date, timedelta

import config
from admin_datos import feriados
from admin_datos import precios as db_precios
from admin_datos import series as db_series
from carga_datos import feriados as carga_feriados
from carga_datos import precios as carga_precios
from carga_datos import series as carga_series
from conexiones import bcra, fred, ppi
from conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas
from renta_fija.calculadoras import cer, cer_cupon, hard_dollar, tamar, tasa_fija

PLAZO_LIQUIDACION = 1          # T+1: precios y cálculos a la fecha de liquidación, salvo que se indique otra cosa
CALENDARIO_HABILES = "BYMA"    # días hábiles del rezago del CER y de las fechas de pago (decisión de Agustin, 13/11/2026)


def _asegurar_feriados(*fechas: date):
    rango = feriados.rango_cargado()
    if not rango or any(not rango[0] <= f.year <= rango[1] for f in fechas):
        anios = [f.year for f in fechas]
        carga_feriados.cargar(desde=min(anios + [config.FERIADOS_DESDE] + ([rango[0]] if rango else [])),
                              hasta=max(anios + [date.today().year + config.FERIADOS_ANIOS_ADELANTE]))


def _cer(fecha: date) -> float:
    """CER de una fecha exacta, de la base propia (datos/series.db). Si falta, la actualiza desde el BCRA."""
    valor = db_series.valor("CER", fecha)
    if valor is None:
        carga_series.actualizar("CER")
        valor = db_series.valor("CER", fecha)
    if valor is None:
        raise ErrorAPI(f"no hay CER del {fecha}: no está en la base propia ni lo publicó el BCRA todavía.")
    return valor


def _ultima_inflacion() -> tuple[float, str]:
    """Último dato de inflación mensual conocido (INDEC vía BCRA): (fracción, mes)."""
    candidatas = [v for v in bcra.buscar_variables("inflacion mensual")
                  if "inflacion mensual" in bcra.normalizar(v["descripcion"])]
    if not candidatas:
        raise ErrorAPI("no se encontró la inflación mensual en el BCRA.")
    v = candidatas[0]
    return float(v["ultimo_valor"]) / 100, str(v["ultima_fecha"])[:7]


def _precio(ticker: str, fecha: date | None) -> tuple[float, str]:
    """Precio por 100 VN y de dónde salió: en vivo (hoy) o el cierre guardado de una fecha."""
    plazo = config.PPI_PLAZO
    if fecha is None:
        datos = carga_precios.registrar(ticker)
        p = ppi.precio_actual(ticker, datos["tipo"], plazo)
        return p["price"], f"PPI en vivo, {str(p.get('date'))[:16]}"
    carga_precios.actualizar(ticker, plazo)
    cierre = db_precios.entre(ticker, plazo, fecha.isoformat(), fecha.isoformat())
    if not cierre:
        raise ValueError(f"no hay cierre guardado de {ticker} el {fecha} (¿fue día hábil?).")
    return cierre[0]["cierre"], f"cierre del {fecha} (base propia, fuente PPI)"


def _pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def calcular_bono(ticker: str, precio: float | None = None, fecha: str | None = None,
                  inflacion_mensual: float | None = None) -> str:
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
        _asegurar_feriados(operacion, f["vencimiento"])
        liquidacion = feriados.sumar_dias_habiles(operacion, PLAZO_LIQUIDACION, "BYMA")
        if liquidacion >= f["vencimiento"]:
            return f"{ticker.upper()} vence el {f['vencimiento']}: no quedan flujos para la liquidación del {liquidacion}."
        if f["familia"] == "hard_dollar":
            return _hard_dollar(f, precio, date.fromisoformat(fecha) if fecha else None, liquidacion)
        if precio is None:
            precio, origen = _precio(ticker, date.fromisoformat(fecha) if fecha else None)
        else:
            origen = "precio indicado"
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"

    encabezado = (
        f"{ticker.upper()} ({f['tipo']}, vence {f['vencimiento']}) – calculadora de Finianz\n"
        f"Precio: {precio:,.2f} por 100 VN ({origen}) | liquidación {liquidacion} (T+{PLAZO_LIQUIDACION})\n"
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
    return encabezado + "\n".join(secciones) + avisos


NOMBRE_FAMILIA = {
    "cer_cero_cupon": "CER", "cer_cupon": "CER", "tasa_fija_capitalizable": "tasa fija",
    "tasa_fija_cupon": "tasa fija", "tamar_capitalizable": "TAMAR",
}


def _calcular_ficha(f: dict, precio: float, liquidacion: date, operacion: date,
                    inflacion_mensual: float | None) -> str:
    if f["familia"].startswith("cer"):
        texto_cer, f, cer_corriente = _datos_cer(f, liquidacion)
        if f["familia"] == "cer_cupon":
            return texto_cer + _cer_cupon(f, precio, cer_corriente, liquidacion)
        return texto_cer + _cer_cero_cupon(f, precio, cer_corriente, liquidacion, inflacion_mensual)
    if f["familia"] == "tasa_fija_capitalizable":
        return _tasa_fija_capitalizable(f, precio, liquidacion)
    if f["familia"] == "tamar_capitalizable":
        return _tamar_capitalizable(f, precio, liquidacion, operacion)
    return _tasa_fija_cupon(f, precio, liquidacion)


def _datos_cer(f: dict, liquidacion: date) -> tuple[str, dict, float]:
    """CER corriente (10.º día hábil anterior a la liquidación) y CER inicial (10.º día hábil anterior a la
    emisión), ambos de la base propia de series: las fichas no traen valores de CER."""
    fecha_cer_corriente = feriados.sumar_dias_habiles(liquidacion, -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    cer_corriente = _cer(fecha_cer_corriente)
    _asegurar_feriados(f["emision"])
    fecha_base = feriados.sumar_dias_habiles(f["emision"], -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    f = dict(f, cer_inicial=_cer(fecha_base))
    texto = (f"Base (CER inicial): {f['cer_inicial']:,.4f} (al {fecha_base}, 10.º día hábil anterior a la emisión "
             f"del {f['emision']}) | CER corriente: {cer_corriente:,.5f} "
             f"(al {fecha_cer_corriente}, 10.º día hábil anterior a la liquidación)\n")
    return texto, f, cer_corriente


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


def _hard_dollar(f: dict, precio: float | None, fecha: date | None, liquidacion: date) -> str:
    """Bono en dólares: TIR con precio MEP y cable, spreads contra Treasuries y entre leyes, dólar implícito."""
    base = f["ticker"].upper()
    ajustar = lambda d: feriados.proximo_dia_habil(d, CALENDARIO_HABILES)

    def calcular(ficha_, p):
        return hard_dollar.calcular(p, liquidacion, ficha_["pagos"], ficha_["tramos"], ficha_["emision"], ajustar)

    precios, faltantes = {}, []
    if precio is not None:
        precios["MEP"] = (precio, "precio indicado")
    else:
        for nombre, sufijo in SUFIJOS_USD.items():
            try:
                precios[nombre] = _precio(base + sufijo, fecha)
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
        f"Liquidación {liquidacion} (T+{PLAZO_LIQUIDACION}) | residual: {r0['residual']:g} | cupón vigente: "
        f"{_pct(r0['tasa_vigente'])} | interés corrido: {r0['interes_corrido']:.4f} | valor técnico: {r0['valor_tecnico']:.4f}\n"
        f"Próximos flujos por 100 VN en USD (renta + amortización, fechas corridas): {proximos}\n"
        f"TIR: nominal anual semestral, base 30/360. Precios por 100 VN en dólares.\n"
    )
    for nombre, r in resultados.items():
        p, origen = precios[nombre]
        texto += (
            f"\n— Con precio {nombre} ({base + SUFIJOS_USD[nombre] if origen != 'precio indicado' else 'indicado'}): "
            f"{p:,.2f} ({origen}) —\n"
            f"Precio clean: {r['precio_clean']:.4f} | paridad: {_pct(r['paridad'])}\n"
            f"TIR: {_pct(r['tir'])} | TEA: {_pct(r['tea'])}\n"
            f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
            f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
            f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        )
        if curva:
            ust = hard_dollar.interpolar(curva, r["duration"])
            texto += (f"Spread contra Treasuries: {(r['tir'] - ust) * 10000:,.0f} pb (Treasury interpolado a "
                      f"{r['duration']:.2f} años: {_pct(ust)}, FRED al {fecha_ust})\n")
        if par and precio is None:
            try:
                p_par, _ = _precio(par["ticker"].upper() + SUFIJOS_USD[nombre], fecha)
                tir_par = calcular(par, p_par)["tir"]
                ny, ar = (r["tir"], tir_par) if f["ley"] == "NY" else (tir_par, r["tir"])
                texto += (f"Spread ley NY − ley AR: {(ny - ar) * 10000:,.0f} pb ({par['ticker'].upper()} a "
                          f"{p_par:,.2f}: TIR {_pct(tir_par)})\n")
            except (ErrorAPI, ValueError) as e:
                texto += f"Spread ley NY − ley AR: sin dato ({e})\n"
    if not curva:
        texto += f"\nSpread contra Treasuries: sin dato ({fecha_ust})\n"
    if precio is None:
        try:
            pesos, origen_pesos = _precio(base, fecha)
            implicitos = " | ".join(f"{'MEP' if n == 'MEP' else 'CCL'}: {pesos / p:,.2f}" for n, (p, _) in precios.items())
            texto += f"\nDólar implícito ({base} en pesos a {pesos:,.2f} / precio en dólares): {implicitos}\n"
        except (ErrorAPI, ValueError) as e:
            texto += f"\nDólar implícito: sin dato ({e})\n"
    for faltante in faltantes:
        texto += f"\nSin precio {faltante}"
    if not f.get("revisado"):
        texto += "\nAVISO: la ficha técnica todavía no fue revisada por Agustin; tomá el resultado como preliminar."
    return texto.rstrip("\n")


def _datos_tamar(f: dict, corte: date) -> dict:
    """TAMAR del bono (ventana con la parte estimada) y TAMAR de referencia, con lo publicado hasta 'corte'.

    Ventana: del 10.º día hábil anterior a la emisión al 10.º anterior al vencimiento. Los días hábiles
    de la ventana posteriores al último dato publicado se estiman con el promedio de los últimos 5.
    """
    _asegurar_feriados(f["emision"], f["vencimiento"], corte)
    rango = db_series.rango("TAMAR")
    if not rango or date.fromisoformat(rango[1]) < feriados.sumar_dias_habiles(corte, -2, CALENDARIO_HABILES):
        carga_series.actualizar("TAMAR")           # faltan datos recientes: se piden al BCRA
    publicadas = db_series.entre("TAMAR", None, corte.isoformat())
    if len(publicadas) < tamar.DIAS_ESTIMACION:
        raise ErrorAPI("no hay suficientes datos de TAMAR en la base propia ni en el BCRA.")
    inicio = feriados.sumar_dias_habiles(f["emision"], -tamar.REZAGO_HABILES, CALENDARIO_HABILES)
    fin = feriados.sumar_dias_habiles(f["vencimiento"], -tamar.REZAGO_HABILES, CALENDARIO_HABILES)
    ultimas = publicadas[-tamar.DIAS_ESTIMACION:]
    referencia = sum(p["valor"] for p in ultimas) / len(ultimas) / 100
    ultima_fecha = date.fromisoformat(publicadas[-1]["fecha"])
    conocidas = [p["valor"] / 100 for p in publicadas if inicio.isoformat() <= p["fecha"] <= fin.isoformat()]
    desde_estimar = max(inicio, ultima_fecha + timedelta(days=1))
    a_estimar = len(feriados.dias_habiles_entre(desde_estimar, fin, CALENDARIO_HABILES))
    return {"inicio": inicio, "fin": fin, "conocidas": conocidas, "a_estimar": a_estimar, "referencia": referencia,
            "tamar_bono": tamar.tamar_del_bono(conocidas, a_estimar, referencia),
            "ultimas": (ultimas[0]["fecha"], ultimas[-1]["fecha"])}


def _tamar_capitalizable(f: dict, precio: float, liquidacion: date, operacion: date) -> str:
    d = _datos_tamar(f, operacion)
    r = tamar.calcular(precio, d["tamar_bono"], f["margen"], f["emision"], f["vencimiento"], liquidacion, d["referencia"])
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


def _tasa_fija_capitalizable(f: dict, precio: float, liquidacion: date) -> str:
    pf = tasa_fija.pago_final(f["tem"], f["emision"], f["vencimiento"])
    r = tasa_fija.calcular_capitalizable(precio, pf, liquidacion, f["vencimiento"])
    return (
        f"Pago final: {r['pago_final']:.4f} por 100 VN (TEM de emisión {_pct(f['tem'])}, emitida el {f['emision']})\n"
        f"Plazo residual: {r['plazo_residual']} días ({r['meses_al_vencimiento']:.2f} meses 30/360) | "
        f"duration: {r['duration']:.4f}\n"
        f"TNA: {_pct(r['tna'])} | TEA (TIR): {_pct(r['tea'])} | TEM (30 días): {_pct(r['tem'])}"
    )


def _tasa_fija_cupon(f: dict, precio: float, liquidacion: date) -> str:
    r = tasa_fija.calcular_cupon(precio, liquidacion, f["pagos"], f["cupon"], f["frecuencia"], f["emision"],
                                 lambda d: feriados.proximo_dia_habil(d, CALENDARIO_HABILES))
    proximos = "; ".join(f"{fl.fecha}: {fl.renta:.4f} + {fl.amortizacion:g} = {fl.total:.4f}" for fl in r["flujos"][:4])
    return (
        f"Residual: {r['residual']:g} | interés corrido: {r['interes_corrido']:.4f} | "
        f"valor técnico: {r['valor_tecnico']:.4f}\n"
        f"Precio clean: {r['precio_clean']:.4f} | paridad: {_pct(r['paridad'])}\n"
        f"TIR: {_pct(r['tir_real'])} | TNA semestral: {_pct(r['tna_semestral'])} | TNA 30 d: {_pct(r['tna_30'])} | "
        f"TEM: {_pct(r['tem'])}\n"
        f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
        f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
        f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        f"Próximos flujos por 100 VN (renta + amortización, fechas corridas): {proximos}"
    )


def _cer_cero_cupon(f: dict, precio: float, cer_corriente: float, liquidacion: date,
                    inflacion_mensual: float | None) -> str:
    if inflacion_mensual is None:
        inflacion, mes_inflacion = _ultima_inflacion()
        origen_inflacion = f"{mes_inflacion}, INDEC vía BCRA"
    else:
        inflacion, origen_inflacion = inflacion_mensual / 100, "indicada"
    fecha_cer_final = feriados.sumar_dias_habiles(f["vencimiento"], -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    r = cer.calcular(precio, f["cer_inicial"], cer_corriente, liquidacion, f["vencimiento"], inflacion)
    return (
        f"Plazo residual: {r['plazo_residual']} días | duration: {r['duration']:.4f} | ratio: {r['ratio']:,.4f}\n"
        f"Fecha CER final (10.º día hábil anterior al vencimiento): {fecha_cer_final}\n"
        f"TNA real: {_pct(r['tna_real'])} | TEA real (TIR): {_pct(r['tea_real'])}\n"
        f"Carry mensual: {_pct(r['carry_mensual'])} (inflación {_pct(inflacion)} [{origen_inflacion}] + TNA / 12)"
    )


def _cer_cupon(f: dict, precio: float, cer_corriente: float, liquidacion: date) -> str:
    r = cer_cupon.calcular(precio, f["cer_inicial"], cer_corriente, liquidacion, f["pagos"], f["cupon"],
                           f["frecuencia"], f["emision"],
                           lambda d: feriados.proximo_dia_habil(d, CALENDARIO_HABILES))
    proximos = "; ".join(f"{fl.fecha}: {fl.renta:.4f} + {fl.amortizacion:g} = {fl.total:.4f}" for fl in r["flujos"][:4])
    return (
        f"Ratio: {r['ratio']:,.4f} | residual: {r['residual']:g} | interés corrido: {r['interes_corrido']:.4f} | "
        f"valor técnico: {r['valor_tecnico']:.4f}\n"
        f"Precio dirty real: {r['precio_dirty_real']:.4f} | clean real: {r['precio_clean_real']:.4f} | "
        f"clean nominal: {r['precio_clean_nominal']:,.2f} | paridad: {_pct(r['paridad'])}\n"
        f"TIR real: {_pct(r['tir_real'])} | TNA semestral: {_pct(r['tna_semestral'])} | TNA 30 d: {_pct(r['tna_30'])} | "
        f"TEM: {_pct(r['tem'])}\n"
        f"Duration: {r['duration']:.4f} | duration modificada: {r['duration_modificada']:.4f} | "
        f"convexidad: {r['convexidad']:.4f} | PV01: {r['pv01']:.6f} | DD (100 pb): {r['dd']:.4f}\n"
        f"Current yield: {_pct(r['current_yield'])} | cash yield (12 meses): {_pct(r['cash_yield'])}\n"
        f"Próximos flujos reales por 100 VN (renta + amortización, fechas corridas): {proximos}"
    )


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
        "Hard dollar (Bonares AL29, AL30, AL35, AE38, AL41 y Globales GD29, GD30, GD35, GD38, GD41, GD46; también "
        "con el ticker en dólares, ej.: AL30D, GD35C): TIR semestral 30/360 con precio MEP y cable, duration, paridad, "
        "spread contra Treasuries, spread ley NY − ley AR y dólar implícito MEP y CCL; 'precio' es en dólares."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string", "description": "Ticker en pesos, ej.: TZX27, TZXD7, X29E7"},
            "precio": {"type": "number", "description": "Precio por 100 VN, si se quiere calcular con otro precio (opcional)"},
            "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD para usar el cierre de ese día (opcional)"},
            "inflacion_mensual": {"type": "number", "description": "Inflación mensual en % para el carry (opcional; por defecto, el último dato del INDEC)"},
        },
        "required": ["ticker"],
    },
}


HERRAMIENTAS = [
    (CALCULAR_BONO, calcular_bono),
]
