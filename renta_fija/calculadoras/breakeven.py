"""Breakevens entre curvas: lo que los precios descuentan de inflación, devaluación, tipo de cambio real,
brecha y TAMAR.

Definiciones acordadas con Agustin (13/11/2026; docs/convenciones-renta-fija.md):
- Cada bono de la curva base (CER, dollar linked o TAMAR) se compara con la otra curva interpolada
  linealmente a su plazo. El eje es la duration en días (duration × 365): en los bonos sin cupón es
  el plazo residual; en los que pagan cupón (TX28, TY30P, hard dollar) es el plazo comparable.
  Fuera del rango de la otra curva no se extrapola.
- Se comparan TEA (efectivas anuales). Breakeven anual = (1 + TEA a) / (1 + TEA b) − 1; mensual =
  (1 + anual)^(1/12) − 1; acumulado hasta el vencimiento = (1 + anual)^(días / 365) − 1.
- Plazo tal cual, sin ajustar por el rezago del CER ni por el tipo de cambio de pago de los dollar linked.
- Forwards: entre dos vencimientos consecutivos, (1 + acumulado 2) / (1 + acumulado 1) − 1.
Funciones puras.
"""


def interpolar(puntos: list[tuple[float, float]], x: float) -> float | None:
    """Interpolación lineal en [(x, valor)]. None si x queda fuera del rango (no se extrapola)."""
    puntos = sorted(puntos)
    if not puntos or x < puntos[0][0] or x > puntos[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        if x0 <= x <= x1:
            return y0 if x1 == x0 else y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return puntos[-1][1]


def mensual(anual: float) -> float:
    return (1 + anual) ** (1 / 12) - 1


def acumulado(anual: float, dias: float) -> float:
    return (1 + anual) ** (dias / 365) - 1


def cruzar(base: list[dict], otra: list[dict], formula) -> list[dict]:
    """Para cada bono de 'base' ({ticker, vencimiento, x, tea}): la TEA de 'otra' interpolada a su x y el
    breakeven = formula(tea base, tea otra), con su versión mensual y acumulada hasta el vencimiento."""
    puntos = [(o["x"], o["tea"]) for o in otra]
    filas = []
    for b in sorted(base, key=lambda b: b["x"]):
        tea_otra = interpolar(puntos, b["x"])
        fila = dict(b, tea_otra=tea_otra, anual=None, mensual=None, acumulado=None)
        if tea_otra is not None:
            anual = formula(b["tea"], tea_otra)
            fila.update(anual=anual, mensual=mensual(anual), acumulado=acumulado(anual, b["x"]))
        filas.append(fila)
    return filas


def forwards(filas: list[dict]) -> list[dict]:
    """Breakeven implícito entre vencimientos consecutivos (por tramo), anual y mensual."""
    validas = [f for f in filas if f["acumulado"] is not None]
    tramos = []
    for a, b in zip(validas, validas[1:]):
        dias = b["x"] - a["x"]
        if dias <= 0:
            continue
        periodo = (1 + b["acumulado"]) / (1 + a["acumulado"]) - 1
        anual = (1 + periodo) ** (365 / dias) - 1
        tramos.append({"desde": a["ticker"], "hasta": b["ticker"], "dias": dias, "periodo": periodo,
                       "anual": anual, "mensual": mensual(anual)})
    return tramos


# Fórmulas de cada breakeven (a = TEA del bono base, b = TEA de la otra curva interpolada)
def inflacion(cer_real: float, tasa_fija: float) -> float:
    """Inflación que iguala un CER (TEA real) con la tasa fija."""
    return (1 + tasa_fija) / (1 + cer_real) - 1


def devaluacion(dolar_linked: float, tasa_fija: float) -> float:
    """Devaluación del A3500 que iguala un dollar linked (TEA en dólares) con la tasa fija."""
    return (1 + tasa_fija) / (1 + dolar_linked) - 1


def tipo_cambio_real(dolar_linked: float, cer_real: float) -> float:
    """Variación del tipo de cambio real (devaluación sobre inflación) que iguala un dollar linked con un CER."""
    return (1 + cer_real) / (1 + dolar_linked) - 1


def brecha(dolar_linked: float, hard_dollar: float) -> float:
    """Variación de la brecha (MEP / A3500) que iguala un dollar linked con un hard dollar en MEP."""
    return (1 + dolar_linked) / (1 + hard_dollar) - 1


def tamar_implicita(tea_objetivo: float, precio: float, plazo: int, dias_30_360: int, margen: float,
                    conocidas: list[float], a_estimar: int) -> float | None:
    """TAMAR promedio de los días por publicar que hace que un bono TAMAR rinda la TEA de la tasa fija.

    Despeja al revés la cuenta del bono: pago final que da esa TEA al precio → TEM → TNA (base 32 días)
    → TAMAR del bono = TNA − margen → TAMAR de los días a estimar. None si ya no quedan días por estimar.
    """
    if a_estimar == 0:
        return None
    pago_final = precio * (1 + tea_objetivo) ** (plazo / 365)
    tem = (pago_final / 100) ** (30 / dias_30_360) - 1
    tna = ((1 + tem) ** (12 * 32 / 365) - 1) * 365 / 32
    tamar_bono = tna - margen
    return (tamar_bono * (len(conocidas) + a_estimar) - sum(conocidas)) / a_estimar


# --- Comparación con el REM ---

def inflacion_acumulada(inflacion_mes: dict[tuple[int, int], float], desde, hasta) -> float:
    """Inflación acumulada entre dos fechas con una inflación por mes calendario: cada mes pesa por la
    fracción de sus días que cae en el período. Error si falta algún mes."""
    from datetime import timedelta
    import calendar
    total, dia = 1.0, desde
    while dia < hasta:
        dias_mes = calendar.monthrange(dia.year, dia.month)[1]
        fin_mes = dia.replace(day=dias_mes) + timedelta(days=1)
        tramo = (min(fin_mes, hasta) - dia).days
        mes = (dia.year, dia.month)
        if mes not in inflacion_mes:
            raise ValueError(f"Falta la inflación de {mes[0]}-{mes[1]:02d}.")
        total *= (1 + inflacion_mes[mes]) ** (tramo / dias_mes)
        dia = min(fin_mes, hasta)
    return total - 1


def interpolar_log(puntos: list[tuple], x) -> float | None:
    """Interpolación lineal del logaritmo (crecimiento geométrico) entre puntos (fecha, valor). None fuera del rango."""
    import math
    puntos = sorted(puntos)
    if not puntos or x < puntos[0][0] or x > puntos[-1][0]:
        return None
    for (x0, y0), (x1, y1) in zip(puntos, puntos[1:]):
        if x0 <= x <= x1:
            peso = 0 if x1 == x0 else (x - x0).days / (x1 - x0).days
            return math.exp(math.log(y0) + (math.log(y1) - math.log(y0)) * peso)
    return puntos[-1][1]


def camino_con_resto(mensuales: dict[tuple[int, int], float], resto: float):
    """Función mes -> valor: el dato mensual donde lo hay; después del último, 'resto' tal cual (ej.: la TAMAR
    del REM: los meses que trae y, para los demás, su valor a 12 meses). Antes del primero, el primero."""
    primero, ultimo = min(mensuales), max(mensuales)

    def valor(mes: tuple[int, int]) -> float:
        if mes in mensuales:
            return mensuales[mes]
        return resto if mes > ultimo else mensuales[primero]
    return valor
