"""Historia de la cartera: variaciones por activo y backtest de la composición actual.

Datos: los cierres de la base propia de precios (PPI, datos/precios.db) y las series del BCRA de la base propia (CER,
A3500, TAMAR). MEP y CCL de cada día, implícitos del AL30 (AL30 / AL30D y AL30 / AL30C), como en la valuación.

Variaciones (decisión de Agustin, 25/11/2026): día, semana, mes, en el año y 12 meses, en la moneda de la vista.
Variación de precio y retorno total (precio + cupones y amortizaciones cobrados en el período, cada uno pasado a la
moneda de la vista con el tipo de cambio del día de pago).

Backtest de la composición actual (decisiones de Agustin, 25/11/2026):
- Se invierte el patrimonio de hoy, con los pesos de hoy, en la fecha de inicio.
- Un activo que todavía no cotizaba queda como liquidez a TAMAR (la del momento) hasta su primer precio.
- Cupones y amortizaciones se reinvierten en el mismo activo. Si un activo se cobra entero, lo cobrado se reparte
  entre los demás activos de la cartera en proporción a su valor de ese día.
- Liquidez sin colocar: no rinde (en dólares, se mantiene en dólares). Money market, cauciones, plazos fijos,
  créditos y pasivos: TAMAR del momento.
"""
import bisect
from datetime import date, timedelta

import config
from admin_datos import precios as db_precios
from admin_datos import series as db_series
from carga_datos import precios as carga_precios
from carga_datos import series as carga_series
from conexiones.http import ErrorAPI
from renta_fija import mercado, metricas
from renta_fija.calculadoras import cer

PERIODOS = [("Día", lambda hoy: hoy - timedelta(days=1)), ("Semana", lambda hoy: hoy - timedelta(days=7)),
            ("Mes", lambda hoy: hoy - timedelta(days=30)), ("En el año", lambda hoy: date(hoy.year - 1, 12, 31)),
            ("12 meses", lambda hoy: hoy - timedelta(days=365))]


class Serie:
    """Serie diaria con el último dato disponible a una fecha (los días sin dato toman el anterior)."""

    def __init__(self, puntos: dict[date, float]):
        self.fechas = sorted(puntos)
        self.valores = [puntos[d] for d in self.fechas]

    def en(self, d: date) -> float | None:
        i = bisect.bisect_right(self.fechas, d) - 1
        return self.valores[i] if i >= 0 else None

    def primera(self) -> date | None:
        return self.fechas[0] if self.fechas else None

    def __bool__(self):
        return bool(self.fechas)


_actualizados: set[str] = set()


def cierres(ticker: str) -> Serie:
    """Cierres de la base propia; antes intenta sumar los días que falten desde PPI (si PPI falla, queda lo guardado)."""
    ticker = ticker.upper()
    if ticker not in _actualizados:
        try:
            carga_precios.actualizar(ticker, config.PPI_PLAZO)
        except (ErrorAPI, ValueError, KeyError):
            pass
        _actualizados.add(ticker)
    return Serie({date.fromisoformat(f["fecha"]): float(f["cierre"])
                  for f in db_precios.entre(ticker, config.PPI_PLAZO) if f.get("cierre")})


def serie(variable: str) -> Serie:
    clave = "serie:" + variable
    if clave not in _actualizados:
        try:
            carga_series.actualizar(variable)
        except (ErrorAPI, ValueError, KeyError):
            pass
        _actualizados.add(clave)
    return Serie({date.fromisoformat(f["fecha"]): float(f["valor"]) for f in db_series.entre(variable)})


def tipos_de_cambio() -> dict[str, Serie]:
    """MEP y CCL de cada día con cierre del AL30 y de su par en dólares."""
    pesos, mep, ccl = cierres("AL30"), cierres("AL30D"), cierres("AL30C")
    return {"mep": Serie({d: p / mep.en(d) for d, p in zip(pesos.fechas, pesos.valores) if mep.en(d)}),
            "ccl": Serie({d: p / ccl.en(d) for d, p in zip(pesos.fechas, pesos.valores) if ccl.en(d)})}


