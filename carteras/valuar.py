"""Valuación de una cartera con el modelo de Agustin (columnas en carteras/excel.py, COLUMNAS).

Por activo:
- TIR Spread/Nominal: la tasa propia del bono, sin proyectar nada. Tasa fija: TIR (TEA) nominal. CER: TIR real
  (CER + x). TAMAR: spread sobre la TAMAR (TNA de 30 días contra el promedio de los últimos 5 días hábiles).
  Dollar linked y hard dollar: TIR en dólares. Renta variable: vacío.
- TIR nominal en base a proyección: TIR (TEA) en pesos con los supuestos de la cartera (hoja Supuestos): CER con la
  inflación supuesta, TAMAR con la TAMAR supuesta, dollar linked con el A3500 supuesto, hard dollar con el MEP (ley
  argentina) o el CCL (ley Nueva York) supuestos. Tasa fija: su TIR. Duales: la pata que más rinde con esos supuestos.
- Nominales, precio (por 100 VN; en renta variable, por unidad), total, % de la cartera y duration (años).

Valuación (decisión de Agustin, 24/11/2026): en pesos; los hard dollar ley argentina al MEP y los ley Nueva York al
CCL (precio en dólares × ese tipo de cambio). Se puede ver en dólares MEP o CCL: todo se divide por ese tipo de cambio.
"""
from dataclasses import dataclass
from datetime import date

from datetime import timedelta

from carteras.excel import TIPOS_LIQUIDEZ, Cartera
import config
from admin_datos import precios as db_precios
from carga_datos import precios as carga_precios
from conexiones.http import ErrorAPI
from renta_fija import leer_fichas, mercado, metricas
from renta_fija.calculadoras import cer, cer_cupon, motor, tamar
from renta_fija.calculadoras import proyeccion_cer as pc

MONEDAS = {"pesos": "pesos", "mep": "dólares MEP", "ccl": "dólares CCL"}
NOMBRES_TIPO = {"LECAP": "Lecap", "BONCAP": "Boncap", "BONTE": "Bonte", "LECER": "Lecer", "BONCER": "Boncer",
                "BONO TAMAR": "Bono TAMAR", "LETRA TAMAR": "Letra TAMAR", "LETRA DL": "Letra dollar linked",
                "BONO DL": "Bono dollar linked", "BONAR": "Bonar", "GLOBAL": "Global",
                "DUAL CER/TAMAR": "Dual CER/TAMAR", "DUAL TAMAR/TASA FIJA": "Dual TAMAR/tasa fija"}
NOMBRES_RV = {"ACCIONES": "Acción", "CEDEARS": "CEDEAR", "ACCIONES-USA": "Acción EE. UU.", "FCI": "FCI", "ETF": "ETF"}
# Clasificación (Agustin, 25/11/2026): categoría (Renta Fija, Renta Variable, Derivados, Liquidez, ...) y subclase
SUBCLASE = {"tasa_fija_capitalizable": "Tasa fija", "tasa_fija_descuento": "Tasa fija", "tasa_fija_cupon": "Tasa fija",
            "cer_cero_cupon": "CER", "cer_cupon": "CER", "tamar_capitalizable": "TAMAR",
            "dolar_linked_bullet": "Dollar linked", "dolar_linked_cupon": "Dollar linked", "hard_dollar": "Hard dollar"}
SUBCLASE_RV = {"Acción": ("Renta Variable", "Acciones", "Pesos"), "CEDEAR": ("Renta Variable", "CEDEARs", "Pesos ajustables (MEP)"),
               "Acción EE. UU.": ("Renta Variable", "Acciones EE. UU.", "Dólar CCL"),
               "ETF": ("Renta Variable", "ETF", "Dólar CCL"), "FCI": ("Fondos comunes", "FCI", "Pesos")}
MONEDA_LIQUIDEZ = {"pesos": "Pesos", "mep": "Dólar MEP", "ccl": "Dólar CCL"}
ORDEN_CATEGORIAS = ["Renta Fija", "Renta Variable", "Fondos comunes", "Derivados", "Liquidez", "Créditos", "Pasivos"]
ORDEN_MONEDAS = ["Pesos", "Pesos ajustables (dólar oficial)", "Pesos ajustables (MEP)", "Dólar MEP", "Dólar CCL"]
DIAS_COBROS = 30
REFERENCIA = {"tasa_fija_capitalizable": "", "tasa_fija_descuento": "", "tasa_fija_cupon": "", "cer_cero_cupon": "CER",
              "cer_cupon": "CER", "tamar_capitalizable": "TAMAR", "dolar_linked_bullet": "USD",
              "dolar_linked_cupon": "USD", "hard_dollar": "USD"}


