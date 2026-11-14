"""Caminos proyectados de la TAMAR y de los tipos de cambio (oficial A3500, MEP y CCL), con escenarios.

Fuentes de la TAMAR (TNA en fracción):
- "actual": el promedio de los últimos 5 días hábiles publicados, plano (lo que usa la calculadora TAMAR).
- "rem": la mediana mensual del último REM en los meses que trae y, después, su valor a 12 meses sin cambios.
- "tna:<tasa>": una TNA plana (ej.: "tna:24%").
- "escenario:<nombre>": renta_fija/escenarios/tamar.toml.

Fuentes del tipo de cambio (pesos por dólar), partiendo del valor de hoy:
- Oficial (A3500): "rem" (promedios mensuales, a 12 meses y de diciembre del REM, a mitad de mes),
  "breakeven" (el A3500 implícito de los dollar linked contra la tasa fija), "mensual:<tasa>" (devaluación
  mensual plana) o "escenario:<nombre>" (renta_fija/escenarios/dolar_oficial.toml).
- MEP y CCL: "mensual:<tasa>" o "escenario:<nombre>" (dolar_mep.toml, dolar_ccl.toml). El valor de hoy es el
  implícito del AL30 (precio en pesos / precio en dólares MEP o cable).
Entre puntos, crecimiento geométrico; después del último, sigue con la variación mensual del último tramo
(o la que indique el escenario en "resto").
"""
import math
import tomllib
from datetime import date, timedelta
from pathlib import Path

from admin_datos import rem as db_rem
from admin_datos import series as db_series
from conexiones.http import ErrorAPI
from renta_fija.calculadoras import breakeven as be
from tools import bonos

ESCENARIOS_DIR = Path(__file__).resolve().parent.parent / "renta_fija" / "escenarios"
ARCHIVOS = {"tamar": "tamar.toml", "oficial": "dolar_oficial.toml", "mep": "dolar_mep.toml", "ccl": "dolar_ccl.toml"}
TIPOS_DOLAR = {"oficial": "A3500", "mep": "MEP", "ccl": "CCL"}


def leer_tasa(texto: str) -> float:
    """"24%", "24" o "0.24" → 0,24 (con % o desde 1 se toma como porcentaje)."""
    limpio = float(texto.strip().replace("%", "").replace(",", "."))
    return limpio / 100 if "%" in texto or limpio >= 1 else limpio


def leer_variacion(texto: str) -> float:
    """Variación mensual: "2%", "2", "1.5" o "0.02" (con % o desde 0,2 se toma como porcentaje)."""
    limpio = float(texto.strip().replace("%", "").replace(",", "."))
    return limpio / 100 if "%" in texto or limpio >= 0.2 else limpio


def parsear_camino(texto: str) -> list[tuple[str, str]]:
    """Camino escrito en la consulta: "camino:2026-12=1.8%;2027-01=1.7%;2027=20%;resto=1%" → [(clave, valor)].
    Claves: AAAA-MM (un mes), AAAA (un año) o resto. Se separa con punto y coma."""
    cuerpo = texto.split(":", 1)[1] if texto.startswith("camino:") else texto
    pares = []
    for parte in filter(None, (p.strip() for p in cuerpo.split(";"))):
        if "=" not in parte:
            raise ValueError(f"En el camino, '{parte}' tiene que ser clave=valor (ej.: 2027-01=1.7%).")
        clave, valor = (x.strip() for x in parte.split("=", 1))
        if not (clave == "resto" or (len(clave) == 7 and clave[4] == "-" and clave[:4].isdigit()) or
                (len(clave) == 4 and clave.isdigit())):
            raise ValueError(f"Clave '{clave}' inválida en el camino: usá AAAA-MM, AAAA o resto.")
        pares.append((clave, valor))
    if not pares:
        raise ValueError("El camino está vacío.")
    return pares


def _mes_de(clave: str) -> tuple[int, int]:
    return int(clave[:4]), int(clave[5:7])