def _es_hard_dollar(fila: dict) -> bool:
    return fila["categoria"] == "Renta Fija" and fila.get("_tipo_fx") is not None


def precio_historico(fila: dict, fx: dict[str, Serie]):
    """Precio en pesos de cada día (por 100 VN; renta variable, por unidad) y la primera fecha con precio."""
    if _es_hard_dollar(fila):
        tipo = fila["_tipo_fx"]
        dolares = cierres(fila["ticker"] + ("C" if tipo == "ccl" else "D"))
        def p(d):
            usd, tc = dolares.en(d), fx[tipo].en(d)
            return usd * tc if usd and tc else None
        primera = max(filter(None, (dolares.primera(), fx[tipo].primera())), default=None) if dolares else None
        return p, primera
    s = cierres(fila["ticker"])
    return s.en, s.primera()


def flujos_pesos(fila: dict, desde: date, hasta: date, fx: dict[str, Serie]) -> list[tuple[date, float, bool]]:
    """Cupones y amortizaciones de un bono entre dos fechas: (fecha, pesos por 100 VN original, es el último pago).
    Los flujos salen de la calculadora del bono con la liquidación al inicio; los de CER se ajustan con el CER del
    pago, los dollar linked con el A3500 y los hard dollar con el MEP o el CCL de ese día."""
    if fila["categoria"] != "Renta Fija":
        return []
    f = fila["_legs"][0][0]
    inicio = max(desde, f["emision"])
    if inicio >= hasta:
        return []
    try:
        m = metricas.calculadora(f, inicio + timedelta(days=1), inicio)(fila["_px"] if fila["_px"] else 100.0)
    except (ErrorAPI, ValueError, KeyError, ZeroDivisionError, ArithmeticError):
        return []
    familia = f["familia"]
    salida = []
    cer_inicial = None
    for x in m["flujos"]:
        if not (desde < x["fecha"] <= hasta) or not x["total"]:
            continue
        monto = x["total"]
        if familia.startswith("cer"):
            if cer_inicial is None:
                cer_inicial = mercado.datos_cer(f, inicio + timedelta(days=1))[1]["cer_inicial"]
            fecha_cer = mercado.feriados.sumar_dias_habiles(x["fecha"], -cer.REZAGO_HABILES, mercado.CALENDARIO_HABILES)
            indice = serie("CER").en(fecha_cer)
            if indice is None:
                continue
            monto *= indice / cer_inicial
        elif familia.startswith("dolar_linked"):
            tc = serie("A3500").en(x["fecha"])
            if tc is None:
                continue
            monto *= tc
        elif familia == "hard_dollar":
            tc = fx[fila["_tipo_fx"]].en(x["fecha"])
            if tc is None:
                continue
            monto *= tc
        salida.append((x["fecha"], monto, x["residual"] <= 1e-9))
    return salida


def _divisor(moneda: str, fx: dict[str, Serie], d: date) -> float | None:
    return 1.0 if moneda == "pesos" else fx[moneda].en(d)


