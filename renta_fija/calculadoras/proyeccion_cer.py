"""Proyección del CER y rendimiento nominal de los bonos CER.

Regla del CER (verificada con la serie del BCRA, 13/11/2026; docs/convenciones-renta-fija.md):
- La inflación del mes m se aplica del día 16 del mes m+1 al 15 del mes m+2, inclusive.
- Factor diario = (1 + inflación) ^ (1 / días corridos del período): el CER crece todos los días.
- Por lo tanto CER(15 del mes m+2) = CER(15 del mes m+1) × (1 + inflación del mes m), y la inflación
  publicada de cada mes se puede leer de la propia serie del CER.

Camino de inflación para proyectar (una inflación por mes):
- Mensual: la del mes, si la fuente la trae (REM de los próximos meses, escenario mes a mes).
- Anual (diciembre contra diciembre): los meses del año que no tienen dato mensual ni publicado se
  completan con una misma tasa, de modo que el año cierre en la inflación anual.
- Años sin dato: la última inflación anual disponible, pasada a mensual.
Funciones puras.
"""
from datetime import date, timedelta

from renta_fija.calculadoras import motor

Mes = tuple[int, int]


def sumar_meses(mes: Mes, k: int) -> Mes:
    n = mes[0] * 12 + mes[1] - 1 + k
    return n // 12, n % 12 + 1


def periodo(mes: Mes) -> tuple[date, date]:
    """Días en los que se aplica la inflación de 'mes': del 16 del mes siguiente al 15 del subsiguiente."""
    a, b = sumar_meses(mes, 1), sumar_meses(mes, 2)
    return date(a[0], a[1], 16), date(b[0], b[1], 15)


def mes_aplicado(dia: date) -> Mes:
    """De qué mes es la inflación que hace crecer el CER ese día."""
    return sumar_meses((dia.year, dia.month), -1 if dia.day >= 16 else -2)


def inflacion_publicada(cer: dict[date, float]) -> dict[Mes, float]:
    """Inflación de cada mes contenida en la serie del CER: CER(15 de m+2) / CER(15 de m+1) − 1."""
    salida = {}
    quinces = sorted(d for d in cer if d.day == 15)
    for d in quinces:
        mes = sumar_meses((d.year, d.month), -2)
        anterior = date(*sumar_meses((d.year, d.month), -1), 15)
        if anterior in cer:
            salida[mes] = cer[d] / cer[anterior] - 1
    return salida


def camino(publicadas: dict[Mes, float], mensuales: dict[Mes, float], anuales: dict[int, float],
           desde: Mes, hasta: Mes) -> dict[Mes, tuple[float, str]]:
    """Inflación de cada mes entre 'desde' y 'hasta' (inclusive) y de dónde sale."""
    salida, mes = {}, desde
    while mes <= hasta:
        if mes in mensuales:
            salida[mes] = (mensuales[mes], "mensual")
        elif mes[0] in anuales:
            conocidos = [(publicadas.get((mes[0], m)), mensuales.get((mes[0], m))) for m in range(1, 13)]
            producto, libres = 1.0, 0
            for m, (pub, men) in zip(range(1, 13), conocidos):
                valor = pub if pub is not None and (mes[0], m) < desde else men
                if valor is None:
                    libres += 1
                else:
                    producto *= 1 + valor
            tasa = ((1 + anuales[mes[0]]) / producto) ** (1 / libres) - 1
            salida[mes] = (tasa, f"anual {mes[0]}")
        else:
            anteriores = [a for a in anuales if a < mes[0]]
            if not anteriores:
                raise ValueError(f"No hay inflación para {mes[0]}-{mes[1]:02d}: falta un dato mensual o anual.")
            ultimo = max(anteriores)
            salida[mes] = ((1 + anuales[ultimo]) ** (1 / 12) - 1, f"anual {ultimo} (último año con dato)")
        mes = sumar_meses(mes, 1)
    return salida


