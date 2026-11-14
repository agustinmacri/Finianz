"""Bonos ajustados por CER que pagan cupón y amortizan (Boncer con cupón: TX28, TX31...).

Definiciones de Agustin (docs/convenciones-renta-fija.md), tomadas de su calculadora del TX28
con las correcciones acordadas el 13/11/2026. Todo por cada 100 de valor nominal original y en
términos reales (sin el ajuste CER), salvo los precios nominales:

- Ratio = CER corriente / CER inicial (CER corriente: 10.º día hábil anterior a la liquidación).
- Residual = 100 − amortizaciones pagadas hasta la liquidación.
- Cupón de cada pago = residual anterior × tasa × días 30/360 del período / 360 (en un semestre completo,
  × 180/360). El primer período empieza en la emisión.
- Interés corrido = residual × tasa × días 30/360 desde el último cupón / 360.
- Valor técnico = residual + interés corrido.
- Precio real = precio de mercado (el de pantalla) / ratio. En el código, "precio_dirty_real".
- Precio sin el interés corrido (real) = precio real − interés corrido: solo para el current yield y el
  cash yield. En los bonos en pesos no se muestra como "clean" (decisión de Agustin, 14/11/2026).
- Paridad = precio real / valor técnico.
- TIR real = la tasa que iguala los flujos futuros (en las fechas de pago corridas al día
  hábil siguiente) al precio real. TNA semestral ((1+TIR)^(1/2) − 1) × 2, TNA 30 d y TEM:
  equivalentes de la TIR.
- Duration (Macaulay), duration modificada = duration / (1 + TIR), convexidad, PV01 (1 pb) y
  DD (100 pb): con el motor común.
- Current yield = tasa × residual / precio real sin el interés corrido.
- Cash yield = (cupones + amortizaciones de los próximos 12 meses) / precio real sin el interés corrido.

Funciones puras: el CER y los días hábiles los recibe el que llama.
"""
from datetime import date, timedelta

from renta_fija.calculadoras import motor
from renta_fija.calculadoras.motor import Flujo

VN = 100.0


def cronograma(pagos: list[dict], tasa: float, emision: date) -> list[dict]:
    """Agrega a cada pago su residual anterior, su renta y su amortización (por 100 VN).

    pagos: [{'fecha': date, 'amortizacion': % del VN original}], en orden.
    La renta se devenga en base 30/360 entre la fecha de pago anterior (o la emisión) y la del pago.
    """
    residual, filas, anterior = VN, [], emision
    for p in sorted(pagos, key=lambda p: p["fecha"]):
        renta = residual * tasa * motor.dias_30_360(anterior, p["fecha"]) / 360
        amort = p.get("amortizacion", 0.0)
        filas.append({"fecha": p["fecha"], "residual_previo": residual, "renta": renta, "amortizacion": amort})
        residual -= amort
        anterior = p["fecha"]
    return filas


def calcular(precio: float, cer_inicial: float, cer_corriente: float, liquidacion: date, pagos: list[dict],
             tasa: float, frecuencia: int, emision: date, ajustar_fecha) -> dict:
    """Todas las variables de un CER con cupón.

    precio: por 100 VN original, nominal y con cupón corrido (como cotiza).
    ajustar_fecha: función que corre una fecha de pago al día hábil siguiente si no es hábil.
    """
    ratio = cer_corriente / cer_inicial
    filas = cronograma(pagos, tasa, emision)
    pasados = [f for f in filas if f["fecha"] <= liquidacion]
    futuros = [f for f in filas if f["fecha"] > liquidacion]
    if not futuros:
        raise ValueError("El bono ya no tiene pagos después de la liquidación.")

    residual = VN - sum(f["amortizacion"] for f in pasados)
    ultimo_cupon = pasados[-1]["fecha"] if pasados else emision
    corrido = motor.interes_corrido(residual, tasa, ultimo_cupon, liquidacion)
    tecnico = residual + corrido

    dirty_real = precio / ratio
    clean_real = dirty_real - corrido
    flujos = [Flujo(ajustar_fecha(f["fecha"]), f["renta"], f["amortizacion"]) for f in futuros]

    tir = motor.tir(flujos, dirty_real, liquidacion)
    dur = motor.duration(flujos, liquidacion, tir)
    md = motor.duration_modificada(flujos, liquidacion, tir)
    cvx = motor.convexidad(flujos, liquidacion, tir)
    en_un_anio = liquidacion + timedelta(days=365)
    caja_12m = sum(f.total for f in flujos if f.fecha <= en_un_anio)

    return {
        "ratio": ratio,
        "residual": residual,
        "interes_corrido": corrido,
        "valor_tecnico": tecnico,
        "precio_dirty_real": dirty_real,
        "precio_clean_real": clean_real,
        "precio_clean_nominal": clean_real * ratio,
        "paridad": dirty_real / tecnico,
        "tir_real": tir,
        "tna_semestral": motor.tna_semestral(tir),
        "tna_30": motor.tna_equivalente(tir, 30),
        "tem": motor.tem(tir),
        "duration": dur,
        "duration_modificada": md,
        "convexidad": cvx,
        "pv01": motor.sensibilidad(dirty_real, md, cvx, 0.0001),
        "dd": motor.sensibilidad(dirty_real, md, cvx, 0.01),
        "current_yield": tasa * residual / clean_real,
        "cash_yield": caja_12m / clean_real,
        "flujos": flujos,
    }
