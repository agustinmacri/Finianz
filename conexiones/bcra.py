"""Client de la API del BCRA – Principales Variables (v4.0).

Solo sabe hablar con el BCRA y devolver datos limpios de Python. No sabe nada de IA.

No hay códigos de variables escritos a mano: se buscan por su descripción en el
listado oficial, así el código no se rompe si el BCRA cambia la numeración.
"""
import unicodedata
from datetime import date, timedelta

import config
from conexiones.http import ErrorAPI, get_json


def listar_variables() -> list[dict]:
    """Todas las variables que publica el BCRA, con su último valor informado."""
    datos = get_json(config.BCRA_URL)
    return [
        {
            "id": v["idVariable"],
            "descripcion": v.get("descripcion", ""),
            "categoria": v.get("categoria"),
            "periodicidad": v.get("periodicidad"),
            "unidad": v.get("unidadExpresion"),
            "ultima_fecha": v.get("ultFechaInformada"),
            "ultimo_valor": v.get("ultValorInformado"),
        }
        for v in datos.get("results", [])
    ]


# Cada palabra de la búsqueda cuenta como encontrada si aparece cualquiera de sus alternativas.
_INFLACION = ("inflacion", "precios")
_EXPECTATIVAS = ("expectativas",)  # el BCRA no usa la sigla REM: dice "relevamiento de expectativas de mercado"
_CER = ("estabilizacion", "cer")  # el CER no figura con su sigla: "coeficiente de estabilización de referencia"

# Variables que el proyecto usa por su id fijo (no dependen de cómo esté escrita la descripción)
ID_CER = 30                        # Coeficiente de estabilización de referencia (base 2.2.02=1), diario

SINONIMOS = {
    "inflacion": _INFLACION, "ipc": _INFLACION, "precios": _INFLACION,
    "dolar": ("cambio",),
    "rem": _EXPECTATIVAS, "esperada": _EXPECTATIVAS, "expectativa": _EXPECTATIVAS, "consenso": _EXPECTATIVAS,
    "cer": _CER,
}

# Palabras que no ayudan a distinguir variables y se ignoran
IGNORAR = {"bcra", "indec", "del", "las", "los", "nivel", "general", "serie", "historica", "dato", "datos", "ultimo"}


def buscar_variables(texto: str) -> list[dict]:
    """Variables ordenadas por cuántas de las palabras buscadas contienen.

    No distingue mayúsculas ni tildes, ignora números y palabras de relleno,
    y traduce sinónimos: "IPC mensual 2026" encuentra "Inflación mensual (variación en %)".
    """
    palabras = {
        SINONIMOS.get(p, (p,))
        for p in normalizar(texto).split()
        if len(p) > 2 and not p.isdigit() and p not in IGNORAR
    }
    puntajes = []
    for v in listar_variables():
        descripcion = normalizar(v["descripcion"])
        puntaje = sum(any(alt in descripcion for alt in alternativas) for alternativas in palabras)
        if puntaje:
            puntajes.append((puntaje, v))
    puntajes.sort(key=lambda par: (-par[0], par[1]["id"]))
    return [v for _, v in puntajes]


def obtener_serie(id_variable: int, desde: str | None = None, hasta: str | None = None) -> list[dict]:
    """Valores históricos de una variable, ordenados del más viejo al más nuevo.

    Fechas en formato 'AAAA-MM-DD'. Si no se indican, trae el último año.
    Devuelve [{'fecha': '2026-10-01', 'valor': 123.4}, ...]
    """
    hasta = hasta or date.today().isoformat()
    desde = desde or (date.fromisoformat(hasta) - timedelta(days=365)).isoformat()

    datos = get_json(f"{config.BCRA_URL}/{id_variable}", params={"desde": desde, "hasta": hasta})
    resultados = datos.get("results", [])
    if not resultados:
        raise ErrorAPI(f"El BCRA no devolvió datos para la variable {id_variable} entre {desde} y {hasta}.")

    serie = [{"fecha": d["fecha"], "valor": d["valor"]} for d in resultados[0].get("detalle", [])]
    return sorted(serie, key=lambda d: d["fecha"])


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para comparar textos."""
    sin_tildes = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sin_tildes.lower()