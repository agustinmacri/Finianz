"""Qué pata de un dual va a pagar, cuando ya no hay duda (decisión de Agustin, 27/11/2026).

Al vencimiento un dual paga la pata de mayor pago final. Cerca del vencimiento, o cuando una variable ya acumuló
mucho, una pata puede quedar definida aunque todavía no se sepa el número exacto. Criterio, sin supuestos: una pata
queda definida si su pago MÍNIMO posible (las variables que faltan publicar en cero: TAMAR 0, inflación 0, A3500 0)
ya es mayor o igual que el pago MÁXIMO posible de la otra. Solo tiene máximo una pata de pago fijo (tasa fija) o
con su variable ya publicada (CER final, TAMAR de toda la ventana, A3500 de pago); si la otra pata depende de algo
que todavía no se publicó, no tiene techo y el dual sigue siendo dual.

Ejemplo, TTD26 (tasa fija / TAMAR): para que pague la tasa fija, la TAMAR de los días que faltan tendría que ser
negativa; la pata TAMAR ya está definida y el bono pasa a la curva TAMAR como un bono más.

Pagos por 100 VN original, en pesos (la pata TAMAR de un dual con VN en dólares, por el tipo de cambio inicial; la
pata dollar linked, USD 100 al A3500 de pago).
"""
from datetime import date

from fuentes_datos import mercado
from fuentes_datos.bases import series as db_series
from renta_fija import metricas
from renta_fija.calculadoras import tamar, tasa_fija


def _cer_minimo(fecha_final: date, operacion: date) -> float:
    """El CER final más bajo posible: el último CER ya conocido el día de la operación hasta la fecha del CER final
    (el CER no baja si la inflación no es negativa)."""
    conocido = mercado.cer_final_conocido(fecha_final, operacion)
    if conocido is not None:
        return conocido
    desde = date.fromordinal(min(fecha_final, operacion).toordinal() - 120)
    filas = db_series.entre("CER", desde.isoformat(), fecha_final.isoformat())
    for fila in reversed(filas):
        fecha = date.fromisoformat(fila["fecha"])
        if mercado.publicacion_cer(fecha) <= operacion:
            return fila["valor"]
    raise ValueError(f"no hay CER conocido antes del {fecha_final}")


def pagos_extremos(f: dict, operacion: date) -> tuple[float, float | None]:
    """(pago mínimo, pago máximo) de una pata, por 100 VN original en pesos; máximo None = sin techo."""
    familia = f["familia"]
    if familia == "tasa_fija_capitalizable":
        pago = tasa_fija.pago_final(f["cupon"], f["emision"], f["vencimiento"])
        return pago, pago
    if familia == "tamar_capitalizable":
        d = mercado.datos_tamar(f, operacion)
        escala = mercado.tipo_cambio_inicial(f)
        total = len(d["conocidas"]) + d["a_estimar"]
        minimo = tamar.pago_final(tamar.tem(sum(d["conocidas"]) / total, f["margen"]), f["emision"], f["vencimiento"]) * escala
        definida = d["a_estimar"] == 0 and d["fin"] < operacion
        return minimo, (minimo if definida else None)
    if familia == "cer_cero_cupon":
        cer_inicial = mercado.cer_de(mercado.fecha_cer(f["emision"]))
        fecha_final = mercado.fecha_cer(f["vencimiento"])
        conocido = mercado.cer_final_conocido(f["vencimiento"], operacion)
        if conocido is not None:
            return 100 * conocido / cer_inicial, 100 * conocido / cer_inicial
        return 100 * _cer_minimo(fecha_final, operacion) / cer_inicial, None
    if familia == "dolar_linked_bullet":
        tc = mercado.a3500_pago_conocido(f, operacion)
        return (100 * tc, 100 * tc) if tc is not None else (0.0, None)
    raise ValueError(f"la familia {familia} no se usa en duales")


def pata_que_paga(ticker: str, operacion: date) -> str | None:
    """La familia de la pata que va a pagar, si ya está definida; None si el dual sigue abierto."""
    patas = metricas.fichas_de(ticker)
    if len(patas) != 2:
        return None
    extremos = {f["familia"]: pagos_extremos(f, operacion) for f in patas}
    for ganadora, otra in ((patas[0]["familia"], patas[1]["familia"]), (patas[1]["familia"], patas[0]["familia"])):
        techo_otra = extremos[otra][1]
        if techo_otra is not None and extremos[ganadora][0] >= techo_otra:
            return ganadora
    return None