def variaciones(v: dict, moneda: str | None = None) -> dict:
    """Variación de precio y retorno total de cada activo (y de la cartera, con las tenencias de hoy) por período."""
    moneda = moneda or v["moneda"]
    hoy = v["fecha"]
    fx = tipos_de_cambio()
    divisor_hoy = 1.0 if moneda == "pesos" else v["fx"][moneda]
    filas, avisos = [], []
    cartera_hoy, cartera_antes = 0.0, {n: [0.0, 0.0, 0.0] for n, _ in PERIODOS}   # antes, ahora, flujos
    for fila in v["filas"]:
        if fila.get("liquidez"):
            continue
        p, _ = precio_historico(fila, fx)
        base = 100.0 if fila["categoria"] == "Renta Fija" else 1.0
        ahora = fila["precio_pesos"] / divisor_hoy
        flujos = flujos_pesos(fila, hoy - timedelta(days=370), hoy, fx)
        resultado = {"ticker": fila["ticker"], "descripcion": fila["descripcion"], "precio": {}, "total": {}}
        for nombre, desde in PERIODOS:
            t0 = desde(hoy)
            p0, div0 = p(t0), _divisor(moneda, fx, t0)
            if not p0 or not div0:
                resultado["precio"][nombre] = resultado["total"][nombre] = None
                continue
            antes = p0 / div0
            cobrado = sum(monto / _divisor(moneda, fx, fecha) for fecha, monto, _ in flujos
                          if t0 < fecha <= hoy and _divisor(moneda, fx, fecha))
            resultado["precio"][nombre] = ahora / antes - 1
            resultado["total"][nombre] = (ahora + cobrado) / antes - 1
            acumulado = cartera_antes[nombre]
            acumulado[0] += fila["nominales"] * antes / base
            acumulado[1] += fila["nominales"] * ahora / base
            acumulado[2] += fila["nominales"] * cobrado / base
        if all(x is None for x in resultado["precio"].values()):
            avisos.append(f"{fila['ticker']}: sin precios históricos en la base propia.")
        filas.append(resultado)
        cartera_hoy += fila["total_pesos"] / divisor_hoy
    total = {"ticker": "", "descripcion": "Cartera (tenencias de hoy)", "precio": {}, "total": {}}
    for nombre, _ in PERIODOS:
        antes, ahora, cobrado = cartera_antes[nombre]
        total["precio"][nombre] = ahora / antes - 1 if antes else None
        total["total"][nombre] = (ahora + cobrado) / antes - 1 if antes else None
    return {"filas": filas, "cartera": total, "periodos": [n for n, _ in PERIODOS], "moneda": moneda,
            "avisos": avisos}


def _crecimiento_tamar(tamar: Serie, desde: date, hasta: date) -> float:
    """Factor de la TAMAR (TNA, capitalización diaria) entre dos fechas, con la tasa vigente cada día."""
    tna = tamar.en(desde)
    if tna is None:
        tna = tamar.valores[0] if tamar else 0.0
    return (1 + tna / 100 / 365) ** (hasta - desde).days


