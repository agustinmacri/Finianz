"""Datos de mercado de los bonos: precios (PPI), CER, A3500, TAMAR y feriados, desde la base propia (datos/) y,
si falta algo, desde las fuentes (BCRA, PPI). Es la parte de renta_fija que sale a buscar datos; las calculadoras
(renta_fija/calculadoras/) no traen nada de afuera.

Lo usan las herramientas del agente (tools/), el panel web (web/) y renta_fija/metricas.py.
"""
from datetime import date, timedelta

import config
from admin_datos import feriados
from admin_datos import precios as db_precios
from admin_datos import series as db_series
from carga_datos import feriados as carga_feriados
from carga_datos import precios as carga_precios
from carga_datos import series as carga_series
from conexiones import bcra, ppi
from conexiones.http import ErrorAPI
from renta_fija.calculadoras import cer, tamar

PLAZO_LIQUIDACION = 1          # T+1: precios y cálculos a la fecha de liquidación, salvo que se indique otra cosa
CALENDARIO_HABILES = "BYMA"    # días hábiles del rezago del CER y de las fechas de pago (decisión de Agustin, 13/11/2026)


def contexto(fecha: date | None = None) -> tuple[date, date, date | None]:
    """(operación, liquidación T+1, fecha de precios): hoy con precios en vivo, o el cierre de 'fecha'."""
    operacion = fecha or date.today()
    asegurar_feriados(operacion)
    liquidacion = feriados.sumar_dias_habiles(operacion, PLAZO_LIQUIDACION, CALENDARIO_HABILES)
    return operacion, liquidacion, (operacion if fecha else None)


def asegurar_feriados(*fechas: date):
    rango = feriados.rango_cargado()
    if not rango or any(not rango[0] <= f.year <= rango[1] for f in fechas):
        anios = [f.year for f in fechas]
        carga_feriados.cargar(desde=min(anios + [config.FERIADOS_DESDE] + ([rango[0]] if rango else [])),
                              hasta=max(anios + [date.today().year + config.FERIADOS_ANIOS_ADELANTE]))


def cer_de(fecha: date) -> float:
    """CER de una fecha exacta, de la base propia (datos/series.db). Si falta, la actualiza desde el BCRA."""
    valor = db_series.valor("CER", fecha)
    if valor is None:
        carga_series.actualizar("CER")
        valor = db_series.valor("CER", fecha)
    if valor is None:
        raise ErrorAPI(f"no hay CER del {fecha}: no está en la base propia ni lo publicó el BCRA todavía.")
    return valor


_cer_refrescado = [0.0]          # momento del último intento de traer CER nuevo del BCRA (una vez por hora)


def publicacion_cer(fecha_cer: date) -> date:
    """Cuándo se conoció el CER de una fecha. El BCRA arma el CER del 16 de un mes al 15 del siguiente con el IPC del
    mes anterior a ese período, así que se conoce el día que el INDEC publica ese IPC (en el mes en que empieza el
    período, antes del 16). Fecha del calendario de publicaciones (código IPC) si está cargada; si no, el 15."""
    inicio = fecha_cer if fecha_cer.day >= 16 else (fecha_cer.replace(day=1) - timedelta(days=1))
    desde, hasta = date(inicio.year, inicio.month, 1), date(inicio.year, inicio.month, 16)
    try:
        from admin_datos import publicaciones
        if publicaciones.hay_datos():
            ipc = [p for p in publicaciones.entre(desde, hasta, "AR", "baja") if p.get("codigo") == "IPC"]
            if ipc:
                return date.fromisoformat(ipc[0]["fecha"])
    except Exception:
        pass
    return date(inicio.year, inicio.month, 15)


