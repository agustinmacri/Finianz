"""Proyección del patrimonio de la cartera hasta una fecha, con uno o varios escenarios.

Decisiones de Agustin (25/11/2026):
- TIR constante: cada bono rinde su TIR de hoy hasta la fecha elegida, sin cambios de tasa (más adelante: tasas
  forward y exit yield por bono). Con TIR constante y los cobros reinvertidos en el mismo bono, el valor crece a esa
  TIR en la unidad del bono: pesos (tasa fija), pesos reales (CER, ajustados con la inflación del escenario),
  dólares (dollar linked al A3500 del escenario; hard dollar al MEP o CCL del escenario). TAMAR y duales: con su TIR
  nominal en pesos bajo el escenario (la de la pata que más rinde).
- Si un bono vence antes de la fecha, lo cobrado se reparte entre los demás activos en proporción a su valor.
- Las acciones mantienen su valor de hoy en dólares: en pesos solo acompañan la devaluación (MEP; las de EE. UU. y
  los ETF, CCL). Los FCI quedan en pesos constantes.
- Liquidez sin colocar: no rinde (en dólares, sigue en dólares). Money market, cauciones, plazos fijos, créditos y
  pasivos: su tasa (se renuevan a la misma tasa).
"""
from datetime import date, timedelta

from carteras import valuar
from carteras.excel import SUPUESTOS, Cartera
from conexiones.http import ErrorAPI
from renta_fija import mercado
from renta_fija.calculadoras import cer

AVISO_ACCIONES = ("Proyección con TIR constante: no supone cambios de tasa ni de precio de mercado. Las acciones y los "
                  "CEDEARs no cambian de valor: en pesos solo acompañan la devaluación del dólar del escenario. Cupones "
                  "reinvertidos en el mismo bono; lo que vence se reparte entre los demás activos.")


def escenarios_disponibles(cartera: Cartera) -> dict[str, dict[str, str]]:
    """Juegos de supuestos para elegir: los de la cartera, el REM, el mercado y los escenarios con nombre cargados en
    renta_fija/escenarios/ (por nombre; las variables sin ese escenario usan el supuesto de la cartera)."""
    propios = {v: cartera.supuestos.get(v) or "rem" for v in SUPUESTOS}
    juegos = {"Supuestos de la cartera": propios,
              "REM": {v: "rem" for v in SUPUESTOS},
              "Mercado (breakevens)": {"inflacion": "breakeven", "tamar": "actual", "dolar_oficial": "breakeven",
                                       "mep": "rem", "ccl": "rem"}}
    try:
        from tools import proyeccion_cer, proyecciones
        por_variable = {"inflacion": proyeccion_cer.escenarios(), "tamar": proyecciones.escenarios("tamar"),
                        "dolar_oficial": proyecciones.escenarios("oficial"), "mep": proyecciones.escenarios("mep"),
                        "ccl": proyecciones.escenarios("ccl")}
    except Exception:
        por_variable = {}
    for nombre in sorted({n for lista in por_variable.values() for n in lista}):
        juegos[f"Escenario {nombre}"] = {v: f"escenario:{nombre}" if nombre in por_variable.get(v, {}) else propios[v]
                                         for v in SUPUESTOS}
    return juegos


def _fechas(desde: date, hasta: date, eventos: list[date]) -> list[date]:
    """Un punto por mes (y en cada vencimiento) desde 'desde' hasta 'hasta'."""
    puntos, d = {desde, hasta}, desde
    while True:
        mes = d.month + 1
        d = date(d.year + (mes > 12), (mes - 1) % 12 + 1, min(desde.day, 28))
        if d >= hasta:
            break
        puntos.add(d)
    puntos |= {e for e in eventos if desde < e <= hasta}
    return sorted(puntos)