def proyectar(cer: dict[date, float], inflacion: dict[Mes, float], hasta: date) -> dict[date, float]:
    """CER diario desde el día siguiente al último dato hasta 'hasta', con la regla del BCRA."""
    dia = max(cer)
    valor = cer[dia]
    salida = {}
    while dia < hasta:
        dia += timedelta(days=1)
        mes = mes_aplicado(dia)
        if mes not in inflacion:
            raise ValueError(f"Falta la inflación de {mes[0]}-{mes[1]:02d} para proyectar el CER del {dia}.")
        inicio, fin = periodo(mes)
        valor *= (1 + inflacion[mes]) ** (1 / ((fin - inicio).days + 1))
        salida[dia] = valor
    return salida


def tiempo_cer(dia: date) -> float:
    """Posición del día medida en meses de CER: cada período del 16 al 15 vale 1, sin importar sus días.
    Con esta escala, una inflación mensual constante hace crecer el logaritmo del CER en línea recta."""
    mes = mes_aplicado(dia)
    inicio, fin = periodo(mes)
    return mes[0] * 12 + mes[1] + ((dia - inicio).days + 1) / ((fin - inicio).days + 1)


def inflacion_desde_cer(ancla: tuple[date, float], puntos: list[tuple[date, float]], desde: Mes,
                        hasta: Mes) -> dict[Mes, tuple[float, str]]:
    """Inflación mensual compatible con niveles de CER en algunas fechas (por ejemplo, los que descuentan
    los bonos). Interpola el logaritmo del CER entre puntos en meses de CER (inflación mensual constante
    entre dos puntos) y lee la inflación de cada mes en los días 15. Después del último punto, repite la
    última inflación mensual obtenida."""
    import math
    nodos = sorted([ancla, *puntos])

    def cer_en(dia: date) -> float | None:
        if dia < nodos[0][0] or dia > nodos[-1][0]:
            return None
        for (d0, c0), (d1, c1) in zip(nodos, nodos[1:]):
            if d0 <= dia <= d1:
                t0, t1, t = tiempo_cer(d0), tiempo_cer(d1), tiempo_cer(dia)
                peso = 0 if t1 == t0 else (t - t0) / (t1 - t0)
                return math.exp(math.log(c0) + (math.log(c1) - math.log(c0)) * peso)
        return nodos[-1][1]

    salida, mes, ultima = {}, desde, None
    while mes <= hasta:
        a, b = date(*sumar_meses(mes, 1), 15), date(*sumar_meses(mes, 2), 15)
        ca, cb = cer_en(a), cer_en(b)
        if ca is not None and cb is not None:
            ultima = cb / ca - 1
            salida[mes] = (ultima, "breakeven")
        elif ultima is not None:
            salida[mes] = (ultima, "breakeven (última, extendida)")
        else:
            raise ValueError("Los niveles de CER no alcanzan para leer la inflación de ningún mes.")
        mes = sumar_meses(mes, 1)
    return salida


# --- Rendimiento nominal de los bonos CER con un CER proyectado ---

def nominal_cero_cupon(precio: float, cer_inicial: float, cer_final: float, liquidacion: date,
                       vencimiento: date) -> dict:
    """Pago final en pesos = 100 × CER final / CER inicial; TNA y TIR nominales como una Lecap."""
    pago = 100 * cer_final / cer_inicial
    plazo = (vencimiento - liquidacion).days
    tna = (pago / precio - 1) * 365 / plazo
    return {"pago_final": pago, "plazo": plazo, "tna": tna, "tir": (pago / precio) ** (365 / plazo) - 1,
            "tem": (pago / precio) ** (30 / plazo) - 1}


def nominal_con_cupon(precio: float, cer_inicial: float, flujos_reales: list[motor.Flujo],
                      cer_de_cada_pago: list[float], liquidacion: date) -> dict:
    """Flujos en pesos = flujo real × CER del pago / CER inicial; TIR nominal efectiva (base 365)."""
    nominales = [motor.Flujo(f.fecha, f.renta * c / cer_inicial, f.amortizacion * c / cer_inicial)
                 for f, c in zip(flujos_reales, cer_de_cada_pago)]
    tir = motor.tir(nominales, precio, liquidacion)
    return {"flujos": nominales, "tir": tir, "tna_semestral": motor.tna_semestral(tir), "tem": motor.tem(tir),
            "duration": motor.duration(nominales, liquidacion, tir)}