def precio(ticker: str, fecha_precios: date | None, avisos: list[str] | None = None) -> float:
    """Precio de mercado. Si el precio en vivo de PPI falla, usa el último cierre guardado en la base propia y lo
    anota en avisos (así una caída de PPI no frena la valuación)."""
    try:
        return mercado.precio(ticker, fecha_precios)[0]
    except ErrorAPI as e:
        if fecha_precios is not None:
            raise
        error = e
    try:
        carga_precios.actualizar(ticker, config.PPI_PLAZO)
    except (ErrorAPI, ValueError):
        pass                                            # si PPI está caído, queda lo que ya estaba guardado
    cierres = db_precios.entre(ticker, config.PPI_PLAZO)
    if not cierres:
        raise ErrorAPI(f"PPI no respondió y no hay cierres guardados de {ticker} ({str(error).splitlines()[0][:120]})")
    ultimo = cierres[-1]
    if avisos is not None:
        avisos.append(f"{ticker}: PPI no respondió el precio en vivo; se usó el cierre del {ultimo['fecha']} "
                      f"({ultimo['cierre']:,.2f}).")
    return ultimo["cierre"]


def tipos_de_cambio(fecha_precios: date | None, avisos: list[str] | None = None) -> dict[str, float]:
    """MEP y CCL implícitos del AL30 (pesos / dólares), como en las proyecciones."""
    pesos = precio("AL30", fecha_precios, avisos)
    return {"mep": pesos / precio("AL30D", fecha_precios, avisos),
            "ccl": pesos / precio("AL30C", fecha_precios, avisos)}


@dataclass
class Contexto:
    operacion: date
    liquidacion: date
    fecha_precios: date | None
    fx: dict[str, float]
    avisos: list[str]


