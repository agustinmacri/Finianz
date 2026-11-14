"""Proyección del CER con distintas fuentes de inflación y rendimiento nominal de los bonos CER.

Fuentes: "breakeven" (la inflación que descuenta la curva CER contra la tasa fija), "rem", "escenario:<nombre>"
(renta_fija/escenarios/inflacion.toml) y "mensual:<tasa>" (una inflación mensual plana).
"rem" usa el último relevamiento cargado (Excel del BCRA en fuentes/rem/, base datos/rem.db): la mediana
de la inflación de cada mes que trae, y la anual (diciembre contra diciembre) de cada año para completar los
meses que faltan, de modo que el año cierre en lo que espera el REM. Si no hay ningún Excel cargado, usa la
mediana a 12 meses de la API, pasada a mensual y plana, y lo aclara como aproximación. Reglas en renta_fija/calculadoras/proyeccion_cer.py y docs/convenciones-renta-fija.md.
"""
import tomllib
from datetime import date, timedelta
from pathlib import Path

from admin_datos import rem as db_rem
from admin_datos import series as db_series
from conexiones import bcra
from conexiones.http import ErrorAPI
from renta_fija import leer_fichas as fichas
from renta_fija.calculadoras import breakeven as be
from renta_fija.calculadoras import cer, cer_cupon
from renta_fija.calculadoras import proyeccion_cer as pc
from tools import bonos, breakevens

ESCENARIOS = Path(__file__).resolve().parent.parent / "renta_fija" / "escenarios" / "inflacion.toml"
MESES_DETALLE = 15        # meses que se muestran uno por uno; después, el resumen anual
MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def escenarios() -> dict[str, dict]:
    """Escenarios cargados: {nombre: {'descripcion', 'mensual': {(a, m): i}, 'anual': {a: i}}}."""
    if not ESCENARIOS.exists():
        return {}
    with open(ESCENARIOS, "rb") as archivo:
        datos = tomllib.load(archivo)
    salida = {}
    for e in datos.get("escenario", []):
        mensual = {(int(k[:4]), int(k[5:7])): float(v) for k, v in e.get("mensual", {}).items()}
        anual = {int(k): float(v) for k, v in e.get("anual", {}).items()}
        if any(not -0.5 < v < 1 for v in [*mensual.values(), *anual.values()]):
            raise ValueError(f"Escenario {e.get('nombre')}: las inflaciones van en fracción (0.02 = 2%).")
        salida[e["nombre"]] = {"descripcion": e.get("descripcion", ""), "mensual": mensual, "anual": anual}
    return salida


def _serie_cer() -> dict[date, float]:
    """CER publicado de los últimos años (de la base propia, actualizada si hace falta)."""
    bonos._cer(date.today() - timedelta(days=1))           # asegura que la base esté al día
    desde = date(date.today().year - 2, 1, 1).isoformat()
    return {date.fromisoformat(p["fecha"]): p["valor"] for p in db_series.entre("CER", desde)}


def tasa_mensual(texto: str) -> float:
    """Lee una inflación mensual: "2%", "2", "1.66" o "0.02". Con % o desde 0,2 se toma como porcentaje
    (una inflación mensual de 20% o más escrita en fracción no es un caso real)."""
    limpio = texto.strip().replace("%", "").replace(",", ".")
    valor = float(limpio)
    return valor / 100 if "%" in texto or valor >= 0.2 else valor


def _rem_12_meses() -> tuple[float, str]:
    """Mediana del REM para la inflación de los próximos 12 meses (fracción) y la fecha del relevamiento."""
    for v in bcra.listar_variables():
        descripcion = bcra.normalizar(v["descripcion"])
        if v["id"] == bcra.ID_REM_12M and ("esperada" in descripcion or "expectativ" in descripcion):
            return float(v["ultimo_valor"]) / 100, str(v["ultima_fecha"])[:10]
    raise ErrorAPI("no se encontró en el BCRA la inflación esperada del REM a 12 meses.")


def rem_inflacion() -> tuple[str, dict, dict] | None:
    """(relevamiento, inflación mensual {(año, mes): fracción}, anual {año: fracción}) del último REM, o None."""
    relevamiento = db_rem.ultimo()
    if relevamiento is None:
        return None
    ipc = db_rem.valores("IPC", relevamiento)
    mensuales = {(int(p[:4]), int(p[5:7])): v / 100 for p, v in ipc.items() if len(p) == 7 and p[4] == "-"}
    anuales = {int(p): v / 100 for p, v in ipc.items() if p.isdigit()}
    return relevamiento, mensuales, anuales


