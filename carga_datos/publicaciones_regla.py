"""Carga de las publicaciones que salen según una regla de días hábiles.

Ejemplo: el ISM manufacturero sale el primer día hábil de cada mes. La regla se define
en el catálogo (calendarios/publicaciones.toml, fuente "regla") con estos campos:
    dia_habil   qué día hábil del mes (1 = primero)
    calendario  con qué feriados se cuentan los días hábiles (AR, BANCOS, BYMA, NYSE, US, US_BONOS)
    excluir     opcional: días del año en que el organismo no publica aunque sean hábiles, como "MM-DD"
                (ej.: el ISM no publica el 2 de enero)
    periodo     opcional: "mes_anterior" si la publicación informa el mes anterior

Usa la base de feriados, así que se carga después de ella y cubre los mismos años.
Las fechas son estimadas: si el organismo publica una excepción, se corrige con una carga manual.
"""
from datetime import date, timedelta

from admin_datos import feriados
from admin_datos.db import conectar
from carga_datos import catalogo

FUENTE = "regla"
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
         "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def cargar() -> dict:
    """Reemplaza en la base las publicaciones calculadas por regla, para los años con feriados cargados."""
    rango = feriados.rango_cargado()
    if not rango:
        raise ValueError("Primero hay que cargar los feriados (python actualizar.py).")
    # Desde el año pasado (como FRED) hasta el último año con feriados
    desde_anio, hasta_anio = max(rango[0], date.today().year - 1), rango[1]

    filas, por_codigo = [], {}
    for p in (p for p in catalogo.leer() if p["fuente"] == FUENTE):
        fechas = [fecha_del_mes(anio, mes, p["dia_habil"], p["calendario"], p.get("excluir", []))
                  for anio in range(desde_anio, hasta_anio + 1) for mes in range(1, 13)]
        for f in fechas:
            filas.append((f.isoformat(), p.get("hora"), p["pais"], p["organismo"], p["codigo"], p["nombre"],
                          _periodo(f, p.get("periodo")), p["importancia"], FUENTE))
        hoy = date.today()
        por_codigo[p["codigo"]] = next((f.isoformat() for f in fechas if f >= hoy), None)

    with conectar("publicaciones") as con:
        con.execute("DELETE FROM publicaciones WHERE fuente = ?", (FUENTE,))
        con.executemany("INSERT OR REPLACE INTO publicaciones VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", filas)
    return {"total": len(filas), "desde": f"{desde_anio}-01", "hasta": f"{hasta_anio}-12", "proximas": por_codigo}


def fecha_del_mes(anio: int, mes: int, numero: int, calendario: str, excluir: list[str]) -> date:
    """El día hábil número 'numero' del mes, según los feriados del calendario y sin los días excluidos."""
    inicio = date(anio, mes, 1)
    fin = (inicio + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    cerrados = {f["fecha"] for f in feriados.feriados_entre(inicio, fin, [feriados.MERCADOS[calendario]])}
    habiles = [d for d in (inicio + timedelta(days=i) for i in range(fin.day))
               if d.weekday() < 5 and d.isoformat() not in cerrados and d.strftime("%m-%d") not in excluir]
    if numero > len(habiles):
        raise ValueError(f"{MESES[mes - 1]} de {anio} tiene solo {len(habiles)} días hábiles.")
    return habiles[numero - 1]


def _periodo(fecha: date, regla: str | None) -> str | None:
    if regla != "mes_anterior":
        return None
    anterior = fecha.replace(day=1) - timedelta(days=1)
    return f"{MESES[anterior.month - 1]} de {anterior.year}"