class Proyecciones:
    """Los caminos de la cartera (inflación, TAMAR, A3500, MEP, CCL), armados una vez y solo si hacen falta."""

    def __init__(self, supuestos: dict[str, str], ctx: Contexto, hasta: date):
        self.fuentes = {v: supuestos.get(v, "rem") for v in ("inflacion", "tamar", "dolar_oficial", "mep", "ccl")}
        self.ctx, self.hasta = ctx, hasta
        self.descripciones: dict[str, str] = {}
        self._cache = {}

    def _una_vez(self, clave, armar):
        if clave not in self._cache:
            self._cache[clave] = armar()
        return self._cache[clave]

    # --- caminos ---
    def cer(self):
        def armar():
            from tools.proyeccion_cer import camino_inflacion
            hasta_mes = pc.mes_aplicado(self.hasta)
            caminos, descripcion, serie, _ = camino_inflacion(self.fuentes["inflacion"], self.ctx.liquidacion, hasta_mes,
                                                              None, self.ctx.operacion, self.ctx.fecha_precios)
            self.descripciones["inflacion"] = descripcion
            proyectado = pc.proyectar(serie, {m: v for m, (v, _) in caminos.items()}, max(self.hasta, max(serie)))
            return lambda d: serie.get(d) or proyectado[d]
        return self._una_vez("cer", armar)

    def tamar(self):
        def armar():
            from tools.proyecciones import camino_tamar
            camino, descripcion = camino_tamar(self.fuentes["tamar"], self.ctx.operacion)
            self.descripciones["tamar"] = descripcion
            return camino
        return self._una_vez("tamar", armar)

    def oficial(self):
        def armar():
            from tools.proyecciones import camino_dolar
            nivel, descripcion, _, _ = camino_dolar("oficial", self.fuentes["dolar_oficial"], self.ctx.operacion,
                                                    self.ctx.fecha_precios)
            self.descripciones["dolar_oficial"] = descripcion
            return nivel
        return self._una_vez("oficial", armar)

    def dolar(self, tipo: str):
        """MEP o CCL. Con "rem" (o "brecha"), la brecha de hoy se mantiene sobre el camino del A3500."""
        def armar():
            fuente, hoy = self.fuentes[tipo], self.ctx.fx[tipo]
            if fuente in ("rem", "brecha"):
                oficial = self.oficial()
                base = oficial(self.ctx.operacion)
                self.descripciones[tipo] = (f"{tipo.upper()} de hoy {hoy:,.2f} con la brecha constante sobre el A3500 "
                                            f"({self.descripciones.get('dolar_oficial', 'camino del oficial')})")
                return lambda d: hoy * oficial(d) / base
            from tools.proyecciones import camino_dolar
            nivel, descripcion, _, _ = camino_dolar(tipo, fuente, self.ctx.operacion, self.ctx.fecha_precios)
            self.descripciones[tipo] = descripcion
            return nivel
        return self._una_vez(tipo, armar)

    # --- TIR nominal en pesos de cada familia ---
    def tir_nominal(self, f: dict, precio: float, m: dict) -> float:
        familia, liq = f["familia"], self.ctx.liquidacion
        if familia.startswith("tasa_fija"):
            return m["tea"]
        if familia in ("cer_cero_cupon", "cer_cupon"):
            cer_en = self.cer()
            _, f2, cer_corriente = mercado.datos_cer(f, liq)
            fecha_cer = lambda p: mercado.feriados.sumar_dias_habiles(p, -cer.REZAGO_HABILES, mercado.CALENDARIO_HABILES)
            if familia == "cer_cero_cupon":
                return pc.nominal_cero_cupon(precio, f2["cer_inicial"], cer_en(fecha_cer(f["vencimiento"])), liq,
                                             f["vencimiento"])["tir"]
            ajustar = lambda d: mercado.feriados.proximo_dia_habil(d, mercado.CALENDARIO_HABILES)
            real = cer_cupon.calcular(precio, f2["cer_inicial"], cer_corriente, liq, f["pagos"], f["cupon"],
                                      f["frecuencia"], f["emision"], ajustar)
            cers = [cer_en(fecha_cer(p["fecha"])) for p in f["pagos"] if p["fecha"] > liq]
            return pc.nominal_con_cupon(precio, f2["cer_inicial"], real["flujos"], cers, liq)["tir"]
        if familia == "tamar_capitalizable":
            from tools.proyecciones import tamar_del_bono
            tamar_bono, d = tamar_del_bono(f, self.ctx.operacion, self.tamar())
            return tamar.calcular(precio, tamar_bono, f["margen"], f["emision"], f["vencimiento"], liq, d["referencia"])["tea"]
        if familia in ("dolar_linked_bullet", "dolar_linked_cupon"):
            return self._tir_en_pesos(m["flujos"], precio, self.oficial())
        if familia == "hard_dollar":
            tipo = "ccl" if f.get("ley") == "NY" else "mep"
            return self._tir_en_pesos(m["flujos"], precio * self.ctx.fx[tipo], self.dolar(tipo))
        raise ValueError(f"sin proyección para {familia}")

    def _tir_en_pesos(self, flujos_usd: list[dict], precio_pesos: float, nivel) -> float:
        flujos = [motor.Flujo(x["fecha"], x["cupon"] * nivel(x["fecha"]), x["amortizacion"] * nivel(x["fecha"]))
                  for x in flujos_usd]
        return motor.tir(flujos, precio_pesos, self.ctx.liquidacion)


def _nombre_tipo(f: dict) -> str:
    nombre = NOMBRES_TIPO.get(f.get("tipo", "").upper(), f.get("tipo", "").title() or f["familia"])
    if f["familia"] == "hard_dollar":
        nombre += " (ley NY)" if f.get("ley") == "NY" else " (ley AR)"
    return nombre


