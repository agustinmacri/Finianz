"""Operaciones de una cartera (hoja "Operaciones" del Excel): de ahí salen las posiciones, la liquidez, el costo y el
resultado realizado. Decisiones de Agustin (25-27/11/2026):

- Columnas: Fecha (de concertación: manda para todo), Contraparte (texto libre), Tipo, Ticker, Nominales, Precio,
  Moneda (pesos, mep o ccl), Monto, Tasa (TNA), Vencimiento, Gastos, Nota.
- Tipos:
  · Títulos: Compra, Venta, Ingreso y Egreso (Ticker, Nominales, Precio por 100 VN o por unidad, Moneda, Gastos).
    Ingreso sin precio: el cierre de ese día. Ingreso y Egreso no mueven la liquidez.
  · Plata: Depósito, Retiro, Dividendo y Cobro (Monto y Moneda). Cobro, con Ticker, reemplaza el cupón o la
    amortización que el sistema calcula para ese día (lo que diga el aviso de pago manda).
  · Money market: Suscripción, Rescate (Monto) y Valuación (fija el saldo real). Rinde a la última TNA cargada.
  · Caución colocadora, Crédito y Pasivo (caución tomadora): Monto, Tasa y Vencimiento; al vencer se cancelan solos
    contra la liquidez, con los intereses (interés simple por los días del plazo).
- Cupones y amortizaciones: los calcula el sistema con las fichas para los nominales que había el día de pago y entran
  enteros a la liquidez de la moneda de pago (pesos; hard dollar ley AR en MEP, ley NY en cable). Pendiente (Agustin):
  traerlos de los avisos de pago (BYMA para el Tesoro, CNV para los corporativos), con su índice (CER, TAMAR, A3500).
- Costo: promedio ponderado, llevado a la vez en pesos, dólares MEP y dólares cable (cada compra pasada al tipo de
  cambio del día de la operación), para ver el resultado en la moneda que se elija.
- Resultado realizado: venta = lo cobrado neto de gastos menos el costo de lo vendido; cupón = todo; amortización = lo
  cobrado menos el costo de la parte amortizada (y el costo de lo que queda baja en proporción); dividendo = todo;
  intereses de cauciones, créditos y money market a favor; los de pasivos, en contra.
"""
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

MONEDAS = ("pesos", "mep", "ccl")
TIPOS = {"compra": "Compra", "venta": "Venta", "ingreso": "Ingreso", "egreso": "Egreso", "deposito": "Depósito",
         "retiro": "Retiro", "dividendo": "Dividendo", "cobro": "Cobro", "suscripcion": "Suscripción",
         "rescate": "Rescate", "valuacion": "Valuación", "caucion colocadora": "Caución colocadora",
         "caucion": "Caución colocadora", "credito": "Crédito", "pasivo": "Pasivo", "caucion tomadora": "Pasivo"}
COLUMNAS = ["Fecha", "Contraparte", "Tipo", "Ticker", "Nominales", "Precio", "Moneda", "Monto", "Tasa", "Vencimiento",
            "Gastos", "Nota"]


def _clave(texto) -> str:
    texto = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return " ".join(texto.replace("_", " ").split())


def tipo_operacion(texto) -> str:
    tipo = TIPOS.get(_clave(texto))
    if tipo is None:
        raise ValueError(f"Tipo de operación desconocido '{texto}'. Opciones: {', '.join(sorted(set(TIPOS.values())))}.")
    return tipo


@dataclass
class Operacion:
    fecha: date
    tipo: str
    ticker: str | None = None
    nominales: float | None = None
    precio: float | None = None
    moneda: str = "pesos"
    monto: float | None = None
    tasa: float | None = None
    vencimiento: date | None = None
    gastos: float = 0.0
    contraparte: str | None = None
    nota: str | None = None


@dataclass
class Tenencia:
    nominales: float = 0.0
    costo: dict = field(default_factory=lambda: {m: 0.0 for m in MONEDAS})     # costo total de lo que queda


@dataclass
class Colocacion:
    """Caución colocadora, crédito o pasivo abierto."""
    tipo: str
    moneda: str
    monto: float
    tasa: float
    desde: date
    vencimiento: date
    contraparte: str | None = None

    def valor(self, d: date) -> float:
        dias = max(min(d, self.vencimiento) - self.desde, timedelta(0)).days
        return self.monto * (1 + self.tasa * dias / 365)


# --- datos externos (se reemplazan en las pruebas) ---

def tipo_de_cambio(moneda: str, d: date) -> float:
    """Pesos por unidad de la moneda el día d (MEP y CCL implícitos del AL30, con el último cierre disponible)."""
    if moneda == "pesos":
        return 1.0
    from carteras import historia
    valor = historia.tipos_de_cambio()[moneda].en(d)
    if valor is None:
        raise ValueError(f"No hay {moneda.upper()} del {d:%d/%m/%Y} en la base de precios (AL30).")
    return valor


