"""Calculadora de bonos propia, con las definiciones de Agustin (docs/convenciones-renta-fija.md).

Arma el cálculo con piezas de cada capa:
- la ficha técnica del bono (renta_fija/fichas/*.toml, vía renta_fija/leer_fichas.py);
- el precio (PPI en vivo, o el cierre guardado en la base propia para una fecha pasada);
- el CER y la inflación del BCRA, y los días hábiles (base de feriados);
- la calculadora de la familia (renta_fija/calculadoras/).
Ningún número sale de cálculos externos: de afuera vienen solo datos.
"""
from datetime import date, timedelta

import config
from admin_datos import feriados
from admin_datos import precios as db_precios
from carga_datos import feriados as carga_feriados
from carga_datos import precios as carga_precios
from conexiones import bcra, ppi
from conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas
from renta_fija.calculadoras import cer

PLAZO_LIQUIDACION = 1          # T+1: precios y cálculos a la fecha de liquidación, salvo que se indique otra cosa
CALENDARIO_HABILES = "AR"      # días hábiles del rezago del CER: calendario nacional oficial (decisión de Agustin)


def _asegurar_feriados(*fechas: date):
    rango = feriados.rango_cargado()
    if not rango or any(not rango[0] <= f.year <= rango[1] for f in fechas):
        carga_feriados.cargar(hasta=max([f.year for f in fechas] + [date.today().year + config.FERIADOS_ANIOS_ADELANTE]))


def _cer(fecha: date) -> float:
    """CER publicado por el BCRA para una fecha exacta (variable id 30, diaria)."""
    serie = bcra.obtener_serie(bcra.ID_CER, (fecha - timedelta(days=7)).isoformat(), fecha.isoformat())
    exacto = [d for d in serie if d["fecha"][:10] == fecha.isoformat()]
    if not exacto:
        raise ErrorAPI(f"el BCRA no tiene el CER del {fecha}.")
    return exacto[0]["valor"]


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
        f = fichas.ficha(ticker)
    except fichas.ErrorFicha as e:
        return f"Error en las fichas técnicas: {e}"
    if not f:
        disponibles = ", ".join(sorted(fichas.leer_todas()))
        return f"No hay ficha técnica de {ticker.upper()}. Bonos con ficha: {disponibles}."

    try:
        operacion = date.fromisoformat(fecha) if fecha else date.today()
        _asegurar_feriados(operacion, f["vencimiento"])
        liquidacion = feriados.sumar_dias_habiles(operacion, PLAZO_LIQUIDACION, "BYMA")
        if liquidacion >= f["vencimiento"]:
            return f"{ticker.upper()} vence el {f['vencimiento']}: no quedan flujos para la liquidación del {liquidacion}."
        if precio is None:
            precio, origen = _precio(ticker, date.fromisoformat(fecha) if fecha else None)
        else:
            origen = "precio indicado"
        fecha_cer_corriente = feriados.sumar_dias_habiles(liquidacion, -cer.REZAGO_HABILES, CALENDARIO_HABILES)
        cer_corriente = _cer(fecha_cer_corriente)
        if inflacion_mensual is None:
            inflacion, mes_inflacion = _ultima_inflacion()
            origen_inflacion = f"{mes_inflacion}, INDEC vía BCRA"
        else:
            inflacion, origen_inflacion = inflacion_mensual / 100, "indicada"
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"

    fecha_cer_final = feriados.sumar_dias_habiles(f["vencimiento"], -cer.REZAGO_HABILES, CALENDARIO_HABILES)
    try:
        r = cer.calcular(precio, f["cer_inicial"], cer_corriente, liquidacion, f["vencimiento"], inflacion)
    except ValueError as e:
        return f"Error en el cálculo: {e}"
    avisos = ""
    if not f.get("revisado"):
        avisos += "\nAVISO: la ficha técnica todavía no fue revisada por Agustin; tomá el resultado como preliminar."
    if f.get("nota"):
        avisos += f"\nNOTA: {f['nota']}"
    return (
        f"{ticker.upper()} ({f['tipo']}, vence {f['vencimiento']}) – calculadora de Finianz\n"
        f"Precio: {precio:,.2f} por 100 VN ({origen}) | liquidación {liquidacion} (T+{PLAZO_LIQUIDACION})\n"
        f"Plazo residual: {r['plazo_residual']} días | duration: {r['duration']:.4f}\n"
        f"Base (CER inicial): {f['cer_inicial']:,.4f} | CER corriente: {cer_corriente:,.5f} "
        f"(al {fecha_cer_corriente}, 10.º día hábil anterior a la liquidación) | "
        f"ratio: {r['ratio']:,.4f}\n"
        f"Fecha CER final (10.º día hábil anterior al vencimiento): {fecha_cer_final}\n"
        f"TNA real: {_pct(r['tna_real'])} | TEA real (TIR): {_pct(r['tea_real'])}\n"
        f"Carry mensual: {_pct(r['carry_mensual'])} (inflación {_pct(inflacion)} [{origen_inflacion}] + TNA / 12)"
        + avisos
    )


CALCULAR_BONO = {
    "name": "calcular_bono",
    "description": (
        "Calculadora propia de bonos CER que no pagan intereses ni amortizaciones (Boncer TZX, LeCER X y la parte "
        "CER de los duales TXM): plazo residual, duration, ratio, TNA real, TEA real (TIR) y carry mensual. "
        "Sin precio, usa el precio de mercado: en vivo, o el cierre de 'fecha' si se indica. Cálculos en T+1."
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