def _renta_fija(pos, fichas: list[dict], ctx: Contexto, proy: Proyecciones) -> dict:
    principal = fichas[0]
    hd = principal["familia"] == "hard_dollar"
    tipo_fx = ("ccl" if principal.get("ley") == "NY" else "mep") if hd else None
    # Hard dollar: precio en dólares (D si es ley AR, C si es ley NY), valuado al MEP o al CCL
    px = precio(pos.ticker + ({"mep": "D", "ccl": "C"}[tipo_fx] if hd else ""), ctx.fecha_precios, ctx.avisos)
    precio_pesos = px * ctx.fx[tipo_fx] if hd else px
    resultados = []
    for f in fichas:                                    # un bono común tiene una pata; un dual, dos
        m = metricas.calculadora(f, ctx.liquidacion, ctx.operacion)(px)
        resultados.append((f, m, proy.tir_nominal(f, px, m)))
    f, m, tir_proy = max(resultados, key=lambda r: r[2])   # dual: paga la pata que más rinde
    f0, m0, _ = resultados[0]                              # la tasa propia, de la primera pata del nombre
    tir_propia = m0["detalle"]["spread"] if f0["familia"] == "tamar_capitalizable" else m0["tea"]
    familia = principal["familia"]
    moneda = ("Dólar CCL" if tipo_fx == "ccl" else "Dólar MEP") if hd else \
        "Pesos ajustables (dólar oficial)" if familia.startswith("dolar_linked") else "Pesos"
    # Cobros: flujos por 100 VN en la unidad del bono, pasados a pesos de hoy (CER, A3500 o el dólar del bono)
    a_pesos = ctx.fx[tipo_fx] if hd else (m["ajuste"][1] if m.get("ajuste") else 1.0)
    unidad_pago = "USD" if hd else "$"
    cobros = []
    for x in m["flujos"]:
        if ctx.liquidacion < x["fecha"] <= ctx.operacion + timedelta(days=DIAS_COBROS) and x["total"]:
            vence = x["fecha"] >= f["vencimiento"]
            concepto = ("Vencimiento" if vence else "Cupón y amortización" if x["cupon"] and x["amortizacion"]
                        else "Amortización" if x["amortizacion"] else "Cupón")
            en_unidad = pos.nominales * x["total"] / 100
            cobros.append({"fecha": x["fecha"], "ticker": pos.ticker, "concepto": concepto,
                           "cupon": pos.nominales * x["cupon"] / 100, "amortizacion": pos.nominales * x["amortizacion"] / 100,
                           "moneda_pago": unidad_pago, "monto": en_unidad if hd else en_unidad * a_pesos,
                           "monto_pesos": en_unidad * a_pesos,
                           "nota": "" if hd or familia.startswith("tasa_fija") or familia == "tamar_capitalizable"
                           else m["ajuste"][0] if m.get("ajuste") else ""})
    return {"categoria": "Renta Fija", "subclase": "Duales" if len(fichas) > 1 else SUBCLASE[familia],
            "moneda_activo": moneda, "emisor": principal.get("emisor") or "Tesoro Nacional", "cobros": cobros,
            "pondera": True, "_legs": [(r[0], r[1]) for r in resultados], "_f": f, "_m": m, "_px": px,
            "_tipo_fx": tipo_fx, "_vencimiento": max(x["vencimiento"] for x in fichas),
            "tipo": pos.tipo or _nombre_tipo(principal),
            "descripcion": pos.descripcion or f"{_nombre_tipo(principal)} vto {principal['vencimiento']:%d/%m/%Y}",
            "ticker": pos.ticker, "referencia": REFERENCIA[f0["familia"]], "tir_propia": tir_propia,
            "tir_proyectada": tir_proy, "nominales": pos.nominales, "precio_pesos": precio_pesos,
            "total_pesos": pos.nominales * precio_pesos / 100, "duration": m["duration"], "renta_fija": True,
            "pata": f["familia"] if len(fichas) > 1 else None}


def _renta_variable(pos, ctx: Contexto) -> dict:
    datos = carga_precios.registrar(pos.ticker)
    px = precio(pos.ticker, ctx.fecha_precios, ctx.avisos)
    tipo = NOMBRES_RV.get(str(datos.get("tipo", "")).upper(), str(datos.get("tipo", "")).title())
    categoria, subclase, moneda = SUBCLASE_RV.get(tipo, ("Renta Variable", tipo or "Otros", "Pesos"))
    descripcion = datos.get("descripcion") or pos.ticker
    return {"categoria": categoria, "subclase": subclase, "moneda_activo": moneda, "emisor": descripcion, "cobros": [],
            "pondera": False, "tipo": pos.tipo or tipo, "descripcion": pos.descripcion or datos.get("descripcion") or pos.ticker,
            "ticker": pos.ticker, "referencia": "", "tir_propia": None, "tir_proyectada": None, "nominales": pos.nominales,
            "precio_pesos": px, "total_pesos": pos.nominales * px, "duration": None, "renta_fija": False,
            "pata": None}


