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

from carteras.excel import Cartera
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
REFERENCIA = {"tasa_fija_capitalizable": "", "tasa_fija_descuento": "", "tasa_fija_cupon": "", "cer_cero_cupon": "CER",
              "cer_cupon": "CER", "tamar_capitalizable": "TAMAR", "dolar_linked_bullet": "USD",
              "dolar_linked_cupon": "USD", "hard_dollar": "USD"}


def tipos_de_cambio(fecha_precios: date | None) -> dict[str, float]:
    """MEP y CCL implícitos del AL30 (pesos / dólares), como en las proyecciones."""
    pesos = mercado.precio("AL30", fecha_precios)[0]
    return {"mep": pesos / mercado.precio("AL30D", fecha_precios)[0],
            "ccl": pesos / mercado.precio("AL30C", fecha_precios)[0]}


@dataclass
class Contexto:
    operacion: date
    liquidacion: date
    fecha_precios: date | None
    fx: dict[str, float]


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
    precio = mercado.precio(pos.ticker + ({"mep": "D", "ccl": "C"}[tipo_fx] if hd else ""), ctx.fecha_precios)[0]
    precio_pesos = precio * ctx.fx[tipo_fx] if hd else precio
    resultados = []
    for f in fichas:                                    # un bono común tiene una pata; un dual, dos
        m = metricas.calculadora(f, ctx.liquidacion, ctx.operacion)(precio)
        resultados.append((f, m, proy.tir_nominal(f, precio, m)))
    f, m, tir_proy = max(resultados, key=lambda r: r[2])   # dual: paga la pata que más rinde
    f0, m0, _ = resultados[0]                              # la tasa propia, de la primera pata del nombre
    tir_propia = m0["detalle"]["spread"] if f0["familia"] == "tamar_capitalizable" else m0["tea"]
    return {"tipo": pos.tipo or _nombre_tipo(principal),
            "descripcion": pos.descripcion or f"{_nombre_tipo(principal)} vto {principal['vencimiento']:%d/%m/%Y}",
            "ticker": pos.ticker, "referencia": REFERENCIA[f0["familia"]], "tir_propia": tir_propia,
            "tir_proyectada": tir_proy, "nominales": pos.nominales, "precio_pesos": precio_pesos,
            "total_pesos": pos.nominales * precio_pesos / 100, "duration": m["duration"], "renta_fija": True,
            "pata": f["familia"] if len(fichas) > 1 else None}


def _renta_variable(pos, ctx: Contexto) -> dict:
    datos = carga_precios.registrar(pos.ticker)
    precio = mercado.precio(pos.ticker, ctx.fecha_precios)[0]
    tipo = NOMBRES_RV.get(str(datos.get("tipo", "")).upper(), str(datos.get("tipo", "")).title())
    return {"tipo": pos.tipo or tipo, "descripcion": pos.descripcion or datos.get("descripcion") or pos.ticker,
            "ticker": pos.ticker, "referencia": "", "tir_propia": None, "tir_proyectada": None, "nominales": pos.nominales,
            "precio_pesos": precio, "total_pesos": pos.nominales * precio, "duration": None, "renta_fija": False,
            "pata": None}


def valuar(cartera: Cartera, moneda: str = "pesos", fecha: date | None = None) -> dict:
    moneda = moneda.lower().strip()
    if moneda not in MONEDAS:
        raise ValueError(f"Moneda desconocida '{moneda}'. Opciones: {', '.join(MONEDAS)}.")
    operacion, liquidacion, fecha_precios = mercado.contexto(fecha)
    ctx = Contexto(operacion, liquidacion, fecha_precios, tipos_de_cambio(fecha_precios))
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
    divisor = 1.0 if moneda == "pesos" else ctx.fx[moneda]
    total = sum(f["total_pesos"] for f in filas)
    for f in filas:
        f["precio"] = f["precio_pesos"] / divisor
        f["total"] = f["total_pesos"] / divisor
        f["peso"] = f["total_pesos"] / total if total else None
    rf = [f for f in filas if f["renta_fija"]]
    total_rf = sum(f["total_pesos"] for f in rf)
    ponderar = lambda campo: (sum(f[campo] * f["total_pesos"] for f in rf if f[campo] is not None)
                              / sum(f["total_pesos"] for f in rf if f[campo] is not None)) if any(f[campo] is not None for f in rf) else None
    totales = {"total": total / divisor, "total_rf": total_rf / divisor, "total_rv": (total - total_rf) / divisor,
               "peso_rf": total_rf / total if total else None, "peso_rv": (total - total_rf) / total if total else None,
               "tir_proyectada_rf": ponderar("tir_proyectada"), "duration_rf": ponderar("duration")}
    nota = (f"Liquidación {liquidacion:%d/%m/%Y}. Hard dollar ley AR al MEP ({ctx.fx['mep']:,.2f}) y ley NY al CCL "
            f"({ctx.fx['ccl']:,.2f}), implícitos del AL30. Precios por 100 VN (renta variable, por unidad)"
            + ("." if moneda == "pesos" else f"; todo convertido a {MONEDAS[moneda]}."))
    supuestos = {v: proy.descripciones[v] for v in ("inflacion", "tamar", "dolar_oficial", "mep", "ccl")
                 if v in proy.descripciones}
    return {"nombre": cartera.nombre, "fecha": operacion, "moneda": moneda, "nombre_moneda": MONEDAS[moneda],
            "filas": filas, "totales": totales, "fx": ctx.fx, "supuestos": supuestos, "avisos": avisos,
            "nota_valuacion": nota, "liquidacion": liquidacion}


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
                                  _pct(f["tir_proyectada"]), f"{f['nominales']:,.0f}", f"{f['precio']:,.2f}",
                                  f"{f['total']:,.2f}", _pct(f["peso"]),
                                  f"{f['duration']:.2f}" if f["duration"] is not None else ""]))
    t = v["totales"]
    lineas.append(f"Total cartera: {t['total']:,.2f} {v['nombre_moneda']}")
    lineas.append(f"Renta fija: {t['total_rf']:,.2f} ({_pct(t['peso_rf'])}) | TIR nominal proyectada ponderada "
                  f"{_pct(t['tir_proyectada_rf'])} | duration ponderada "
                  + (f"{t['duration_rf']:.2f} años" if t["duration_rf"] is not None else "–"))
    if t["total_rv"]:
        lineas.append(f"Renta variable: {t['total_rv']:,.2f} ({_pct(t['peso_rv'])})")
    duales = [f for f in v["filas"] if f["pata"]]
    if duales:
        lineas.append("Duales: la TIR proyectada es la de la pata que más rinde con los supuestos ("
                      + ", ".join(f"{f['ticker']}: {f['pata'].replace('_', ' ')}" for f in duales) + ").")
    if v["supuestos"]:
        lineas.append("Supuestos de la proyección: " + " | ".join(f"{k}: {d}" for k, d in v["supuestos"].items()))
    for aviso in v["avisos"]:
        lineas.append("Aviso: " + aviso)
    return "\n".join(lineas)