def precio_cierre(ticker: str, moneda: str, d: date) -> float:
    """Cierre de un día, para los ingresos sin precio (D o C para los precios en dólares)."""
    from fuentes_datos import mercado
    sufijo = {"mep": "D", "ccl": "C"}.get(moneda, "")
    return mercado.precio(ticker + sufijo, d)[0]


def es_renta_fija(ticker: str) -> bool:
    from renta_fija import leer_fichas
    return bool(leer_fichas.fichas_de(ticker))


def pagos(ticker: str, desde: date, hasta: date) -> list[dict]:
    """Cupones y amortizaciones de un bono entre dos fechas, por 100 VN original y en la moneda de pago
    (renta_fija/pagos.py)."""
    from renta_fija import pagos as pagos_bono
    return pagos_bono.pagos(ticker, desde, hasta)


# --- motor ---

class Libro:
    """Recorre las operaciones en orden y lleva el estado de la cartera."""

    def __init__(self):
        self.tenencias: dict[str, Tenencia] = {}
        self.liquidez = {m: 0.0 for m in MONEDAS}
        self.mm = {m: 0.0 for m in MONEDAS}               # saldo del money market por moneda
        self.tasa_mm = {m: 0.0 for m in MONEDAS}
        self.fecha_mm = {m: None for m in MONEDAS}
        self.colocaciones: list[Colocacion] = []
        self.realizado: list[dict] = []
        self.cobros: list[dict] = []
        self.avisos: list[str] = []
        self.fecha: date | None = None

    # conversiones
    def _en_todas(self, monto: float, moneda: str, d: date) -> dict:
        pesos = monto * tipo_de_cambio(moneda, d)
        return {m: pesos / tipo_de_cambio(m, d) for m in MONEDAS}

    def _realizar(self, d, ticker, concepto, moneda, monto, costo: dict | None = None, contraparte=None):
        ingreso = self._en_todas(monto, moneda, d)
        resultado = {m: ingreso[m] - (costo[m] if costo else 0.0) for m in MONEDAS}
        self.realizado.append({"fecha": d, "ticker": ticker, "concepto": concepto, "moneda": moneda, "monto": monto,
                               "resultado": resultado, "contraparte": contraparte})

    # money market: rinde a la última TNA (capitalización diaria)
    def _devengar_mm(self, d: date):
        for m in MONEDAS:
            if self.fecha_mm[m] and self.mm[m] and d > self.fecha_mm[m]:
                interes = self.mm[m] * ((1 + self.tasa_mm[m] / 365) ** (d - self.fecha_mm[m]).days - 1)
                if interes:
                    self.mm[m] += interes
                    self._realizar(d, "", "Interés money market", m, interes)
            self.fecha_mm[m] = d

    def _vencimientos(self, hasta: date):
        for c in [c for c in self.colocaciones if c.vencimiento <= hasta]:
            final = c.valor(c.vencimiento)
            signo = -1 if c.tipo == "Pasivo" else 1
            self.liquidez[c.moneda] += signo * final
            self._realizar(c.vencimiento, "", f"Interés {c.tipo.lower()}", c.moneda, signo * (final - c.monto),
                           contraparte=c.contraparte)
            self.colocaciones.remove(c)

    def _cobrar(self, d: date, ticker: str, p: dict, monto_aviso: float | None = None):
        t = self.tenencias[ticker]
        renta = t.nominales * p["renta"] / 100
        amortizacion = t.nominales * p["amortizacion"] / 100
        if monto_aviso is not None and renta + amortizacion:     # el aviso de pago manda: se reparte en proporción
            escala = monto_aviso / (renta + amortizacion)
            renta, amortizacion = renta * escala, amortizacion * escala
        moneda = p["moneda"]
        self.liquidez[moneda] += renta + amortizacion           # entra todo a la liquidez
        self.cobros.append({"fecha": d, "ticker": ticker, "moneda": moneda, "renta": renta,
                            "amortizacion": amortizacion, "total": renta + amortizacion,
                            "aviso": monto_aviso is not None})
        if renta:
            self._realizar(d, ticker, "Cupón", moneda, renta)
        if amortizacion:
            fraccion = min(p["amortizacion"] / p["residual_antes"], 1.0) if p["residual_antes"] else 1.0
            costo = {m: t.costo[m] * fraccion for m in MONEDAS}
            for m in MONEDAS:
                t.costo[m] -= costo[m]
            self._realizar(d, ticker, "Vencimiento" if p["final"] else "Amortización", moneda, amortizacion, costo)
        if p["final"]:
            t.nominales = 0.0
            t.costo = {m: 0.0 for m in MONEDAS}

    def aplicar(self, op: Operacion):
        d, moneda = op.fecha, op.moneda
        tipo = op.tipo
        if tipo in ("Compra", "Ingreso"):
            precio = op.precio
            if precio is None:
                if tipo == "Compra":
                    raise ValueError(f"{d:%d/%m/%Y} compra de {op.ticker}: falta el precio.")
                precio = precio_cierre(op.ticker, moneda, d)
            base = 100.0 if es_renta_fija(op.ticker) else 1.0
            importe = op.nominales * precio / base + (op.gastos or 0.0)
            t = self.tenencias.setdefault(op.ticker, Tenencia())
            t.nominales += op.nominales
            for m, valor in self._en_todas(importe, moneda, d).items():
                t.costo[m] += valor
            if tipo == "Compra":
                self.liquidez[moneda] -= importe
        elif tipo in ("Venta", "Egreso"):
            t = self.tenencias.get(op.ticker)
            if not t or t.nominales < op.nominales - 1e-6:
                raise ValueError(f"{d:%d/%m/%Y} {tipo.lower()} de {op.nominales:,.0f} {op.ticker}: hay "
                                 f"{t.nominales if t else 0:,.0f}.")
            fraccion = op.nominales / t.nominales
            costo = {m: t.costo[m] * fraccion for m in MONEDAS}
            t.nominales -= op.nominales
            for m in MONEDAS:
                t.costo[m] -= costo[m]
            if tipo == "Venta":
                if op.precio is None:
                    raise ValueError(f"{d:%d/%m/%Y} venta de {op.ticker}: falta el precio.")
                base = 100.0 if es_renta_fija(op.ticker) else 1.0
                neto = op.nominales * op.precio / base - (op.gastos or 0.0)
                self.liquidez[moneda] += neto
                self._realizar(d, op.ticker, "Venta", moneda, neto, costo, op.contraparte)
        elif tipo in ("Depósito", "Retiro"):
            self.liquidez[moneda] += op.monto if tipo == "Depósito" else -op.monto
        elif tipo == "Dividendo":
            self.liquidez[moneda] += op.monto
            self._realizar(d, op.ticker or "", "Dividendo", moneda, op.monto, contraparte=op.contraparte)
        elif tipo == "Cobro":
            pass                                         # se aplica en el cobro automático de ese día
        elif tipo in ("Suscripción", "Rescate", "Valuación"):
            if op.tasa is not None:
                self.tasa_mm[moneda] = op.tasa
            if tipo == "Suscripción":
                self.mm[moneda] += op.monto
                self.liquidez[moneda] -= op.monto
            elif tipo == "Rescate":
                self.mm[moneda] -= op.monto
                self.liquidez[moneda] += op.monto
            else:
                diferencia = op.monto - self.mm[moneda]
                if diferencia:
                    self._realizar(d, "", "Ajuste valuación money market", moneda, diferencia)
                self.mm[moneda] = op.monto
            self.fecha_mm[moneda] = d
        elif tipo in ("Caución colocadora", "Crédito", "Pasivo"):
            if not op.vencimiento or op.vencimiento <= d:
                raise ValueError(f"{d:%d/%m/%Y} {tipo.lower()}: falta el vencimiento (posterior a la fecha).")
            self.colocaciones.append(Colocacion(tipo, moneda, op.monto, op.tasa or 0.0, d, op.vencimiento,
                                                op.contraparte))
            self.liquidez[moneda] += op.monto if tipo == "Pasivo" else -op.monto

    def preparar(self, operaciones: list[Operacion], fin: date):
        """Para recorrer de a poco (evolución diaria): las operaciones en orden y los pagos de cada bono hasta 'fin'."""
        self._ops = sorted(operaciones, key=lambda op: op.fecha)
        self._i, self._anterior, self._fin = 0, None, fin
        self._inicio = (self._ops[0].fecha - timedelta(days=1)) if self._ops else fin
        self._corregidos = {(op.ticker.upper(), op.fecha): op.monto for op in self._ops
                            if op.tipo == "Cobro" and op.ticker}
        self._pagos = {}
        return self

    def hasta(self, d: date) -> list[Operacion]:
        """Avanza hasta el día d (inclusive). Devuelve las operaciones aplicadas en el tramo."""
        aplicadas = []
        while self._i < len(self._ops) and self._ops[self._i].fecha <= d:
            op = self._ops[self._i]
            self._avanzar(self._anterior, op.fecha, self._corregidos)
            self.aplicar(op)
            aplicadas.append(op)
            self._anterior = op.fecha
            self._i += 1
        self._avanzar(self._anterior, d, self._corregidos)
        if self._anterior is not None and d > self._anterior:
            self._anterior = d
        self.fecha = d
        return aplicadas

    def recorrer(self, operaciones: list[Operacion], hasta: date):
        """Aplica las operaciones hasta 'hasta' (inclusive), con los cobros, vencimientos e intereses en el medio."""
        self.preparar([op for op in operaciones if op.fecha <= hasta], hasta)
        self.hasta(hasta)
        return self

    def _pagos_de(self, ticker: str, desde: date, hasta: date) -> list[dict]:
        if ticker not in self._pagos:
            self._pagos[ticker] = pagos(ticker, self._inicio, max(self._fin, hasta))
        return [p for p in self._pagos[ticker] if desde < p["fecha"] <= hasta]

    def _avanzar(self, desde: date | None, hasta: date, corregidos: dict):
        """Cobros, vencimientos e intereses entre la última operación y la siguiente. Los del mismo día de una
        operación se aplican antes que ella (un pago del día lo cobra quien tenía los títulos)."""
        if desde is None:
            return
        tope = hasta
        if tope > desde:
            eventos = []
            for ticker, t in self.tenencias.items():
                if t.nominales > 0 and es_renta_fija(ticker):
                    eventos += [(p["fecha"], ticker, p) for p in self._pagos_de(ticker, desde, tope)]
            for d, ticker, p in sorted(eventos, key=lambda e: e[0]):
                self._devengar_mm(d)
                self._vencimientos(d)
                if self.tenencias[ticker].nominales > 0:
                    self._cobrar(d, ticker, p, corregidos.get((ticker.upper(), d)))
        self._vencimientos(tope)
        self._devengar_mm(tope)