def tasa_liquidez(x, operacion: date) -> tuple[float, float]:
    """TEA y duration de una fila de liquidez. La liquidez a la vista (o cualquier tipo sin tasa) rinde 0 con duration
    0 (decisión de Agustin). Con vencimiento: TEA = (1 + TNA × plazo/365)^(365/plazo) − 1 y duration = plazo/365.
    Sin vencimiento (money market): capitalización diaria, (1 + TNA/365)^365 − 1, duration 0."""
    if x.tipo == "Liquidez" or not x.tasa:
        return 0.0, 0.0
    if x.vencimiento and x.vencimiento > operacion:
        plazo = (x.vencimiento - operacion).days
        return (1 + x.tasa * plazo / 365) ** (365 / plazo) - 1, plazo / 365
    return (1 + x.tasa / 365) ** 365 - 1, 0.0


def _liquidez(x, ctx: Contexto) -> dict:
    categoria, signo = TIPOS_LIQUIDEZ[x.tipo]
    tea, duration = tasa_liquidez(x, ctx.operacion)
    fx = 1.0 if x.moneda == "pesos" else ctx.fx[x.moneda]
    cobros = []
    if x.vencimiento and ctx.operacion <= x.vencimiento <= ctx.operacion + timedelta(days=DIAS_COBROS):
        final = x.monto * (1 + (x.tasa or 0) * max((x.vencimiento - ctx.operacion).days, 0) / 365)
        cobros.append({"fecha": x.vencimiento, "ticker": x.descripcion or x.tipo,
                       "concepto": "Vencimiento" + (" (a pagar)" if signo < 0 else ""), "cupon": final - x.monto,
                       "amortizacion": x.monto, "moneda_pago": "$" if x.moneda == "pesos" else "USD",
                       "monto": signo * final, "monto_pesos": signo * final * fx, "nota": "con la tasa cargada"})
    return {"categoria": categoria, "subclase": x.tipo, "moneda_activo": MONEDA_LIQUIDEZ[x.moneda],
            "emisor": x.descripcion or x.tipo, "cobros": cobros, "pondera": True, "tipo": x.tipo,
            "descripcion": x.descripcion or x.tipo, "ticker": "", "referencia": "", "tir_propia": tea,
            "tir_proyectada": tea, "nominales": signo * x.monto, "precio_pesos": None, "total_pesos": signo * x.monto * fx,
            "duration": duration, "renta_fija": False, "pata": None, "liquidez": True, "_liq": x}


def cuadros(filas: list[dict], total: float) -> dict:
    """Cuadros de composición en la moneda de la vista: por categoría y subclase, por moneda, subclase × moneda y
    por emisor. Cada uno con total y % del patrimonio."""
    peso = lambda x: x / total if total else None
    suma = {}
    for f in filas:
        suma.setdefault((f["categoria"], f["subclase"]), 0.0)
        suma[(f["categoria"], f["subclase"])] += f["total"]
    orden_cat = lambda c: ORDEN_CATEGORIAS.index(c) if c in ORDEN_CATEGORIAS else len(ORDEN_CATEGORIAS)
    categoria = []
    for cat in sorted({c for c, _ in suma}, key=orden_cat):
        subs = sorted(((s, t) for (c, s), t in suma.items() if c == cat), key=lambda x: -abs(x[1]))
        total_cat = sum(t for _, t in subs)
        categoria.append({"categoria": cat, "subclase": None, "total": total_cat, "peso": peso(total_cat)})
        categoria += [{"categoria": cat, "subclase": s, "total": t, "peso": peso(t)} for s, t in subs]
    por_moneda = {}
    for f in filas:
        por_moneda[f["moneda_activo"]] = por_moneda.get(f["moneda_activo"], 0.0) + f["total"]
    orden_mon = lambda m: ORDEN_MONEDAS.index(m) if m in ORDEN_MONEDAS else len(ORDEN_MONEDAS)
    monedas = sorted(por_moneda, key=orden_mon)
    cruce = {}
    for f in filas:
        fila = cruce.setdefault((f["categoria"], f["subclase"]), {m: 0.0 for m in monedas})
        fila[f["moneda_activo"]] += f["total"]
    por_emisor = {}
    for f in filas:
        por_emisor[f["emisor"]] = por_emisor.get(f["emisor"], 0.0) + f["total"]
    return {"categoria": categoria,
            "moneda": [{"moneda": m, "total": por_moneda[m], "peso": peso(por_moneda[m])} for m in monedas],
            "monedas": monedas,
            "clase_moneda": [{"categoria": c, "subclase": s, **valores, "total": sum(valores.values()),
                              "peso": peso(sum(valores.values()))}
                             for (c, s), valores in sorted(cruce.items(), key=lambda x: (orden_cat(x[0][0]), -abs(sum(x[1].values()))))],
            "emisor": [{"emisor": e, "total": t, "peso": peso(t)}
                       for e, t in sorted(por_emisor.items(), key=lambda x: -abs(x[1]))]}


