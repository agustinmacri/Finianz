"""Carga del calendario de difusión del INDEC desde sus PDF semestrales.

Los PDF se guardan en calendarios/indec/ (se suben a git: son públicos y livianos).
Cuando el INDEC publica el calendario de un semestre nuevo, se descarga de
https://www.indec.gob.ar/ftp/cuadros/publicaciones/calendario_<1|2>sem<año>.pdf
se copia a esa carpeta y se corre `python actualizar.py`.
Si el INDEC actualiza un semestre, se REEMPLAZA el PDF (no se deja el viejo al lado).
"""
import re
from datetime import date

import pypdf

import config
from admin_datos.db import conectar
from carga_datos import catalogo

CARPETA = config.CALENDARIOS_DIR / "indec"
FUENTE = "indec_pdf"

MESES = {m: i for i, m in enumerate(
    ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
     "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"], start=1)}
DIAS = ["LU", "MA", "MI", "JU", "VI", "SA", "DO"]

RENGLON_CON_DIA = re.compile(r"^(\d{1,2}) (LU|MA|MI|JU|VI|SA|DO) (.+)$")
# El semestre se toma del pie de página (hay títulos que también dicen "semestre de AAAA")
SEMESTRE = re.compile(r"CALENDARIO DE DIFUSIÓN\.\s*(Primer|Segundo) semestre de (\d{4})")
# Renglones del pie de página que no son publicaciones
PIE = re.compile(r"^(Actualizado al|CALENDARIO DE DIFUSIÓN|INDECArgentina)")
# Un título está completo si termina en un año ("... Septiembre de 2026", "... Año 2025")
TERMINA_EN_ANIO = re.compile(r"\d{4}\)?\.?$")


def cargar() -> dict:
    """Lee todos los PDF de calendarios/indec/ y reemplaza en la base las publicaciones del INDEC.

    Devuelve un resumen: cuántas se cargaron, cuántas son de las que seguimos, y avisos
    (días de la semana que no coinciden, semestres repetidos, renglones no reconocidos).
    """
    seguidas = [p for p in catalogo.leer() if p["fuente"] == FUENTE]
    archivos = sorted(CARPETA.glob("*.pdf"))
    publicaciones, avisos, semestres = [], [], {}

    for archivo in archivos:
        texto = "\n".join(pagina.extract_text() or "" for pagina in pypdf.PdfReader(archivo).pages)
        encontrados, avisos_archivo, semestre = leer_texto(texto, archivo.name)
        if semestre in semestres:
            avisos.append(f"{archivo.name} y {semestres[semestre]} son del mismo semestre: dejá solo el más nuevo.")
        semestres[semestre] = archivo.name
        publicaciones += encontrados
        avisos += avisos_archivo

    for p in publicaciones:
        seguida = next((s for s in seguidas if p["titulo"].startswith(s["patron"])), None)
        p["codigo"] = seguida["codigo"] if seguida else None
        p["importancia"] = seguida["importancia"] if seguida else "baja"

    with conectar("publicaciones") as con:
        con.execute("DELETE FROM publicaciones WHERE fuente = ?", (FUENTE,))
        con.executemany(
            "INSERT OR REPLACE INTO publicaciones VALUES (?, NULL, 'AR', 'INDEC', ?, ?, ?, ?, ?)",
            [(p["fecha"], p["codigo"], p["titulo"], p["periodo"], p["importancia"], FUENTE) for p in publicaciones],
        )

    return {
        "archivos": [a.name for a in archivos],
        "total": len(publicaciones),
        "seguidas": sum(1 for p in publicaciones if p["codigo"]),
        "desde": min((p["fecha"] for p in publicaciones), default=None),
        "hasta": max((p["fecha"] for p in publicaciones), default=None),
        "sin_encontrar": [s["codigo"] for s in seguidas if not any(p["codigo"] == s["codigo"] for p in publicaciones)],
        "avisos": avisos,
    }


def leer_texto(texto: str, nombre_archivo: str = "PDF") -> tuple[list[dict], list[str], str]:
    """Convierte el texto de un calendario semestral en una lista de publicaciones con fecha.

    El PDF está en columnas, así que los meses pueden aparecer desordenados: no importa,
    porque cada renglón con nombre de mes fija el mes de los renglones que siguen.
    """
    semestre = SEMESTRE.search(texto)
    if not semestre:
        raise ValueError(f"{nombre_archivo}: no se encontró 'Primer/Segundo semestre de AAAA' en el pie del calendario.")
    anio = int(semestre.group(2))
    meses_validos = range(1, 7) if semestre.group(1) == "Primer" else range(7, 13)

    publicaciones, avisos = [], []
    mes = dia = None

    for crudo in texto.splitlines():
        renglon = crudo.strip()
        if not renglon or PIE.match(renglon):
            continue
        if renglon in MESES:
            mes = MESES[renglon]
            if mes not in meses_validos:
                avisos.append(f"{nombre_archivo}: el mes {renglon} no corresponde al {semestre.group(1).lower()} semestre de {anio}.")
            continue

        coincidencia = RENGLON_CON_DIA.match(renglon)
        if coincidencia:
            dia = int(coincidencia.group(1))
            fecha = date(anio, mes, dia)
            if DIAS[fecha.weekday()] != coincidencia.group(2):
                avisos.append(f"{nombre_archivo}: el {fecha} figura como {coincidencia.group(2)} pero es "
                              f"{DIAS[fecha.weekday()]} (se usa la fecha).")
            publicaciones.append({"fecha": fecha.isoformat(), "titulo": coincidencia.group(3).strip()})
        elif publicaciones and _continua(publicaciones[-1]["titulo"], renglon):
            publicaciones[-1]["titulo"] += " " + renglon     # continuación del título anterior
        elif mes and dia:
            publicaciones.append({"fecha": date(anio, mes, dia).isoformat(), "titulo": renglon})  # otra del mismo día
        else:
            avisos.append(f"{nombre_archivo}: renglón no reconocido: {renglon[:60]}")

    for p in publicaciones:
        p["titulo"] = re.sub(r"\s+", " ", p["titulo"]).strip()
        p["periodo"] = _periodo(p["titulo"])
    return publicaciones, avisos, f"{semestre.group(1)} {anio}"


def _continua(titulo_anterior: str, renglon: str) -> bool:
    """¿El renglón es la continuación del título anterior (que quedó cortado en el PDF)?"""
    if renglon[0].islower() or renglon[0].isdigit():
        return True                                   # "consumo privado cultural. Año 2025", "2026-enero 2027"
    anterior = titulo_anterior.rstrip()
    incompleto = anterior.endswith((".", ",", " de", " del", " y")) and not TERMINA_EN_ANIO.search(anterior)
    return incompleto                                  # "...Supermercados y autoservicios mayoristas." + "Expectativas..."


def _periodo(titulo: str) -> str | None:
    """Último tramo del título, si indica un período: "Septiembre de 2026", "Tercer trimestre de 2026"."""
    if ". " not in titulo:
        return None
    ultimo = titulo.rsplit(". ", 1)[1].rstrip(".")
    return ultimo if re.search(r"\d{4}", ultimo) else None