def estado(operaciones: list[Operacion], hasta: date | None = None) -> Libro:
    """El estado de la cartera a una fecha (hoy, si no se indica)."""
    return Libro().recorrer(operaciones, hasta or date.today())


def resultados(v: dict) -> dict:
    """Resultado realizado (por activo y concepto) y no realizado (valor de hoy − costo), en la moneda de la vista."""
    moneda = v["moneda"]
    realizado = {}
    for x in (v.get("libro") or {}).get("realizado", []):
        clave = x["ticker"] or x["concepto"]
        fila = realizado.setdefault(clave, {"activo": clave, "ventas": 0.0, "cupones": 0.0, "amortizaciones": 0.0,
                                            "otros": 0.0})
        destino = {"Venta": "ventas", "Cupón": "cupones", "Amortización": "amortizaciones",
                   "Vencimiento": "amortizaciones"}.get(x["concepto"], "otros")
        fila[destino] += x["resultado"][moneda]
    for fila in realizado.values():
        fila["total"] = fila["ventas"] + fila["cupones"] + fila["amortizaciones"] + fila["otros"]
    no_realizado = [{"ticker": f["ticker"], "descripcion": f["descripcion"], "costo": f["costo"], "valor": f["total"],
                     "resultado": f["no_realizado"], "porcentaje": f["no_realizado"] / f["costo"] if f["costo"] else None}
                    for f in v["filas"] if "costo" in f]
    return {"realizado": sorted(realizado.values(), key=lambda x: -abs(x["total"])), "no_realizado": no_realizado,
            "total_realizado": sum(x["total"] for x in realizado.values()),
            "total_no_realizado": sum(x["resultado"] for x in no_realizado), "moneda": moneda}