def _crecimientos(v: dict, proy: valuar.Proyecciones):
    """Para cada fila, una función d -> factor de crecimiento en pesos desde hoy (1 en la liquidación)."""
    ctx = v["_ctx"]
    t0, op = ctx.liquidacion, ctx.operacion
    anios = lambda d: max((d - t0).days, 0) / 365
    fecha_cer = lambda d: mercado.feriados.sumar_dias_habiles(d, -cer.REZAGO_HABILES, mercado.CALENDARIO_HABILES)
    dolar = {t: proy.dolar(t) for t in ("mep", "ccl")}
    def relacion(tipo):
        nivel = dolar[tipo]
        base = nivel(op)
        return lambda d: nivel(d) / base
    salida = []
    for fila in v["filas"]:
        if fila.get("liquidez"):
            x = fila["_liq"]
            tea = fila["tir_proyectada"] or 0.0
            ajuste = relacion(x.moneda) if x.moneda != "pesos" else (lambda d: 1.0)
            salida.append(lambda d, tea=tea, ajuste=ajuste: (1 + tea) ** anios(d) * ajuste(d))
            continue
        if fila["categoria"] != "Renta Fija":
            if fila["subclase"] == "FCI":
                salida.append(lambda d: 1.0)
            else:
                salida.append(relacion("ccl" if fila["moneda_activo"] == "Dólar CCL" else "mep"))
            continue
        f, m = fila["_f"], fila["_m"]
        familia = f["familia"]
        if len(fila["_legs"]) > 1 or familia == "tamar_capitalizable":
            tir = max(proy.tir_nominal(fl, fila["_px"], ml) for fl, ml in fila["_legs"])
            salida.append(lambda d, tir=tir: (1 + tir) ** anios(d))
        elif familia.startswith("tasa_fija") or m.get("cer_conocido"):
            salida.append(lambda d, tea=m["tea"]: (1 + tea) ** anios(d))
        elif familia.startswith("cer"):
            indice = proy.cer()
            base = indice(fecha_cer(t0))
            salida.append(lambda d, tea=m["tea"], indice=indice, base=base:
                          (1 + tea) ** anios(d) * indice(fecha_cer(d)) / base)
        elif familia.startswith("dolar_linked"):
            oficial = proy.oficial()
            base = oficial(op)
            salida.append(lambda d, tea=m["tea"], oficial=oficial, base=base: (1 + tea) ** anios(d) * oficial(d) / base)
        else:                                              # hard dollar
            salida.append(lambda d, tea=m["tea"], r=relacion(fila["_tipo_fx"]): (1 + tea) ** anios(d) * r(d))
    return salida, dolar


def proyectar(v: dict, cartera: Cartera, hasta: date, escenarios: dict[str, dict[str, str]]) -> dict:
    """El patrimonio de cada escenario hasta 'hasta': puntos mensuales en pesos, MEP y CCL, y el resumen."""
    ctx = v["_ctx"]
    t0 = ctx.liquidacion
    if hasta <= t0:
        raise ValueError("Elegí una fecha posterior a hoy.")
    vencimientos = [f["_vencimiento"] for f in v["filas"] if f.get("_vencimiento")]
    resultados, avisos = {}, []
    for nombre, supuestos in escenarios.items():
        proy = valuar.Proyecciones(supuestos, ctx, max([hasta + timedelta(days=40), *vencimientos]))
        try:
            crecimientos, dolar = _crecimientos(v, proy)
            fechas = _fechas(t0, hasta, vencimientos)
            vivos = [True] * len(v["filas"])
            valores = [f["total_pesos"] for f in v["filas"]]
            puntos, anterior = [], t0
            for d in fechas:
                for i, g in enumerate(crecimientos):
                    if vivos[i] and d > anterior:
                        valores[i] *= g(d) / g(anterior)
                for i, fila in enumerate(v["filas"]):
                    if vivos[i] and fila.get("_vencimiento") and anterior < fila["_vencimiento"] <= d:
                        cobrado, valores[i], vivos[i] = valores[i], 0.0, False
                        destinos = [j for j, f in enumerate(v["filas"]) if vivos[j] and valores[j] > 0
                                    and f["categoria"] != "Pasivos"]
                        suma = sum(valores[j] for j in destinos)
                        if suma:
                            for j in destinos:
                                valores[j] += cobrado * valores[j] / suma
                        else:                               # nada más en cartera: queda como liquidez en pesos
                            valores.append(cobrado)
                            vivos.append(True)
                            crecimientos.append(lambda d: 1.0)
                total = sum(x for x, vivo in zip(valores, vivos) if vivo)
                mep, ccl = dolar["mep"](d), dolar["ccl"](d)
                puntos.append({"fecha": d, "pesos": total, "mep": total / mep, "ccl": total / ccl})
                anterior = d
        except (ErrorAPI, ValueError, KeyError, ZeroDivisionError) as e:
            avisos.append(f"{nombre}: no se pudo proyectar ({str(e).splitlines()[0][:160]}).")
            continue
        anios = (hasta - t0).days / 365
        resumen = {}
        for moneda in ("pesos", "mep", "ccl"):
            a, b = puntos[0][moneda], puntos[-1][moneda]
            rendimiento = b / a - 1 if a else None
            resumen[moneda] = {"inicial": a, "final": b, "rendimiento": rendimiento,
                               "anualizado": (1 + rendimiento) ** (1 / anios) - 1 if rendimiento is not None
                               and anios > 0.05 and rendimiento > -1 else None}
        resultados[nombre] = {"puntos": puntos, "resumen": resumen, "supuestos": dict(proy.descripciones)}
    return {"escenarios": resultados, "avisos": avisos, "hasta": hasta, "desde": t0, "aclaracion": AVISO_ACCIONES}
