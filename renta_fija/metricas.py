"""Métricas de un bono a un precio dado (TEA, TNA, duration) y el camino inverso: el precio para una tasa.

Es el mismo cálculo con el que se arman las curvas (renta_fija/curvas_mercado.py usa calculadora()). Los datos que no dependen
del precio (CER, A3500, TAMAR publicada) se traen una sola vez por bono, así el precio para una tasa se busca
recalculando solo la parte que depende del precio.

TNA de cada familia (convenciones de docs/convenciones-renta-fija.md):
- Lecap, letras a descuento y TAMAR: TNA simple al vencimiento.
- CER cero cupón: TNA real simple al vencimiento.
- Bonos con cupón (CER con cupón, tasa fija con cupón, dollar linked con cupón): TNA semestral.
- Hard dollar: TNA semestral (la "TIR" del mercado).
- Si la calculadora no la da: la TNA simple equivalente a la TEA en el plazo al vencimiento.
"""
import math
from datetime import date
from typing import Callable

from renta_fija.calculadoras import cer, cer_cupon, dolar_linked, hard_dollar, motor, tamar, tasa_fija
from renta_fija import mercado

UNIDAD = {"tasa_fija_capitalizable": "pesos", "tasa_fija_descuento": "pesos", "tasa_fija_cupon": "pesos",
          "cer_cero_cupon": "pesos reales (se ajustan por CER)", "cer_cupon": "pesos reales (se ajustan por CER)",
          "dolar_linked_bullet": "dólares (se pagan en pesos al A3500)",
          "dolar_linked_cupon": "dólares (se pagan en pesos al A3500)",
          "tamar_capitalizable": "pesos (estimado con la TAMAR publicada y la actual para lo que falta)",
          "hard_dollar": "dólares"}
FAMILIAS_CURVA = {"tasa_fija_capitalizable": "tasa_fija", "tasa_fija_descuento": "tasa_fija",
                  "tasa_fija_cupon": "tasa_fija", "cer_cero_cupon": "cer", "cer_cupon": "cer",
                  "dolar_linked_bullet": "dl", "tamar_capitalizable": "tamar", "hard_dollar": "hd"}


