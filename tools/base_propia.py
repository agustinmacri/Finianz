"""consultar_base: lectura de los datos que ya están guardados en el sistema, sin llamar a ninguna API.

La usa el agente de renta fija para el contexto de sus cálculos. Si necesita un dato que no está acá
(u otro análisis macro), se lo pide al agente macro con consultar_agente_macro.
"""
from datetime import date

from admin_datos import rem as db_rem
from admin_datos import series as db_series
from renta_fija.calculadoras import proyeccion_cer as pc

VARIABLES = ("CER", "TAMAR", "A3500", "inflacion", "REM")
VARIABLES_REM = ("IPC", "IPC_NUCLEO", "TAMAR", "TIPO_CAMBIO", "PIB", "DESOCUPACION", "RESULTADO_PRIMARIO",
                 "EXPORTACIONES", "IMPORTACIONES")


def consultar_base(variable: str, desde: str | None = None, hasta: str | None = None, ultimos: int = 10,
                   variable_rem: str = "IPC") -> str:
    if variable not in VARIABLES:
        return f"Variable desconocida: {variable}. Opciones: {', '.join(VARIABLES)}."
    if variable in ("CER", "TAMAR", "A3500"):
        filas = db_series.entre(variable, desde, hasta)
        if not filas:
            return f"No hay datos de {variable} guardados{' en ese período' if desde or hasta else ''}."
        mostrar = filas if desde else filas[-ultimos:]
        unidad = {"CER": "índice", "TAMAR": "% TNA", "A3500": "$ por US$"}[variable]
        rango = db_series.rango(variable)
        return (f"{variable} ({unidad}), base propia (fuente BCRA). Guardado del {rango[0]} al {rango[1]}.\n"
                + "\n".join(f"{f['fecha']}: {f['valor']:,.4f}" for f in mostrar))
    if variable == "inflacion":
        cer = {date.fromisoformat(f["fecha"]): f["valor"] for f in db_series.entre("CER", desde and f"{int(desde[:4]) - 1}-01-01")}
        meses = sorted(pc.inflacion_publicada(cer).items())
        if desde:
            meses = [(m, v) for m, v in meses if f"{m[0]}-{m[1]:02d}" >= desde[:7]]
        if hasta:
            meses = [(m, v) for m, v in meses if f"{m[0]}-{m[1]:02d}" <= hasta[:7]]
        if not meses:
            return "No hay inflación publicada en la base para ese período."
        mostrar = meses if desde else meses[-ultimos:]
        return ("Inflación mensual publicada (INDEC), leída de la serie del CER de la base propia: la del mes m entra en el "
                "CER del 16 de m+1 al 15 de m+2.\n" + "\n".join(f"{m[0]}-{m[1]:02d}: {v * 100:.2f}%" for m, v in mostrar))
    relevamiento = db_rem.ultimo()
    if relevamiento is None:
        return "No hay ningún relevamiento del REM cargado (fuentes/rem/)."
    if variable_rem not in VARIABLES_REM:
        return f"Variable del REM desconocida: {variable_rem}. Opciones: {', '.join(VARIABLES_REM)}."
    valores = db_rem.valores(variable_rem, relevamiento)
    if not valores:
        return f"El REM {relevamiento} no tiene {variable_rem}."
    return (f"REM del BCRA, relevamiento {relevamiento}, {variable_rem} (mediana):\n"
            + "\n".join(f"{p}: {v:,.4g}" for p, v in sorted(valores.items())))


CONSULTAR_BASE = {
    "name": "consultar_base",
    "description": (
        "Datos guardados en el sistema, sin llamar a ninguna API: CER, TAMAR (% TNA) y A3500 diarios; 'inflacion' "
        "(mensual publicada, leída del CER); 'REM' (último relevamiento: IPC, IPC_NUCLEO, TAMAR, TIPO_CAMBIO, PIB, "
        "DESOCUPACION...). Por defecto devuelve los últimos valores; con desde/hasta, un período."
    ),
    "parameters": {"type": "object", "properties": {
        "variable": {"type": "string", "enum": list(VARIABLES), "description": "Qué dato leer"},
        "desde": {"type": "string", "description": "Fecha AAAA-MM-DD (opcional)"},
        "hasta": {"type": "string", "description": "Fecha AAAA-MM-DD (opcional)"},
        "ultimos": {"type": "integer", "description": "Cuántos valores mostrar sin desde (por defecto 10)"},
        "variable_rem": {"type": "string", "enum": list(VARIABLES_REM), "description": "Con variable='REM': cuál (por defecto IPC)"},
    }, "required": ["variable"]},
}

HERRAMIENTAS = [(CONSULTAR_BASE, consultar_base)]
