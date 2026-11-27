"""Cupones y amortizaciones de un bono entre dos fechas, en la moneda en que se cobran.

Es la única fuente de los pagos de un bono para las carteras: el libro de operaciones (carteras/operaciones.py), las
variaciones y el backtest (carteras/historia.py).

- Montos por 100 VN original, en la moneda de pago: pesos; hard dollar en dólares MEP (ley AR) o cable (ley NY).
- CER: con el CER del pago (10.º día hábil anterior), de la base propia.
- Dollar linked: con el A3500 de pago (3.er día hábil anterior, o el rezago de la ficha).
- TAMAR: el pago final con la calculadora a la fecha del pago (la TAMAR ya publicada).
- Pago ya conocido (CER, A3500 o TAMAR publicados): los flujos ya están en pesos.
- Duales: en cada fecha, la pata que más paga.
"""
from datetime import date, timedelta

from fuentes_datos.bases import series as db_series
from renta_fija import metricas
from fuentes_datos import mercado


def pagos(ticker: str, desde: date, hasta: date) -> list[dict]:
    """[{"fecha", "moneda", "renta", "amortizacion", "residual_antes", "final"}] con desde < fecha <= hasta."""
    salida = {}
    for f in metricas.fichas_de(ticker):
        inicio = max(desde, f["emision"])
        if inicio >= hasta:
            continue
        try:
            m = metricas.calculadora(f, inicio + timedelta(days=1), inicio)(100.0)
        except Exception:
            continue
        familia = f["familia"]
        moneda = mercado.moneda_hard_dollar(f) if familia == "hard_dollar" else "pesos"
        cer_inicial = None
        for x in m["flujos"]:
            if not (desde < x["fecha"] <= hasta) or not x["total"]:
                continue
            factor = 1.0
            if m.get("pago_conocido"):
                pass
            elif familia.startswith("cer"):
                indice = db_series.valor("CER", mercado.fecha_cer(x["fecha"]))
                if indice is None:
                    continue
                if cer_inicial is None:
                    cer_inicial = mercado.datos_cer(f, inicio + timedelta(days=1))[1]["cer_inicial"]
                factor = indice / cer_inicial
            elif familia.startswith("dolar_linked"):
                tc = mercado.a3500_pago_conocido(f, x["fecha"])
                if tc is None:
                    continue
                factor = tc
            elif familia == "tamar_capitalizable" and x["fecha"] >= f["vencimiento"]:
                try:                                   # el pago final con la TAMAR ya publicada
                    final = metricas.calculadora(f, x["fecha"] - timedelta(days=1), x["fecha"] - timedelta(days=2))(100.0)
                    x = dict(x, **{k: final["flujos"][-1][k] for k in ("cupon", "amortizacion", "total")})
                except Exception:
                    pass
            pago = {"fecha": x["fecha"], "moneda": moneda, "renta": x["cupon"] * factor,
                    "amortizacion": x["amortizacion"] * factor, "residual_antes": (x["residual"] + x["amortizacion"]) * factor,
                    "final": x["residual"] <= 1e-9}
            previo = salida.get(x["fecha"])
            if previo is None or pago["renta"] + pago["amortizacion"] > previo["renta"] + previo["amortizacion"]:
                salida[x["fecha"]] = pago                # dual: la pata que más paga
    return [salida[d] for d in sorted(salida)]