def backtest(v: dict, desde: date) -> dict:
    """Evolución del patrimonio de hoy invertido con la composición de hoy desde 'desde', en pesos, MEP y CCL."""
    hoy = v["fecha"]
    fx = tipos_de_cambio()
    tamar = serie("TAMAR")
    al30 = cierres("AL30")
    fechas = [d for d in al30.fechas if desde <= d <= hoy]
    if not fechas:
        raise ValueError("No hay cierres del AL30 en la base propia para ese período.")
    inicio = fechas[0]
    patrimonio = sum(f["total_pesos"] for f in v["filas"])
    if not patrimonio:
        raise ValueError("La cartera no tiene valor.")
    avisos = []
    if inicio > desde + timedelta(days=5):
        avisos.append(f"El primer día con datos es el {inicio:%d/%m/%Y}.")
    estados = []
    for fila in v["filas"]:
        monto = fila["total_pesos"]
        if fila.get("liquidez"):
            x = fila["_liq"]
            regla = "fija" if x.tipo == "Liquidez" and x.moneda == "pesos" else \
                "dolares" if x.moneda != "pesos" else "tamar"
            estado = {"fila": fila, "clase": "liquidez", "regla": regla, "valor": monto, "moneda": x.moneda}
            if regla == "dolares":
                estado["dolares"] = monto / fx[x.moneda].en(inicio)
            estados.append(estado)
            continue
        p, primera = precio_historico(fila, fx)
        base = 100.0 if fila["categoria"] == "Renta Fija" else 1.0
        emision = fila["_legs"][0][0]["emision"] if fila["categoria"] == "Renta Fija" else None
        disponible = max(filter(None, (primera, emision)), default=None)
        estados.append({"fila": fila, "clase": "activo", "p": p, "base": base, "efectivo": monto, "unidades": 0.0,
                        "disponible": disponible, "activo": False, "vivo": True,
                        "flujos": flujos_pesos(fila, inicio, hoy, fx)})
        if disponible is None:
            avisos.append(f"{fila['ticker']}: sin precios en la base propia; queda como liquidez a TAMAR todo el período.")
        elif disponible > inicio:
            avisos.append(f"{fila['ticker']}: sin precio hasta el {disponible:%d/%m/%Y}; hasta entonces, liquidez a TAMAR.")

    def valor(e, d):
        if e["clase"] == "liquidez":
            return e["dolares"] * fx[e["moneda"]].en(d) if e["regla"] == "dolares" else e["valor"]
        if not e["vivo"]:
            return 0.0
        if not e["activo"]:
            return e["efectivo"]
        precio = e["p"](d)
        return e["unidades"] * precio / e["base"] if precio else e["efectivo"]

    def repartir(monto, d, excepto):
        """Lo cobrado de un activo que se cobró entero va a los demás, en proporción a su valor."""
        destinos = [(e, valor(e, d)) for e in estados if e is not excepto and valor(e, d) > 0
                    and not (e["clase"] == "liquidez" and e["fila"]["categoria"] == "Pasivos")]
        suma = sum(x for _, x in destinos)
        if not suma:
            avisos.append(f"Sin activos para reinvertir un cobro del {d:%d/%m/%Y}: queda como liquidez sin rendimiento.")
            estados.append({"fila": {"categoria": "Liquidez"}, "clase": "liquidez", "regla": "fija", "valor": monto,
                            "moneda": "pesos"})
            return
        for e, x in destinos:
            parte = monto * x / suma
            if e["clase"] == "liquidez":
                if e["regla"] == "dolares":
                    e["dolares"] += parte / fx[e["moneda"]].en(d)
                else:
                    e["valor"] += parte
            elif e["activo"] and e["p"](d):
                e["unidades"] += parte / (e["p"](d) / e["base"])
            else:
                e["efectivo"] += parte

    puntos, anterior = [], None
    for d in fechas:
        for e in list(estados):
            if e["clase"] == "liquidez":
                if e["regla"] == "tamar" and anterior:
                    e["valor"] *= _crecimiento_tamar(tamar, anterior, d)
                continue
            if not e["vivo"]:
                continue
            if not e["activo"]:
                if anterior:
                    e["efectivo"] *= _crecimiento_tamar(tamar, anterior, d)
                if e["disponible"] and d >= e["disponible"] and e["p"](d):
                    e["unidades"] = e["efectivo"] / (e["p"](d) / e["base"])
                    e["activo"] = True
                continue
            for fecha, monto, ultimo in e["flujos"]:
                if anterior and anterior < fecha <= d:
                    cobro = e["unidades"] * monto / 100
                    if ultimo:
                        e["vivo"] = False
                        repartir(cobro, d, e)
                    elif e["p"](d):
                        e["unidades"] += cobro / (e["p"](d) / e["base"])      # se reinvierte en el mismo activo
        total = sum(valor(e, d) for e in estados)
        mep, ccl = fx["mep"].en(d), fx["ccl"].en(d)
        puntos.append({"fecha": d, "pesos": total, "mep": total / mep if mep else None,
                       "ccl": total / ccl if ccl else None})
        anterior = d
    resumen = {}
    for moneda in ("pesos", "mep", "ccl"):
        validos = [x for x in puntos if x[moneda]]
        if len(validos) >= 2:
            a, b = validos[0], validos[-1]
            anios = (b["fecha"] - a["fecha"]).days / 365
            rendimiento = b[moneda] / a[moneda] - 1
            resumen[moneda] = {"inicial": a[moneda], "final": b[moneda], "rendimiento": rendimiento,
                               "anualizado": (1 + rendimiento) ** (1 / anios) - 1 if anios > 0.05 else None}
    return {"puntos": puntos, "resumen": resumen, "avisos": avisos, "desde": inicio, "hasta": fechas[-1]}
