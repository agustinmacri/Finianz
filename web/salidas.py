"""Convierte las salidas de texto de las herramientas (renglones con columnas separadas por " | ") en tablas.

El panel no calcula nada: llama a las mismas herramientas que usa el agente y muestra lo que devuelven. Este módulo
solo reconoce las tablas dentro del texto para mostrarlas como tablas y graficar los caminos.
"""
import re

import pandas as pd


def bloques(texto: str) -> list[tuple[str, object]]:
    """Parte el texto en bloques ("texto", str) y ("tabla", DataFrame). Una tabla es una serie de renglones con
    " | " y la misma cantidad de columnas; el primero es el encabezado."""
    salida, buffer, filas = [], [], []

    def cerrar_tabla():
        nonlocal filas
        if len(filas) >= 2:
            ancho = len(filas[0])
            datos = [f[:ancho] + [""] * (ancho - len(f)) for f in filas[1:]]
            salida.append(("tabla", pd.DataFrame(datos, columns=_unicos(filas[0]))))
        elif filas and _es_encabezado(filas[0]):
            buffer.append("_(sin bonos para comparar en este cruce)_")
        elif filas:
            buffer.append(" | ".join(filas[0]))
        filas = []

    def cerrar_texto():
        nonlocal buffer
        # Un renglón en blanco separa bloques (así un título queda solo y el panel lo puede destacar)
        for parte in "\n".join(buffer).split("\n\n"):
            if parte.strip():
                salida.append(("texto", parte.strip()))
        buffer = []

    for renglon in texto.splitlines():
        celdas = [c.strip() for c in renglon.split(" | ")] if " | " in renglon else None
        if celdas and ": " in celdas[0]:
            celdas = None            # "Acumulada …: usada 2% | REM 3%" o "Sin precio: … | …" es texto, no una fila
        if celdas:
            # Un encabezado nuevo (o un renglón más ancho que el encabezado) empieza otra tabla
            if filas and (_es_encabezado(celdas) or len(celdas) > len(filas[0]) + 1):
                cerrar_tabla()
            if not filas:
                cerrar_texto()
            filas.append(celdas)
        else:
            cerrar_tabla()
            buffer.append(renglon)
    cerrar_tabla()
    cerrar_texto()
    return salida


def _es_encabezado(celdas: list[str]) -> bool:
    return celdas[0] in ("Bono", "Mes", "Año") or celdas[0].startswith("Año (")


def _unicos(columnas: list[str]) -> list[str]:
    vistos, salida = {}, []
    for c in columnas:
        vistos[c] = vistos.get(c, 0) + 1
        salida.append(c if vistos[c] == 1 else f"{c} ({vistos[c]})")
    return salida


def numero(celda: str) -> float | None:
    """'2.15%' → 0.0215; '1,500.00 (+1.5%)' → 1500.0; '–' → None. El asterisco (dato extendido) se ignora."""
    if celda is None:
        return None
    texto = str(celda).strip().rstrip("*")
    m = re.match(r"^([+−-]?[\d,]*\.?\d+)\s*(%?)", texto.replace("−", "-"))
    if not m:
        return None
    valor = float(m.group(1).replace(",", ""))
    return valor / 100 if m.group(2) == "%" else valor


def tabla_de_meses(texto: str) -> pd.DataFrame | None:
    """La tabla mes a mes del camino (la que empieza con "Mes |"), con números: una columna por fuente."""
    for tipo, contenido in bloques(texto):
        if tipo == "tabla" and contenido.columns[0] == "Mes":
            df = contenido.set_index("Mes")
            return df.apply(lambda col: col.map(numero))
    return None