def inflacion_rem_por_mes(hasta_mes: pc.Mes) -> tuple[str, dict[pc.Mes, float]] | None:
    """Inflación de cada mes: la publicada (leída del CER) y, desde el primer mes sin publicar, el camino del REM."""
    rem = rem_inflacion()
    if rem is None:
        return None
    relevamiento, mensuales, anuales = rem
    publicadas = pc.inflacion_publicada(_serie_cer())
    desde = pc.sumar_meses(max(publicadas), 1)
    caminos = pc.camino(publicadas, mensuales, anuales, desde, max(hasta_mes, desde))
    return relevamiento, publicadas | {m: v for m, (v, _) in caminos.items()}


def _nombre_mes(mes: pc.Mes) -> str:
    return f"{MESES[mes[1] - 1]}-{mes[0] % 100:02d}"


def camino_inflacion(fuente: str, liquidacion: date, hasta_mes: pc.Mes, curvas: dict | None = None,
                     operacion: date | None = None, fecha_precios: date | None = None):
    """Inflación de cada mes sin publicar según la fuente: (caminos {mes: (inflación, origen)}, descripción,
    serie del CER, inflación publicada). Para "breakeven" usa las curvas (las arma si no se pasan)."""
    serie = _serie_cer()
    publicadas = pc.inflacion_publicada(serie)
    ultimo = max(serie)
    desde = pc.sumar_meses(max(publicadas), 1)
    hasta_mes = max(hasta_mes, desde)
    if fuente == "breakeven" and curvas is None:
        curvas, _, _ = breakevens._curvas(operacion or date.today(), liquidacion, fecha_precios,
                                          {"tasa_fija_capitalizable", "tasa_fija_cupon", "cer_cero_cupon"})
    puntos_tf = [(p["x"], p["tea"]) for p in curvas["tasa_fija"]] if curvas else []
    # Camino de inflación según la fuente
    if fuente == "rem" and db_rem.ultimo():
        relevamiento, mensuales, anuales = rem_inflacion()
        caminos = pc.camino(publicadas, mensuales, anuales, desde, hasta_mes)
        meses_rem = sorted(m for m in mensuales if m >= desde)
        descripcion = (f"REM del BCRA, relevamiento {relevamiento} (mediana). Mes a mes"
                       + (f" de {_nombre_mes(meses_rem[0])} a {_nombre_mes(meses_rem[-1])}" if meses_rem else ": ninguno pendiente")
                       + "; inflación anual " + ", ".join(f"{a} {bonos._pct(v)}" for a, v in sorted(anuales.items()))
                       + ". Los meses sin dato mensual completan cada año para cerrar en esa anual; después de "
                       + f"{max(anuales)} se repite la última anual. Los meses ya publicados usan el dato del INDEC")
    elif fuente.startswith("mensual:") or fuente == "rem":
        if fuente == "rem":
            anual, fecha_rem = _rem_12_meses()
            tasa = (1 + anual) ** (1 / 12) - 1
            descripcion = (f"REM (relevamiento al {fecha_rem}): mediana de la inflación esperada a 12 meses "
                           f"{bonos._pct(anual)}, pasada a mensual ({bonos._pct(tasa)}) y aplicada plana. Aproximación: "
                           "no hay ningún Excel del REM en fuentes/rem/")
        else:
            tasa = tasa_mensual(fuente.split(":", 1)[1])
            descripcion = f"inflación mensual plana de {bonos._pct(tasa)}"
        mes, caminos = desde, {}
        while mes <= hasta_mes:
            caminos[mes] = (tasa, "plana")
            mes = pc.sumar_meses(mes, 1)
    elif fuente.startswith("escenario:"):
        nombre = fuente.split(":", 1)[1]
        todos = escenarios()
        if nombre not in todos:
            raise ValueError(f"No existe el escenario '{nombre}'. Cargados: {', '.join(todos) or 'ninguno'} (renta_fija/escenarios/inflacion.toml).")
        e = todos[nombre]
        caminos = pc.camino(publicadas, e["mensual"], e["anual"], desde, hasta_mes)
        descripcion = f"escenario '{nombre}': {e['descripcion']}"
    elif fuente == "breakeven":
        nodos = []
        for p in curvas["cer"]:
            f = fichas.ficha(p["ticker"], "cer_cero_cupon")
            tf = be.interpolar(puntos_tf, p["x"])
            if f is None or tf is None:
                continue
            _, f2, _ = bonos._datos_cer(f, liquidacion)
            plazo = (f["vencimiento"] - liquidacion).days
            cer_final = p["precio"] * (1 + tf) ** (plazo / 365) * f2["cer_inicial"] / 100
            fecha_final = bonos.feriados.sumar_dias_habiles(f["vencimiento"], -cer.REZAGO_HABILES, bonos.CALENDARIO_HABILES)
            if fecha_final > ultimo:
                nodos.append((fecha_final, cer_final))
        if not nodos:
            raise ValueError("No alcanzan los bonos CER y de tasa fija con precio para armar el breakeven.")
        caminos = pc.inflacion_desde_cer((ultimo, serie[ultimo]), nodos, desde, hasta_mes)
        descripcion = "breakeven: la inflación que iguala cada CER cero cupón con la tasa fija a su plazo"
    else:
        raise ValueError("Fuente desconocida. Opciones: breakeven, rem, escenario:<nombre>, mensual:<tasa> (ej.: mensual:2%).")

    return caminos, descripcion, serie, publicadas


