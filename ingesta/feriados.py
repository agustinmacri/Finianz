"""Carga de feriados en la base: librería holidays + ajustes manuales.

No usa internet: la librería trae los feriados de cualquier año.
Se corre desde actualizar.py (o sola la primera vez que un agente consulta feriados).
"""
import tomllib
from datetime import date, datetime

import holidays

import config
from admin_datos.db import conectar

# Calendario -> cómo obtenerlo de la librería
CALENDARIOS = {
    "AR": lambda anios: holidays.AR(years=anios),                                    # feriados nacionales
    "AR_BANCOS": lambda anios: holidays.AR(years=anios, categories=("public", "bank")),  # + Día del Bancario, etc.
    "BYMA": lambda anios: holidays.financial_holidays("BYMA", years=anios),          # días sin mercado local
    "US": lambda anios: holidays.US(years=anios),                                    # feriados federales de EE. UU.
    "NYSE": lambda anios: holidays.financial_holidays("NYSE", years=anios),          # días sin bolsa de EE. UU.
    "US_BONOS": lambda anios: holidays.financial_holidays("XSIF", years=anios),      # días sin mercado de Treasuries (SIFMA)
}

ARCHIVO_AJUSTES = config.CALENDARIOS_DIR / "feriados_ajustes.toml"

# Primer año que la librería cubre para BYMA (antes: aproximación con el calendario nacional)
BYMA_DESDE = holidays.financial_holidays("BYMA").start_year


class ErrorAjustes(Exception):
    """Error en calendarios/feriados_ajustes.toml, con un mensaje que indica qué corregir."""


def cargar(desde: int | None = None, hasta: int | None = None) -> dict:
    """Recarga los feriados entre dos años (por defecto, desde FERIADOS_DESDE hasta el año próximo).

    Reemplaza lo que había en ese rango: si la librería corrigió un feriado, la base queda al día.
    Devuelve un resumen con cuántos feriados se cargaron por calendario y cuántos ajustes se aplicaron.
    """
    desde = desde or config.FERIADOS_DESDE
    hasta = hasta or date.today().year + 1
    anios = list(range(desde, hasta + 1))
    ajustes = leer_ajustes()  # se valida antes de tocar la base: si el archivo tiene errores, no se borra nada

    resumen = {"desde": desde, "hasta": hasta, "por_calendario": {}, "ajustes": len(ajustes)}
    with conectar("feriados") as con:
        con.execute("DELETE FROM feriados WHERE fecha BETWEEN ? AND ?", (f"{desde}-01-01", f"{hasta}-12-31"))
        for calendario, obtener in CALENDARIOS.items():
            filas = [(d.isoformat(), calendario, nombre, "holidays") for d, nombre in obtener(anios).items()]
            con.executemany("INSERT OR REPLACE INTO feriados VALUES (?, ?, ?, ?)", filas)
            resumen["por_calendario"][calendario] = len(filas)

        # La librería tiene el calendario de BYMA recién desde 2026. Para los años anteriores
        # se usa el calendario nacional como aproximación, marcado como tal (fuente "aproximado").
        anios_sin_byma = [a for a in anios if a < BYMA_DESDE]
        if anios_sin_byma:
            filas = [(d.isoformat(), "BYMA", nombre, "aproximado") for d, nombre in holidays.AR(years=anios_sin_byma).items()]
            con.executemany("INSERT OR REPLACE INTO feriados VALUES (?, ?, ?, ?)", filas)
            resumen["por_calendario"]["BYMA"] += len(filas)
            resumen["byma_aproximado_hasta"] = BYMA_DESDE - 1

        for a in ajustes:
            if a["accion"] == "agregar":
                con.execute("INSERT OR REPLACE INTO feriados VALUES (?, ?, ?, 'ajuste')",
                            (a["fecha"], a["calendario"], a["nombre"]))
            else:
                con.execute("DELETE FROM feriados WHERE fecha = ? AND calendario = ?", (a["fecha"], a["calendario"]))

        ahora = datetime.now().isoformat(timespec="seconds")
        for clave, valor in (("feriados_desde", desde), ("feriados_hasta", hasta),
                             ("feriados_version_holidays", holidays.__version__)):
            con.execute("INSERT OR REPLACE INTO metadatos VALUES (?, ?, ?)", (clave, str(valor), ahora))
    return resumen


def leer_ajustes() -> list[dict]:
    """Lee y valida el archivo de ajustes. Si algo está mal, dice qué ajuste y qué campo."""
    if not ARCHIVO_AJUSTES.exists():
        return []
    try:
        datos = tomllib.loads(ARCHIVO_AJUSTES.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise ErrorAjustes(f"{ARCHIVO_AJUSTES.name} tiene un error de formato: {e}") from None

    ajustes = []
    for i, a in enumerate(datos.get("ajuste", []), start=1):
        donde = f"{ARCHIVO_AJUSTES.name}, ajuste n.º {i}"
        fecha = a.get("fecha")
        if isinstance(fecha, str):
            try:
                fecha = date.fromisoformat(fecha)
            except ValueError:
                raise ErrorAjustes(f"{donde}: la fecha '{fecha}' no tiene formato AAAA-MM-DD.") from None
        if not isinstance(fecha, date):
            raise ErrorAjustes(f"{donde}: falta la fecha o no tiene formato AAAA-MM-DD.")
        if a.get("calendario") not in CALENDARIOS:
            raise ErrorAjustes(f"{donde}: calendario '{a.get('calendario')}' inválido. Opciones: {', '.join(CALENDARIOS)}.")
        if a.get("accion") not in ("agregar", "quitar"):
            raise ErrorAjustes(f"{donde}: accion debe ser \"agregar\" o \"quitar\".")
        if a["accion"] == "agregar" and not a.get("nombre"):
            raise ErrorAjustes(f"{donde}: para agregar un feriado hace falta el nombre.")
        ajustes.append({"fecha": fecha.isoformat(), "calendario": a["calendario"], "accion": a["accion"],
                        "nombre": a.get("nombre", ""), "motivo": a.get("motivo", "")})
    return ajustes