def desde_foto(cartera, fecha: date) -> list[Operacion]:
    """Pasa una cartera cargada como foto (posiciones y liquidez) a operaciones: cada posición como Ingreso al cierre
    de esa fecha, la liquidez como Depósito, el money market como Suscripción y cauciones, créditos y pasivos como
    tales (Agustin, 25/11/2026)."""
    lista = []
    for p in cartera.posiciones:
        lista.append(Operacion(fecha, "Ingreso", p.ticker, p.nominales, precio_cierre(p.ticker, "pesos", fecha),
                               nota="convertida desde la foto de la cartera"))
    equivalencias = {"Liquidez": "Depósito", "Money market": "Suscripción", "Caución colocadora": "Caución colocadora",
                     "Plazo fijo": "Crédito", "Crédito": "Crédito", "Caución tomadora": "Pasivo", "Pasivo": "Pasivo"}
    for x in cartera.liquidez:
        tipo = equivalencias[x.tipo]
        vencimiento = x.vencimiento if x.vencimiento and x.vencimiento > fecha else None
        if tipo in ("Caución colocadora", "Crédito", "Pasivo") and vencimiento is None:
            vencimiento = fecha + timedelta(days=30)
        lista.append(Operacion(fecha, tipo, monto=x.monto, moneda=x.moneda, tasa=x.tasa, vencimiento=vencimiento,
                               nota=(x.descripcion or "") + (" (vencimiento supuesto a 30 días: corregilo)"
                                                             if tipo in ("Caución colocadora", "Crédito", "Pasivo")
                                                             and not (x.vencimiento and x.vencimiento > fecha) else "")))
    return lista
