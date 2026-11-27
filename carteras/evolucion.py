"""Evolución real del patrimonio de una cartera con operaciones (etapa 3, paso 3; Agustin, 25/11/2026).

Cada día hábil (los del AL30 en la base de precios, más los días con operaciones) desde la primera operación:
- Patrimonio: títulos a su cierre (hard dollar: precio en dólares × MEP o cable del día; renta fija por 100 VN),
  liquidez por moneda, money market devengado, cauciones y créditos con su interés corrido, menos los pasivos.
  En pesos, dólares MEP y dólares cable (MEP y cable implícitos del AL30 de cada día).
- Aportes y retiros: Depósito y Retiro, e Ingreso y Egreso de títulos (a su precio). No son ganancia.
- Rendimiento sin el efecto de aportes y retiros (TWR): encadena los rendimientos diarios
  r = (patrimonio del día − aportes del día) / patrimonio del día anterior − 1.
- TIR de la cartera (rendimiento ponderado por dinero): la tasa que iguala los aportes y retiros con el patrimonio
  final.
"""
from datetime import date

from carteras import operaciones as ops

MONEDAS = ops.MONEDAS


# --- datos (se reemplazan en las pruebas) ---

def series_tipo_de_cambio() -> dict:
    from carteras import historia
    return historia.tipos_de_cambio()


def precio_historico(ticker: str):
    """Precio en pesos de cada día (por 100 VN en renta fija; por unidad en renta variable), con el último cierre."""
    from carteras import historia
    from renta_fija import leer_fichas
    fichas = leer_fichas.fichas_de(ticker)
    hd = next((f for f in fichas if f["familia"] == "hard_dollar"), None)
    if hd:
        tipo = "ccl" if hd.get("ley") == "NY" else "mep"
        dolares, fx = historia.cierres(ticker + ("C" if tipo == "ccl" else "D")), series_tipo_de_cambio()[tipo]
        return lambda d: dolares.en(d) * fx.en(d) if dolares.en(d) and fx.en(d) else None
    return historia.cierres(ticker).en


def dias_habiles(desde: date, hasta: date) -> list[date]:
    serie = series_tipo_de_cambio()["mep"]
    return [d for d in serie.fechas if desde <= d <= hasta]


# --- cálculo ---

def _tir(flujos: list[tuple[date, float]]) -> float | None:
    """TIR anual (TEA) de flujos fechados, por bisección. None si no cambia de signo."""
    if not flujos or all(m >= 0 for _, m in flujos) or all(m <= 0 for _, m in flujos):
        return None
    t0 = min(d for d, _ in flujos)
    vpn = lambda r: sum(m / (1 + r) ** ((d - t0).days / 365) for d, m in flujos)
    bajo, alto = -0.99, 10.0
    if vpn(bajo) * vpn(alto) > 0:
        return None
    for _ in range(200):
        medio = (bajo + alto) / 2
        if vpn(bajo) * vpn(medio) <= 0:
            alto = medio
        else:
            bajo = medio
    return (bajo + alto) / 2


def evolucion(operaciones: list, hasta: date | None = None) -> dict:
    if not operaciones:
        raise ValueError("La cartera no tiene operaciones.")
    hasta = hasta or date.today()
    inicio = min(op.fecha for op in operaciones)
    fx = series_tipo_de_cambio()
    fechas = sorted(set(dias_habiles(inicio, hasta)) | {op.fecha for op in operaciones if op.fecha <= hasta} | {hasta})
    libro = ops.Libro().preparar([op for op in operaciones if op.fecha <= hasta], hasta)
    precios, ultimo, avisos = {}, {}, []
    tc = lambda m, d: 1.0 if m == "pesos" else fx[m].en(d)

    def precio(ticker, d):
        if ticker not in precios:
            try:
                precios[ticker] = precio_historico(ticker)
            except Exception:
                precios[ticker] = lambda d: None
        valor = precios[ticker](d)
        if valor:
            ultimo[ticker] = valor
        return valor or ultimo.get(ticker)

    puntos, anterior = [], None
    flujos_tir = {m: [] for m in MONEDAS}
    for d in fechas:
        if any(tc(m, d) is None for m in MONEDAS):
            continue                                     # sin MEP o cable para ese día
        aplicadas = libro.hasta(d)
        # Aportes y retiros del día, en pesos
        flujo = 0.0
        for op in aplicadas:
            if op.tipo in ("Depósito", "Retiro"):
                flujo += (op.monto if op.tipo == "Depósito" else -op.monto) * tc(op.moneda, d)
            elif op.tipo in ("Ingreso", "Egreso"):
                base = 100.0 if ops.es_renta_fija(op.ticker) else 1.0
                valor = op.precio * tc(op.moneda, d) if op.precio else precio(op.ticker, d)
                if valor is None:
                    valor = ops.precio_cierre(op.ticker, op.moneda, d) * tc(op.moneda, d)
                flujo += (1 if op.tipo == "Ingreso" else -1) * op.nominales * valor / base
        # Patrimonio
        titulos = 0.0
        for ticker, t in libro.tenencias.items():
            if t.nominales <= 1e-9:
                continue
            p = precio(ticker, d)
            if p is None:
                if f"{ticker}: sin precio" not in " ".join(avisos):
                    avisos.append(f"{ticker}: sin precio histórico en la base; se valúa al costo hasta que lo haya.")
                titulos += t.costo["pesos"]
                continue
            titulos += t.nominales * p / (100.0 if ops.es_renta_fija(ticker) else 1.0)
        liquidez = sum(libro.liquidez[m] * tc(m, d) for m in MONEDAS)
        mm = sum(libro.mm[m] * (1 + libro.tasa_mm[m] / 365) ** max((d - (libro.fecha_mm[m] or d)).days, 0) * tc(m, d)
                 for m in MONEDAS)
        colocado = sum((-1 if c.tipo == "Pasivo" else 1) * c.valor(d) * tc(c.moneda, d) for c in libro.colocaciones)
        total = titulos + liquidez + mm + colocado
        punto = {"fecha": d, "flujo_pesos": flujo}
        for m in MONEDAS:
            punto[m] = total / tc(m, d)
            punto["flujo_" + m] = flujo / tc(m, d)
            if flujo:
                flujos_tir[m].append((d, -punto["flujo_" + m]))
            if anterior and anterior[m] > 0:
                punto["r_" + m] = (punto[m] - punto["flujo_" + m]) / anterior[m] - 1
        puntos.append(punto)
        anterior = punto
    if not puntos:
        raise ValueError("No hay tipos de cambio en la base para el período de las operaciones.")
    resumen = {}
    final = puntos[-1]
    dias = (final["fecha"] - puntos[0]["fecha"]).days
    for m in MONEDAS:
        twr = 1.0
        for p in puntos:
            twr *= 1 + p.get("r_" + m, 0.0)
        twr -= 1
        aportes = sum(p["flujo_" + m] for p in puntos)
        resumen[m] = {"final": final[m], "aportes_netos": aportes, "ganancia": final[m] - aportes, "twr": twr,
                      "twr_anual": (1 + twr) ** (365 / dias) - 1 if dias > 30 and twr > -1 else None,
                      "tir": _tir(flujos_tir[m] + [(final["fecha"], final[m])])}
    return {"puntos": puntos, "resumen": resumen, "avisos": avisos, "desde": puntos[0]["fecha"], "hasta": final["fecha"]}