def escenarios(variable: str) -> dict[str, dict]:
    """Escenarios de 'tamar', 'oficial', 'mep' o 'ccl': {nombre: {descripcion, mensual, nivel, resto}}.
    mensual: {(año, mes): valor} (TNA para la TAMAR; variación mensual para el dólar); nivel: {(año, mes): $};
    resto: lo que sigue después del último mes (TNA o variación mensual)."""
    ruta = ESCENARIOS_DIR / ARCHIVOS[variable]
    if not ruta.exists():
        return {}
    with open(ruta, "rb") as archivo:
        datos = tomllib.load(archivo)
    salida = {}
    for e in datos.get("escenario", []):
        mes = lambda k: (int(k[:4]), int(k[5:7]))
        salida[e["nombre"]] = {"descripcion": e.get("descripcion", ""),
                               "mensual": {mes(k): float(v) for k, v in e.get("mensual", {}).items()},
                               "nivel": {mes(k): float(v) for k, v in e.get("nivel", {}).items()},
                               "resto": float(e["resto"]) if "resto" in e else None}
    return salida


def _escenario(variable: str, fuente: str) -> tuple[str, dict]:
    nombre = fuente.split(":", 1)[1]
    todos = escenarios(variable)
    if nombre not in todos:
        raise ValueError(f"No existe el escenario '{nombre}' de {variable}. Cargados: {', '.join(todos) or 'ninguno'} "
                         f"(renta_fija/escenarios/{ARCHIVOS[variable]}).")
    return nombre, todos[nombre]


# --- TAMAR ---

def camino_tamar(fuente: str, operacion: date):
    """(función mes -> TNA, descripción)."""
    if fuente == "actual":
        publicadas = db_series.entre("TAMAR", None, operacion.isoformat())[-5:]
        if len(publicadas) < 5:
            raise ErrorAPI("no hay suficientes datos de TAMAR en la base.")
        valor = sum(p["valor"] for p in publicadas) / 500
        return (lambda mes: valor), f"TAMAR actual plana: {bonos._pct(valor)} (últimos 5 días hábiles publicados)"
    if fuente == "rem":
        relevamiento = db_rem.ultimo()
        mensual = db_rem.por_mes("TAMAR", relevamiento, incluir_anuales=False) if relevamiento else {}
        doce = db_rem.valores("TAMAR", relevamiento).get("prox12") if relevamiento else None
        if not mensual or doce is None:
            raise ValueError("No hay REM cargado con TAMAR (fuentes/rem/).")
        return (be.camino_con_resto({m: v / 100 for m, v in mensual.items()}, doce / 100),
                f"REM {relevamiento}: TAMAR mensual de {_mes(min(mensual))} a {_mes(max(mensual))} y después la de 12 meses "
                f"({bonos._pct(doce / 100)})")
    if fuente.startswith("tna:"):
        valor = leer_tasa(fuente.split(":", 1)[1])
        return (lambda mes: valor), f"TAMAR plana de {bonos._pct(valor)} TNA"
    if fuente.startswith("escenario:"):
        nombre, e = _escenario("tamar", fuente)
        if not e["mensual"]:
            raise ValueError(f"El escenario '{nombre}' no tiene meses.")
        resto = e["resto"] if e["resto"] is not None else e["mensual"][max(e["mensual"])]
        return be.camino_con_resto(e["mensual"], resto), f"escenario de TAMAR '{nombre}': {e['descripcion']}"
    if fuente.startswith("camino:"):
        pares = parsear_camino(fuente)
        mensual = {_mes_de(c): leer_tasa(v) for c, v in pares if len(c) == 7}
        resto = next((leer_tasa(v) for c, v in pares if c == "resto"), None)
        if not mensual:
            if resto is None:
                raise ValueError("El camino de TAMAR necesita meses (AAAA-MM=TNA) o resto.")
            return (lambda mes: resto), f"TAMAR plana de {bonos._pct(resto)} TNA (camino indicado)"
        resto = resto if resto is not None else mensual[max(mensual)]
        return (be.camino_con_resto(mensual, resto),
                "camino de TAMAR indicado: " + ", ".join(f"{_mes(m)} {bonos._pct(v)}" for m, v in sorted(mensual.items()))
                + f"; después {bonos._pct(resto)}")
    raise ValueError("Fuente de TAMAR desconocida. Opciones: actual, rem, tna:<tasa>, camino:<meses>, escenario:<nombre>.")