def cer_final_conocido(fecha_pago: date, operacion: date | None = None) -> float | None:
    """CER que ajusta un pago (10.º día hábil anterior) si ya se conocía el día de 'operacion' (hoy, si no se
    indica); si no, None. Desde que se conoce, el pago queda fijo en pesos y el bono es de tasa fija (decisión de
    Agustin, 26/11/2026). Para una fecha pasada en la que todavía no se conocía, sigue siendo un bono CER aunque hoy
    el dato ya esté en la base."""
    import time
    operacion = operacion or date.today()
    fecha = feriados.sumar_dias_habiles(fecha_pago, -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    if publicacion_cer(fecha) > operacion:
        return None
    valor = db_series.valor("CER", fecha)
    if valor is None and time.time() - _cer_refrescado[0] > 3600:
        _cer_refrescado[0] = time.time()
        try:
            carga_series.actualizar("CER")
        except ErrorAPI:
            pass
        valor = db_series.valor("CER", fecha)
    return valor


REZAGO_TC_PAGO_DL = 3            # Lelink del Tesoro: A3500 del 3.er día hábil anterior al pago (resoluciones conjuntas)
_a3500_refrescado = [0.0]


def a3500_pago_conocido(f: dict, operacion: date | None = None) -> float | None:
    """A3500 con el que paga un dollar linked al vencimiento (3.er día hábil anterior al pago, o el rezago de la ficha
    en 'rezago_tipo_cambio'), si ya se conocía el día de 'operacion' (hoy, si no se indica); si no, None."""
    import time
    rezago = int(f.get("rezago_tipo_cambio", REZAGO_TC_PAGO_DL))
    fecha = feriados.sumar_dias_habiles(f["vencimiento"], -rezago, CALENDARIO_HABILES)
    if fecha > (operacion or date.today()):
        return None
    valor = db_series.valor("A3500", fecha)
    if valor is None and date.today() >= fecha and time.time() - _a3500_refrescado[0] > 3600:
        _a3500_refrescado[0] = time.time()
        try:
            carga_series.actualizar("A3500")
        except ErrorAPI:
            pass
        valor = db_series.valor("A3500", fecha)
    return valor


def tipo_cambio_inicial(f: dict) -> float:
    """Escala de la pata TAMAR de un dual TAMAR/dollar linked (TMVE8): el VN está en dólares y la pata TAMAR
    capitaliza el VN pasado a pesos al tipo de cambio inicial (A3500 del día hábil anterior a la licitación). Con
    'tipo_cambio_inicial' (número) o 'fecha_tipo_cambio_inicial' (fecha del A3500) en la ficha; sin ellos, 1 (los
    TAMAR comunes, con VN en pesos)."""
    if f.get("tipo_cambio_inicial"):
        return float(f["tipo_cambio_inicial"])
    if f.get("fecha_tipo_cambio_inicial"):
        fecha = f["fecha_tipo_cambio_inicial"]
        valor = db_series.valor("A3500", fecha)
        if valor is None:
            try:
                carga_series.actualizar("A3500")
            except ErrorAPI:
                pass
            valor = db_series.valor("A3500", fecha)
        if valor is None:
            raise ValueError(f"{f['ticker']}: no hay A3500 del {fecha:%d/%m/%Y} (tipo de cambio inicial) en la base.")
        return valor
    return 1.0


def ultima_inflacion() -> tuple[float, str]:
    """Último dato de inflación mensual conocido (INDEC vía BCRA): (fracción, mes)."""
    candidatas = [v for v in bcra.buscar_variables("inflacion mensual")
                  if "inflacion mensual" in bcra.normalizar(v["descripcion"])]
    if not candidatas:
        raise ErrorAPI("no se encontró la inflación mensual en el BCRA.")
    v = candidatas[0]
    return float(v["ultimo_valor"]) / 100, str(v["ultima_fecha"])[:7]


def precio(ticker: str, fecha: date | None) -> tuple[float, str]:
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


def datos_cer(f: dict, liquidacion: date) -> tuple[str, dict, float]:
    """CER corriente (10.º día hábil anterior a la liquidación) y CER inicial (10.º día hábil anterior a la
    emisión), ambos de la base propia de series: las fichas no traen valores de CER."""
    fecha_cer_corriente = feriados.sumar_dias_habiles(liquidacion, -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    cer_corriente = cer_de(fecha_cer_corriente)
    asegurar_feriados(f["emision"])
    fecha_base = feriados.sumar_dias_habiles(f["emision"], -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    f = dict(f, cer_inicial=cer_de(fecha_base))
    texto = (f"Base (CER inicial): {f['cer_inicial']:,.4f} (al {fecha_base}, 10.º día hábil anterior a la emisión "
             f"del {f['emision']}) | CER corriente: {cer_corriente:,.5f} "
             f"(al {fecha_cer_corriente}, 10.º día hábil anterior a la liquidación)\n")
    return texto, f, cer_corriente


def a3500(operacion: date) -> tuple[float, date, bool]:
    """A3500 del día de concertación. Si todavía no se publicó (sale alrededor de las 15 h), se estima con el
    del último día hábil anterior. Devuelve (valor, fecha del dato, estimado)."""
    valor = db_series.valor("A3500", operacion)
    if valor is None:
        carga_series.actualizar("A3500")
        valor = db_series.valor("A3500", operacion)
    if valor is not None:
        return valor, operacion, False
    anteriores = db_series.entre("A3500", (operacion - timedelta(days=10)).isoformat(),
                                 (operacion - timedelta(days=1)).isoformat())
    if not anteriores:
        raise ErrorAPI(f"no hay A3500 del {operacion} ni de los días anteriores en la base ni en el BCRA.")
    return anteriores[-1]["valor"], date.fromisoformat(anteriores[-1]["fecha"]), True


def datos_tamar(f: dict, corte: date) -> dict:
    """TAMAR del bono (ventana con la parte estimada) y TAMAR de referencia, con lo publicado hasta 'corte'.

    Ventana: del 10.º día hábil anterior a la emisión al 10.º anterior al vencimiento. Los días hábiles
    de la ventana posteriores al último dato publicado se estiman con el promedio de los últimos 5.
    """
    asegurar_feriados(f["emision"], f["vencimiento"], corte)
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
            "desde_estimar": desde_estimar,
            "tamar_bono": tamar.tamar_del_bono(conocidas, a_estimar, referencia),
            "ultimas": (ultimas[0]["fecha"], ultimas[-1]["fecha"])}