def proyectar_cer(fuente: str = "breakeven", ticker: str | None = None, fecha: str | None = None) -> str:
    try:
        operacion = date.fromisoformat(fecha) if fecha else date.today()
        bonos._asegurar_feriados(operacion, operacion + timedelta(days=365 * 6))
        liquidacion = bonos.feriados.sumar_dias_habiles(operacion, bonos.PLAZO_LIQUIDACION, "BYMA")
        serie = _serie_cer()
        publicadas = pc.inflacion_publicada(serie)
        ultimo = max(serie)
        desde = pc.sumar_meses(max(publicadas), 1)

        lista = [f for f in fichas.todas() if f["familia"].startswith("cer")
                 and liquidacion < f["vencimiento"] and (ticker is None or f["ticker"].upper() == ticker.upper())]
        if not lista:
            return f"No hay bonos CER vigentes{' con el ticker ' + ticker.upper() if ticker else ''}."
        fechas_cer = {}                                   # fecha de CER de cada pago (10 días hábiles antes)
        for f in lista:
            pagos = [p["fecha"] for p in f["pagos"]] if f["familia"] == "cer_cupon" else [f["vencimiento"]]
            fechas_cer[f["ticker"]] = [(p, bonos.feriados.sumar_dias_habiles(p, -cer.REZAGO_HABILES, bonos.CALENDARIO_HABILES))
                                       for p in pagos if p > liquidacion]
        hasta = max(d for v in fechas_cer.values() for _, d in v)
        hasta_mes = pc.mes_aplicado(hasta) if hasta > ultimo else desde

        fecha_precios = operacion if fecha else None
        curvas, _, errores = breakevens._curvas(operacion, liquidacion, fecha_precios,
                                                {"tasa_fija_capitalizable", "tasa_fija_cupon", "cer_cero_cupon"})
        puntos_tf = [(p["x"], p["tea"]) for p in curvas["tasa_fija"]]

        caminos, descripcion, serie, publicadas = camino_inflacion(fuente, liquidacion, hasta_mes, curvas, operacion, fecha_precios)
        proyectado = pc.proyectar(serie, {m: v for m, (v, _) in caminos.items()}, max(hasta, ultimo))
        cer_en = lambda d: serie.get(d) or proyectado[d]
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"

    texto = [f"Proyección del CER – calculadora de Finianz – fuente: {descripcion}",
             f"Último CER publicado: {ultimo} = {serie[ultimo]:,.4f} (incluye la inflación de {_nombre_mes(max(publicadas))}: "
             f"{bonos._pct(publicadas[max(publicadas)])})"]
    if caminos:
        meses = list(caminos.items())
        texto.append("Inflación mensual usada: " + "; ".join(
            f"{_nombre_mes(m)} {bonos._pct(v)}" + ("" if o in ("mensual", "plana", "breakeven") else f" ({o})")
            for m, (v, o) in meses[:MESES_DETALLE]) + ("; …" if len(meses) > MESES_DETALLE else ""))
        extendidos = [m for m, (_, o) in meses if "extendida" in o]
        if extendidos:
            texto.append(f"Desde {_nombre_mes(extendidos[0])} la curva no tiene más bonos: se repite la última inflación mensual.")
        anios = sorted({m[0] for m in caminos})
        resumen = []
        for a in anios:
            meses = [publicadas.get((a, k)) if (a, k) < desde else caminos.get((a, k), (None,))[0] for k in range(1, 13)]
            if all(v is not None for v in meses) and a > max(publicadas)[0] - 1:
                acumulada = 1.0
                for v in meses:
                    acumulada *= 1 + v
                resumen.append(f"{a}: {bonos._pct(acumulada - 1)}")
        if resumen:
            texto.append("Inflación anual (dic/dic) que resulta: " + " | ".join(resumen))

    texto.append(f"\nRendimiento nominal con ese CER (liquidación {liquidacion}, precios de mercado):")
    texto.append("Bono | vence | CER final (fecha) | pago final o TIR | TNA | TIR nominal | TEA tasa fija al plazo")
    precios = {p["ticker"]: p["precio"] for p in curvas["cer"]}
    for f in sorted(lista, key=lambda f: f["vencimiento"]):
        t = f["ticker"].upper()
        try:
            precio = precios.get(t) or bonos._precio(t, fecha_precios)[0]
            _, f2, cer_corriente = bonos._datos_cer(f, liquidacion)
            if f["familia"] == "cer_cupon":
                ajustar = lambda d: bonos.feriados.proximo_dia_habil(d, bonos.CALENDARIO_HABILES)
                real = cer_cupon.calcular(precio, f2["cer_inicial"], cer_corriente, liquidacion, f["pagos"], f["cupon"],
                                          f["frecuencia"], f["emision"], ajustar)
                cers = [cer_en(d) for _, d in fechas_cer[f["ticker"]]]
                r = pc.nominal_con_cupon(precio, f2["cer_inicial"], real["flujos"], cers, liquidacion)
                tf = be.interpolar(puntos_tf, r["duration"] * 365)
                fecha_final = fechas_cer[f["ticker"]][-1][1]
                texto.append(f"{t} | {f['vencimiento']} | {cers[-1]:,.2f} ({fecha_final}) | flujos ajustados | "
                             f"{bonos._pct(r['tna_semestral'])} semestral | {bonos._pct(r['tir'])} | "
                             f"{bonos._pct(tf) if tf is not None else 'fuera de la curva'}")
            else:
                fecha_final = fechas_cer[f["ticker"]][-1][1]
                cf = cer_en(fecha_final)
                r = pc.nominal_cero_cupon(precio, f2["cer_inicial"], cf, liquidacion, f["vencimiento"])
                tf = be.interpolar(puntos_tf, r["plazo"])
                dual = " (dual: solo la pata CER)" if "DUAL" in f["tipo"].upper() else ""
                texto.append(f"{t}{dual} | {f['vencimiento']} | {cf:,.2f} ({fecha_final}) | {r['pago_final']:.2f} | "
                             f"{bonos._pct(r['tna'])} | {bonos._pct(r['tir'])} | "
                             f"{bonos._pct(tf) if tf is not None else 'fuera de la curva'}")
        except (ErrorAPI, ValueError, KeyError) as e:
            texto.append(f"{t} | error: {e}")
    if errores:
        texto.append("Sin precio: " + " | ".join(errores))
    return "\n".join(texto)


PROYECTAR_CER = {
    "name": "proyectar_cer",
    "description": (
        "Proyecta el CER con la regla del BCRA (la inflación del mes m se reparte del 16 de m+1 al 15 de m+2) y calcula "
        "el rendimiento nominal de los bonos CER (TNA, TIR nominal y CER final) para contrastarlo con la tasa fija u "
        "otros activos. Fuentes de inflación: 'breakeven' (la que descuenta la curva), 'rem' (expectativas del REM), "
        "'escenario:<nombre>' (escenarios cargados) o 'mensual:<tasa>' (plana, en porcentaje: 'mensual:2%'). "
        "Para el REM usá 'rem': no armes la inflación a mano."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fuente": {"type": "string", "description": "breakeven, rem, escenario:<nombre> o mensual:<tasa en %> (ej.: mensual:2%). Por defecto, breakeven"},
            "ticker": {"type": "string", "description": "Un bono CER puntual (opcional; si no, todos)"},
            "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD para usar los cierres de ese día (opcional)"},
        },
    },
}

HERRAMIENTAS = [(PROYECTAR_CER, proyectar_cer)]