def valuar(cartera: Cartera, moneda: str = "pesos", fecha: date | None = None) -> dict:
    moneda = moneda.lower().strip()
    if moneda not in MONEDAS:
        raise ValueError(f"Moneda desconocida '{moneda}'. Opciones: {', '.join(MONEDAS)}.")
    operacion, liquidacion, fecha_precios = mercado.contexto(fecha)
    avisos_precios: list[str] = []
    try:
        fx = tipos_de_cambio(fecha_precios, avisos_precios)
    except ErrorAPI as e:
        raise ValueError(f"no se pudo armar el MEP y el CCL del AL30: {str(e).splitlines()[0]}") from None
    ctx = Contexto(operacion, liquidacion, fecha_precios, fx, avisos_precios)
    fichas_de = {p.ticker: [f for f in leer_fichas.fichas_de(p.ticker) if f["familia"] in metricas.UNIDAD]
                 for p in cartera.posiciones}
    vencimientos = [f["vencimiento"] for lista in fichas_de.values() for f in lista]
    proy = Proyecciones(cartera.supuestos, ctx, max(vencimientos, default=operacion))
    filas, avisos = [], []
    for pos in cartera.posiciones:
        fichas = fichas_de[pos.ticker]
        if fichas and all(f["vencimiento"] <= liquidacion for f in fichas):
            avisos.append(f"{pos.ticker}: ya venció; no se valúa.")
            continue
        try:
            fila = _renta_fija(pos, [f for f in fichas if f["vencimiento"] > liquidacion], ctx, proy) if fichas \
                else _renta_variable(pos, ctx)
        except (ErrorAPI, ValueError, KeyError, ZeroDivisionError) as e:
            avisos.append(f"{pos.ticker}: no se pudo valuar ({str(e).splitlines()[0][:160]}).")
            continue
        filas.append(fila)
    for x in cartera.liquidez:
        filas.append(_liquidez(x, ctx))
    divisor = 1.0 if moneda == "pesos" else ctx.fx[moneda]
    total = sum(f["total_pesos"] for f in filas)
    for f in filas:
        f["precio"] = f["precio_pesos"] / divisor if f["precio_pesos"] is not None else None
        f["total"] = f["total_pesos"] / divisor
        f["peso"] = f["total_pesos"] / total if total else None
    rf = [f for f in filas if f["renta_fija"]]
    total_rf = sum(f["total_pesos"] for f in rf)
    # TIR y duration ponderadas por monto: renta fija, liquidez, créditos y pasivos (estos con monto negativo).
    # La renta variable no tiene TIR ni duration y queda afuera.
    ponderan = [f for f in filas if f["pondera"]]
    def ponderar(campo):
        con_dato = [f for f in ponderan if f[campo] is not None]
        base = sum(f["total_pesos"] for f in con_dato)
        return sum(f[campo] * f["total_pesos"] for f in con_dato) / base if con_dato and base else None
    por_categoria = lambda cat: sum(f["total_pesos"] for f in filas if f["categoria"] == cat) / divisor
    totales = {"total": total / divisor, "total_rf": total_rf / divisor, "total_rv": por_categoria("Renta Variable"),
               "peso_rf": total_rf / total if total else None,
               "peso_rv": por_categoria("Renta Variable") * divisor / total if total else None,
               "total_liquidez": por_categoria("Liquidez"), "total_creditos": por_categoria("Créditos"),
               "total_pasivos": por_categoria("Pasivos"),
               "tir_proyectada_rf": ponderar("tir_proyectada"), "duration_rf": ponderar("duration")}
    cobros = sorted((c | {"monto_vista": c["monto_pesos"] / divisor} for f in filas for c in f["cobros"]),
                    key=lambda c: (c["fecha"], c["ticker"]))
    nota = (f"Liquidación {liquidacion:%d/%m/%Y}. Hard dollar ley AR al MEP ({ctx.fx['mep']:,.2f}) y ley NY al CCL "
            f"({ctx.fx['ccl']:,.2f}), implícitos del AL30. Precios por 100 VN (renta variable, por unidad)"
            + ("." if moneda == "pesos" else f"; todo convertido a {MONEDAS[moneda]}."))
    supuestos = {v: proy.descripciones[v] for v in ("inflacion", "tamar", "dolar_oficial", "mep", "ccl")
                 if v in proy.descripciones}
    return {"nombre": cartera.nombre, "fecha": operacion, "moneda": moneda, "nombre_moneda": MONEDAS[moneda],
            "filas": filas, "totales": totales, "fx": ctx.fx, "supuestos": supuestos, "cobros": cobros,
            "cuadros": cuadros(filas, total / divisor), "dias_cobros": DIAS_COBROS,
            "nota_valuacion": nota, "liquidacion": liquidacion, "avisos": avisos_precios + avisos, "_ctx": ctx}


