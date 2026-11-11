"""Carga del calendario de publicaciones de EE. UU. desde la API de FRED.

Qué publicaciones se cargan lo define el catálogo (calendarios/publicaciones.toml, fuente "fred"):
cada una indica su nombre exacto en FRED ('fred_release'). El id se busca por ese nombre,
así no hay números mágicos en el código.

Se cargan las fechas desde el 1 de enero del año pasado, incluidas las futuras que FRED ya
tiene programadas. Si FRED falla, la base no se toca: quedan las fechas de la carga anterior.
"""
import difflib
from datetime import date

from admin_datos.db import conectar
from carga_datos import catalogo
from conexiones import fred

FUENTE = "fred"


def cargar(desde: date | None = None) -> dict:
    """Reemplaza en la base las publicaciones de FRED. Puede lanzar ErrorAPI (sin tocar la base)."""
    desde = desde or date(date.today().year - 1, 1, 1)
    hoy = date.today().isoformat()
    seguidas = [p for p in catalogo.leer() if p["fuente"] == FUENTE]
    ids = fred.listar_publicaciones()

    filas, por_codigo, avisos = [], {}, []
    for p in seguidas:
        release_id, aviso = _buscar_id(p["fred_release"], ids)
        if aviso:
            avisos.append(f"{p['codigo']}: {aviso}")
        if release_id is None:
            continue
        fechas = fred.fechas_publicacion(release_id, desde.isoformat())
        futuras = [f for f in fechas if f >= hoy]
        por_codigo[p["codigo"]] = {"fechas": len(fechas), "proxima": futuras[0] if futuras else None}
        if not futuras:
            avisos.append(f"{p['codigo']}: FRED no tiene fechas futuras programadas.")
        filas += [(f, p.get("hora"), "US", p["organismo"], p["codigo"], p["nombre"], None, p["importancia"], FUENTE)
                  for f in fechas]

    # Se escribe recién al final: si algo falló antes, la base queda como estaba
    with conectar("publicaciones") as con:
        con.execute("DELETE FROM publicaciones WHERE fuente = ?", (FUENTE,))
        con.executemany("INSERT OR REPLACE INTO publicaciones VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", filas)

    return {
        "total": len(filas),
        "desde": min((f[0] for f in filas), default=None),
        "hasta": max((f[0] for f in filas), default=None),
        "por_codigo": por_codigo,
        "avisos": avisos,
    }


def _buscar_id(nombre: str, ids: dict[str, int]) -> tuple[int | None, str | None]:
    """Id de FRED para un nombre del catálogo. Devuelve (id, aviso)."""
    exactos = {n.lower(): i for n, i in ids.items()}
    if nombre.lower() in exactos:
        return exactos[nombre.lower()], None
    parecidos = difflib.get_close_matches(nombre, list(ids), n=3, cutoff=0.6)
    sugerencia = f" ¿Quisiste decir: {' | '.join(parecidos)}?" if parecidos else ""
    return None, f"no existe en FRED una publicación llamada '{nombre}' (revisá 'fred_release').{sugerencia}"