def tamar_del_bono(f: dict, operacion: date, camino) -> tuple[float, dict]:
    """TAMAR promedio de la ventana del bono: lo publicado más los días por publicar con el camino."""
    d = bonos._datos_tamar(f, operacion)
    dias = bonos.feriados.dias_habiles_entre(d["desde_estimar"], d["fin"], bonos.CALENDARIO_HABILES)
    valores = [camino((x.year, x.month)) for x in dias]
    total = len(d["conocidas"]) + len(valores)
    return (sum(d["conocidas"]) + sum(valores)) / total, d


# --- Tipo de cambio ---

def nivel_hoy(tipo: str, operacion: date, fecha_precios: date | None) -> tuple[float, str]:
    if tipo == "oficial":
        valor, fecha_tc, estimado = bonos._a3500(operacion)
        return valor, f"A3500 del {fecha_tc}{' (estimado)' if estimado else ''}"
    pesos, _ = bonos._precio("AL30", fecha_precios)
    dolares, _ = bonos._precio("AL30" + ("D" if tipo == "mep" else "C"), fecha_precios)
    return pesos / dolares, f"{TIPOS_DOLAR[tipo]} implícito del AL30 ({pesos:,.2f} / {dolares:,.2f})"


def _extender(puntos: list[tuple[date, float]], resto_mensual: float | None):
    """Función fecha -> nivel: geométrica entre puntos; después del último, la variación mensual 'resto' (o la
    del último tramo)."""
    puntos = sorted(puntos)
    if resto_mensual is None:
        if len(puntos) >= 2:
            (d0, v0), (d1, v1) = puntos[-2], puntos[-1]
            resto_mensual = (v1 / v0) ** (30.4375 / max((d1 - d0).days, 1)) - 1
        else:
            resto_mensual = 0.0

    def nivel(dia: date) -> float:
        if dia <= puntos[0][0]:
            return puntos[0][1]
        if dia >= puntos[-1][0]:
            return puntos[-1][1] * (1 + resto_mensual) ** ((dia - puntos[-1][0]).days / 30.4375)
        return be.interpolar_log(puntos, dia)
    return nivel