def _pct(x: float | None, referencia: str = "") -> str:
    if x is None:
        return ""
    return f"{referencia} + {x:.2%}" if referencia else f"{x:.2%}"


def texto(v: dict) -> str:
    """La cartera valuada como tabla de texto (para la terminal y el agente)."""
    lineas = [f"Cartera {v['nombre']} – {v['fecha']:%d/%m/%Y} – valuada en {v['nombre_moneda']} – calculadora de Finianz",
              v["nota_valuacion"],
              " | ".join(["Tipo Activo", "Descripcion", "Ticker", "Tir Spread/Nominal", "Tir Nominal en base a proyeccion",
                          "Nominales", "Precio", "Total", "% Cartera", "Duration Activo"])]
    for f in v["filas"]:
        lineas.append(" | ".join([f["tipo"], f["descripcion"], f["ticker"], _pct(f["tir_propia"], f["referencia"]),
                                  _pct(f["tir_proyectada"]), f"{f['nominales']:,.0f}",
                                  f"{f['precio']:,.2f}" if f["precio"] is not None else "",
                                  f"{f['total']:,.2f}", _pct(f["peso"]),
                                  f"{f['duration']:.2f}" if f["duration"] is not None else ""]))
    t = v["totales"]
    lineas.append(f"Patrimonio: {t['total']:,.2f} {v['nombre_moneda']}")
    lineas.append(f"TIR nominal proyectada ponderada {_pct(t['tir_proyectada_rf'])} | duration ponderada "
                  + (f"{t['duration_rf']:.2f} años" if t["duration_rf"] is not None else "–")
                  + " (renta fija, liquidez, créditos y pasivos; la liquidez sin colocar rinde 0 con duration 0)")
    c = v["cuadros"]
    lineas.append("Por categoría y subclase: " + " | ".join(
        f"{x['categoria'] if x['subclase'] is None else '  ' + x['subclase']}: {x['total']:,.2f} ({_pct(x['peso'])})"
        for x in c["categoria"]))
    lineas.append("Por moneda: " + " | ".join(f"{x['moneda']}: {x['total']:,.2f} ({_pct(x['peso'])})" for x in c["moneda"]))
    lineas.append("Por emisor: " + " | ".join(f"{x['emisor']}: {x['total']:,.2f} ({_pct(x['peso'])})" for x in c["emisor"]))
    if v["cobros"]:
        lineas.append(f"Cobros de los próximos {v['dias_cobros']} días: " + " | ".join(
            f"{x['fecha']:%d/%m/%Y} {x['ticker']} {x['concepto'].lower()} {x['moneda_pago']} {x['monto']:,.2f}"
            for x in v["cobros"]))
    duales = [f for f in v["filas"] if f["pata"]]
    if duales:
        lineas.append("Duales: la TIR proyectada es la de la pata que más rinde con los supuestos ("
                      + ", ".join(f"{f['ticker']}: {f['pata'].replace('_', ' ')}" for f in duales) + ").")
    if v["supuestos"]:
        lineas.append("Supuestos de la proyección: " + " | ".join(f"{k}: {d}" for k, d in v["supuestos"].items()))
    for aviso in v["avisos"]:
        lineas.append("Aviso: " + aviso)
    return "\n".join(lineas)