def calculadora(f: dict, liquidacion: date, operacion: date, contexto: dict | None = None) -> Callable[[float], dict]:
    """Función precio -> {"curva", "tea", "tna", "duration" (años), "extra"} para la ficha f.
    Lanza ValueError si la familia no tiene curva."""
    familia = f["familia"]
    ajustar = lambda d: mercado.feriados.proximo_dia_habil(d, mercado.CALENDARIO_HABILES)
    contexto = contexto if contexto is not None else {}

    if familia == "tasa_fija_capitalizable":
        pago = tasa_fija.pago_final(f["cupon"], f["emision"], f["vencimiento"])
        calc = lambda p: tasa_fija.calcular_capitalizable(p, pago, liquidacion, f["vencimiento"])
        tasa = "tea"
    elif familia == "tasa_fija_descuento":
        calc = lambda p: tasa_fija.calcular_descuento(p, liquidacion, f["vencimiento"])
        tasa = "tea"
    elif familia == "tasa_fija_cupon":
        calc = lambda p: tasa_fija.calcular_cupon(p, liquidacion, f["pagos"], f["cupon"], f["frecuencia"], f["emision"], ajustar)
        tasa = "tir_real"
    elif familia == "cer_cero_cupon":
        _, f2, cer_corriente = mercado.datos_cer(f, liquidacion)
        calc = lambda p: cer.calcular(p, f2["cer_inicial"], cer_corriente, liquidacion, f["vencimiento"])
        tasa = "tea_real"
    elif familia == "cer_cupon":
        _, f2, cer_corriente = mercado.datos_cer(f, liquidacion)
        calc = lambda p: cer_cupon.calcular(p, f2["cer_inicial"], cer_corriente, liquidacion, f["pagos"], f["cupon"],
                                            f["frecuencia"], f["emision"], ajustar)
        tasa = "tir_real"
    elif familia == "dolar_linked_bullet":
        tc, fecha_tc, estimado = mercado.a3500(operacion)
        contexto["a3500"] = (tc, fecha_tc, estimado)
        calc = lambda p: dolar_linked.calcular_bullet(p, tc, liquidacion, f["vencimiento"])
        tasa = "tea"
    elif familia == "tamar_capitalizable":
        d = mercado.datos_tamar(f, operacion)
        contexto["tamar_referencia"] = d["referencia"]
        calc = lambda p: tamar.calcular(p, d["tamar_bono"], f["margen"], f["emision"], f["vencimiento"], liquidacion,
                                        d["referencia"])
        tasa = "tea"
    elif familia == "hard_dollar":
        calc = lambda p: hard_dollar.calcular(p, liquidacion, f["pagos"], f["tramos"], f["emision"], ajustar)
        tasa = "tea"
    elif familia == "dolar_linked_cupon":
        tc, fecha_tc, estimado = mercado.a3500(operacion)
        contexto["a3500"] = (tc, fecha_tc, estimado)
        calc = lambda p: dolar_linked.calcular_cupon(p, tc, liquidacion, f["pagos"], f["cupon"], f["emision"], f["base"],
                                                     ajustar)
        tasa = "tir"
    else:
        raise ValueError(f"la familia {familia} no tiene curva")

    plazo = (f["vencimiento"] - liquidacion).days

    def metricas(precio: float) -> dict:
        r = calc(precio)
        tea = r[tasa]
        if familia == "hard_dollar":
            tna = r["tir"]                                   # en hard dollar, la "TIR" del mercado es la TNA semestral
        else:
            tna = next((r[k] for k in ("tna", "tna_real", "tna_semestral") if k in r), None)
        if tna is None and plazo > 0:
            tna = ((1 + tea) ** (plazo / 365) - 1) * 365 / plazo
        extra = {}
        if familia == "tamar_capitalizable":
            extra = dict(margen=f["margen"], conocidas=d["conocidas"], a_estimar=d["a_estimar"], plazo=r["plazo_residual"],
                         dias_30_360=motor.dias_30_360(f["emision"], f["vencimiento"]), emision=f["emision"],
                         desde_estimar=d["desde_estimar"], fin_ventana=d["fin"])
        return {"curva": FAMILIAS_CURVA.get(familia), "tea": tea, "tna": tna, "duration": r["duration"], "extra": extra,
                "detalle": r, "flujos": _flujos(r), "unidad": UNIDAD[familia], "ajuste": _ajuste()}

    def _flujos(r: dict) -> list[dict]:
        """Pagos futuros por 100 VN original, en la unidad del bono: fecha, cupón, amortización, total y residual."""
        if "flujos" in r:
            lista = [(fl.fecha, fl.renta, fl.amortizacion) for fl in r["flujos"]]
        elif familia == "tasa_fija_capitalizable":
            lista = [(f["vencimiento"], pago - 100, 100.0)]
        elif familia == "tamar_capitalizable":
            lista = [(f["vencimiento"], r["pago_final"] - 100, 100.0)]
        else:                                                # descuento, CER cero cupón, dollar linked bullet
            lista = [(f["vencimiento"], 0.0, 100.0)]
        residual = r.get("residual", 100.0)
        filas = []
        for fecha, cupon, amortizacion in lista:
            residual -= amortizacion
            filas.append({"fecha": fecha, "cupon": cupon, "amortizacion": amortizacion, "total": cupon + amortizacion,
                          "residual": max(residual, 0.0)})
        return filas

    def _ajuste() -> tuple[str, float] | None:
        """Para pasar los flujos a pesos de hoy: el coeficiente CER o el A3500."""
        if familia in ("cer_cero_cupon", "cer_cupon"):
            return ("en pesos con el CER de hoy", cer_corriente / f2["cer_inicial"])
        if familia in ("dolar_linked_bullet", "dolar_linked_cupon"):
            return ("en pesos al A3500 de hoy", tc)
        return None

    return metricas


def precio_para(metricas: Callable[[float], dict], objetivo: float, campo: str = "tea", referencia: float = 100.0) -> float:
    """El precio al que la tasa ('tea' o 'tna') es igual al objetivo. A mayor precio, menor tasa: se busca por
    bisección en escala logarítmica, entre referencia/1000 y referencia×1000 (si en un extremo la calculadora no
    converge, se acerca de a 10 veces hacia la referencia)."""
    def diferencia(log_precio: float) -> float | None:
        try:
            return metricas(math.exp(log_precio))[campo] - objetivo
        except (OverflowError, ZeroDivisionError, ValueError, ArithmeticError):
            return None

    centro = math.log(referencia)
    bajo = alto = None
    for paso in range(3, -1, -1):                       # 1000×, 100×, 10×, 1× hacia cada lado
        if bajo is None:
            d = diferencia(centro - paso * math.log(10))
            if d is not None:
                bajo, d_bajo = centro - paso * math.log(10), d
        if alto is None:
            d = diferencia(centro + paso * math.log(10))
            if d is not None:
                alto, d_alto = centro + paso * math.log(10), d
    if bajo is None or alto is None or d_bajo < 0 or d_alto > 0:
        raise ValueError("no hay un precio razonable que dé esa tasa")
    for _ in range(200):
        medio = (bajo + alto) / 2
        d = diferencia(medio)
        if d is None:
            raise ValueError("la calculadora no converge cerca de esa tasa")
        if abs(d) < 1e-12:
            break
        bajo, alto = (medio, alto) if d > 0 else (bajo, medio)
    return math.exp((bajo + alto) / 2)