def camino_dolar(tipo: str, fuente: str, operacion: date, fecha_precios: date | None = None, curvas: dict | None = None):
    """(función fecha -> pesos por dólar, descripción, nivel de hoy, de dónde sale el de hoy)."""
    if tipo not in TIPOS_DOLAR:
        raise ValueError("Tipo de dólar desconocido. Opciones: oficial, mep, ccl.")
    if tipo != "oficial" and not fuente.startswith(("mensual:", "escenario:", "camino:")):
        raise ValueError(f"Fuente de {TIPOS_DOLAR[tipo]} desconocida. Opciones: mensual:<tasa>, camino:<meses>, "
                         "escenario:<nombre> (el REM y el breakeven son solo para el oficial).")
    hoy, origen_hoy = nivel_hoy(tipo, operacion, fecha_precios)
    if fuente.startswith("mensual:"):
        v = leer_variacion(fuente.split(":", 1)[1])
        return _extender([(operacion, hoy)], v), f"{TIPOS_DOLAR[tipo]}: variación mensual plana de {bonos._pct(v)}", hoy, origen_hoy
    if fuente == "rem" and tipo == "oficial":
        relevamiento = db_rem.ultimo()
        tc = db_rem.por_mes("TIPO_CAMBIO", relevamiento, incluir_proximos=True) if relevamiento else {}
        if not tc:
            raise ValueError("No hay REM cargado con tipo de cambio (fuentes/rem/).")
        # El mes en curso no se usa: el REM lo estimó antes y hoy ya está el dato real
        puntos = [(operacion, hoy)] + [(date(a, m, 15), v) for (a, m), v in tc.items() if (a, m) > (operacion.year, operacion.month)]
        return (_extender(puntos, None), f"REM {relevamiento}: tipo de cambio esperado (promedios mensuales a mitad de mes, "
                f"a 12 meses y de diciembre); después de {_mes(max(tc))}, la variación del último tramo", hoy, origen_hoy)
    if fuente == "breakeven" and tipo == "oficial":
        from tools import breakevens
        liquidacion = bonos.feriados.sumar_dias_habiles(operacion, bonos.PLAZO_LIQUIDACION, "BYMA")
        if curvas is None:
            curvas, _, _ = breakevens._curvas(operacion, liquidacion, fecha_precios,
                                              {"tasa_fija_capitalizable", "tasa_fija_cupon", "dolar_linked_bullet"})
        filas = [f for f in be.cruzar(curvas["dl"], curvas["tasa_fija"], be.devaluacion) if f["acumulado"] is not None]
        if not filas:
            raise ValueError("No alcanzan los dollar linked y la tasa fija con precio para el breakeven.")
        puntos = [(operacion, hoy)] + [(f["vencimiento"], hoy * (1 + f["acumulado"])) for f in filas]
        return (_extender(puntos, None), "breakeven: el A3500 implícito de cada dollar linked contra la tasa fija; después "
                "del último, la variación del último tramo", hoy, origen_hoy)
    if fuente.startswith(("escenario:", "camino:")):
        if fuente.startswith("escenario:"):
            nombre, e = _escenario(tipo, fuente)
            descripcion = f"escenario de {TIPOS_DOLAR[tipo]} '{nombre}': {e['descripcion']}"
        else:
            pares = parsear_camino(fuente)
            e = {"nivel": {_mes_de(c): float(v.replace(",", ".")) for c, v in pares if len(c) == 7 and "%" not in v},
                 "mensual": {_mes_de(c): leer_variacion(v) for c, v in pares if len(c) == 7 and "%" in v},
                 "resto": next((leer_variacion(v) for c, v in pares if c == "resto"), None)}
            descripcion = (f"camino de {TIPOS_DOLAR[tipo]} indicado: "
                           + ", ".join(f"{_mes(m)} ${v:,.0f}" for m, v in sorted(e["nivel"].items()))
                           + (", " if e["nivel"] and e["mensual"] else "")
                           + ", ".join(f"{_mes(m)} {bonos._pct(v)}" for m, v in sorted(e["mensual"].items()))
                           + (f"; después {bonos._pct(e['resto'])} mensual" if e["resto"] is not None else ""))
        puntos, nivel, mes = [(operacion, hoy)], hoy, (operacion.year, operacion.month)
        ultimo = max([*e["mensual"], *e["nivel"]], default=None)
        while ultimo and mes <= ultimo:
            if mes in e["nivel"]:
                nivel = e["nivel"][mes]
            elif mes in e["mensual"]:
                nivel = nivel * (1 + e["mensual"][mes])
            else:
                mes = (mes[0] + mes[1] // 12, mes[1] % 12 + 1)
                continue
            dia = date(mes[0], mes[1], 15)
            if dia > operacion:
                puntos.append((dia, nivel))
            mes = (mes[0] + mes[1] // 12, mes[1] % 12 + 1)
        return _extender(puntos, e["resto"]), descripcion, hoy, origen_hoy
    opciones = ("rem, breakeven, mensual:<tasa>, camino:<meses>, escenario:<nombre>" if tipo == "oficial"
                else "mensual:<tasa>, camino:<meses>, escenario:<nombre>")
    raise ValueError(f"Fuente de {TIPOS_DOLAR[tipo]} desconocida. Opciones: {opciones}.")


def _mes(mes: tuple[int, int]) -> str:
    return f"{mes[1]:02d}/{mes[0]}"


# --- Herramientas ---

def _contexto(fecha: str | None):
    operacion = date.fromisoformat(fecha) if fecha else date.today()
    bonos._asegurar_feriados(operacion, operacion + timedelta(days=365 * 6))
    liquidacion = bonos.feriados.sumar_dias_habiles(operacion, bonos.PLAZO_LIQUIDACION, "BYMA")
    return operacion, liquidacion, (operacion if fecha else None)


def _tasa_fija(operacion, liquidacion, fecha_precios, curvas=None):
    from tools import breakevens
    if curvas is None:
        curvas, _, _ = breakevens._curvas(operacion, liquidacion, fecha_precios, {"tasa_fija_capitalizable", "tasa_fija_cupon"})
    return [(p["x"], p["tea"]) for p in curvas["tasa_fija"]]


def _comparar(puntos_tf, dias) -> str:
    tf = be.interpolar(puntos_tf, dias)
    return bonos._pct(tf) if tf is not None else "fuera de la curva"


def proyectar_tamar(fuente: str = "rem", ticker: str | None = None, fecha: str | None = None) -> str:
    from renta_fija import leer_fichas as fichas
    from renta_fija.calculadoras import tamar
    try:
        operacion, liquidacion, fecha_precios = _contexto(fecha)
        camino, descripcion = camino_tamar(fuente, operacion)
        lista = [f for f in fichas.todas() if f["familia"] == "tamar_capitalizable" and liquidacion < f["vencimiento"]
                 and (ticker is None or f["ticker"].upper() == ticker.upper())]
        if not lista:
            return f"No hay bonos TAMAR vigentes{' con el ticker ' + ticker.upper() if ticker else ''}."
        puntos_tf = _tasa_fija(operacion, liquidacion, fecha_precios)
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    texto = [f"Proyección de bonos TAMAR – calculadora de Finianz – {descripcion}",
             f"Liquidación {liquidacion}. Los días de TAMAR ya publicados entran con su valor; los que faltan, con este camino.",
             "Bono | vence | TAMAR del bono | pago final | TNA | TEA (TIR) | TEA tasa fija al plazo"]
    for f in sorted(lista, key=lambda f: f["vencimiento"]):
        t = f["ticker"].upper()
        try:
            precio, _ = bonos._precio(t, fecha_precios)
            tamar_bono, d = tamar_del_bono(f, operacion, camino)
            r = tamar.calcular(precio, tamar_bono, f["margen"], f["emision"], f["vencimiento"], liquidacion, d["referencia"])
            dual = " (dual: pata TAMAR)" if "DUAL" in f["tipo"].upper() else ""
            texto.append(f"{t}{dual} | {f['vencimiento']} | {bonos._pct(tamar_bono)} | {r['pago_final']:.4f} | {bonos._pct(r['tna'])} | "
                         f"{bonos._pct(r['tea'])} | {_comparar(puntos_tf, r['plazo_residual'])}")
        except (ErrorAPI, ValueError) as e:
            texto.append(f"{t} | error: {e}")
    return "\n".join(texto)


def proyectar_dolar(tipo: str = "oficial", fuente: str = "rem", ticker: str | None = None, fecha: str | None = None) -> str:
    from renta_fija import leer_fichas as fichas
    from renta_fija.calculadoras import hard_dollar, motor
    try:
        operacion, liquidacion, fecha_precios = _contexto(fecha)
        nivel, descripcion, hoy, origen_hoy = camino_dolar(tipo, fuente, operacion, fecha_precios)
        familia = "dolar_linked_bullet" if tipo == "oficial" else "hard_dollar"
        lista = [f for f in fichas.todas() if f["familia"] == familia and liquidacion < f["vencimiento"]
                 and (ticker is None or f["ticker"].upper() == ticker.upper())]
        if not lista:
            return f"No hay bonos {'dollar linked' if tipo == 'oficial' else 'hard dollar'} vigentes" \
                   f"{' con el ticker ' + ticker.upper() if ticker else ''}."
        puntos_tf = _tasa_fija(operacion, liquidacion, fecha_precios)
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    texto = [f"Rendimiento en pesos con el {TIPOS_DOLAR[tipo]} proyectado – calculadora de Finianz – {descripcion}",
             f"{TIPOS_DOLAR[tipo]} de hoy: {hoy:,.2f} ({origen_hoy}) | liquidación {liquidacion}"]
    if tipo == "oficial":
        texto.append("Pago en pesos = 100 × tipo de cambio proyectado al vencimiento (aproxima el tipo de cambio de pago del prospecto).")
        texto.append("Bono | vence | A3500 proyectado | pago en pesos | TNA en pesos | TEA en pesos | TEA tasa fija al plazo")
    else:
        texto.append(f"Flujos en dólares de cada pago × {TIPOS_DOLAR[tipo]} proyectado en esa fecha, contra el precio en pesos.")
        texto.append(f"Bono | vence | {TIPOS_DOLAR[tipo]} al vencimiento | TIR en pesos (TEA) | duration en pesos | TEA tasa fija a esa duration")
    ajustar = lambda d: bonos.feriados.proximo_dia_habil(d, bonos.CALENDARIO_HABILES)
    for f in sorted(lista, key=lambda f: f["vencimiento"]):
        t = f["ticker"].upper()
        try:
            precio, _ = bonos._precio(t, fecha_precios)
            if tipo == "oficial":
                tc = nivel(f["vencimiento"])
                pago = 100 * tc
                plazo = (f["vencimiento"] - liquidacion).days
                tna = (pago / precio - 1) * 365 / plazo
                tea = (pago / precio) ** (365 / plazo) - 1
                texto.append(f"{t} | {f['vencimiento']} | {tc:,.2f} | {pago:,.2f} | {bonos._pct(tna)} | {bonos._pct(tea)} | "
                             f"{_comparar(puntos_tf, plazo)}")
            else:
                filas = hard_dollar.cronograma(f["pagos"], f["tramos"], f["emision"])
                flujos = [motor.Flujo(ajustar(x["fecha"]), x["renta"] * nivel(ajustar(x["fecha"])),
                                      x["amortizacion"] * nivel(ajustar(x["fecha"])))
                          for x in filas if x["fecha"] > liquidacion]
                tir = motor.tir(flujos, precio, liquidacion)
                dur = motor.duration(flujos, liquidacion, tir)
                texto.append(f"{t} | {f['vencimiento']} | {nivel(f['vencimiento']):,.2f} | {bonos._pct(tir)} | {dur:.2f} | "
                             f"{_comparar(puntos_tf, dur * 365)}")
        except (ErrorAPI, ValueError) as e:
            texto.append(f"{t} | error: {e}")
    return "\n".join(texto)


PROYECTAR_TAMAR = {
    "name": "proyectar_tamar",
    "description": (
        "Rendimiento de los bonos TAMAR (y la pata TAMAR de los duales) con un camino de TAMAR: 'actual' (los últimos 5 "
        "días, plana), 'rem' (mediana mensual del REM y después la de 12 meses), 'tna:<tasa>' (plana, ej.: 'tna:24%') o "
        "'escenario:<nombre>'. Da la TAMAR del bono, el pago final, la TNA, la TEA y la tasa fija al mismo plazo."
    ),
    "parameters": {"type": "object", "properties": {
        "fuente": {"type": "string", "description": "actual, rem, tna:<tasa>, camino:<meses> (TNA por mes y resto, ej.: camino:2026-12=24%;2027-01=23%;resto=21%) o escenario:<nombre> (por defecto, rem)"},
        "ticker": {"type": "string", "description": "Un bono TAMAR puntual (opcional)"},
        "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD (opcional)"},
    }},
}

PROYECTAR_DOLAR = {
    "name": "proyectar_dolar",
    "description": (
        "Rendimiento en pesos con un tipo de cambio proyectado. tipo 'oficial' (A3500): bonos dollar linked; fuentes 'rem', "
        "'breakeven', 'mensual:<variación>' (ej.: 'mensual:1.5%') o 'escenario:<nombre>'. tipo 'mep' o 'ccl': bonos hard "
        "dollar valuados en pesos; fuentes 'mensual:<variación>' o 'escenario:<nombre>'. Compara con la tasa fija."
    ),
    "parameters": {"type": "object", "properties": {
        "tipo": {"type": "string", "enum": ["oficial", "mep", "ccl"], "description": "Qué dólar proyectar (por defecto, oficial)"},
        "fuente": {"type": "string", "description": "rem, breakeven, mensual:<variación>, camino:<meses> (nivel en $ o variación con %, y resto; ej.: camino:2026-12=1600;2027-06=1.5%;resto=1%) o escenario:<nombre>"},
        "ticker": {"type": "string", "description": "Un bono puntual (opcional)"},
        "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD (opcional)"},
    }},
}

HERRAMIENTAS = [(PROYECTAR_TAMAR, proyectar_tamar), (PROYECTAR_DOLAR, proyectar_dolar)]
