"""Entrada y salida de carteras en Excel.

Cada cartera es un .xlsx en datos/carteras/ (esa carpeta no se sube al repo: son datos de clientes).
- Hoja "Cartera": una fila por activo con Ticker y Nominales (en acciones y CEDEARs, la cantidad). Opcionales:
  Tipo Activo y Descripcion (si faltan, salen de la ficha del bono o de PPI).
- Hoja "Supuestos" (opcional): Variable | Fuente, para la TIR nominal proyectada. Variables: inflacion, tamar,
  dolar_oficial, mep, ccl. Fuentes: las mismas del agente (rem, breakeven, mensual:2%, camino:..., escenario:<nombre>).
  Lo que no se indica usa el REM; para MEP y CCL, "rem" mantiene la brecha de hoy con el A3500 del REM.

La plantilla vacía está en carteras/plantilla_cartera.xlsx (python -m carteras plantilla la vuelve a generar).
"""
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import config

COLUMNAS = ["Tipo Activo", "Descripcion", "Ticker", "Tir Spread/Nominal", "Tir Nominal en base a proyeccion",
            "Nominales", "Precio", "Total", "% Cartera", "Duration Activo"]
SUPUESTOS = ("inflacion", "tamar", "dolar_oficial", "mep", "ccl")
PLANTILLA = Path(__file__).resolve().parent / "plantilla_cartera.xlsx"


def carpeta() -> Path:
    return config.DATOS_DIR / "carteras"


@dataclass
class Posicion:
    ticker: str
    nominales: float
    tipo: str | None = None
    descripcion: str | None = None


@dataclass
class Cartera:
    nombre: str
    posiciones: list[Posicion]
    supuestos: dict[str, str] = field(default_factory=dict)


def _clave(texto) -> str:
    plano = unicodedata.normalize("NFD", str(texto or "")).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in plano if c.isalnum())


def listar() -> list[str]:
    return sorted(p.stem for p in carpeta().glob("*.xlsx") if not p.stem.startswith("~$"))


def ruta(nombre: str) -> Path:
    directa = Path(nombre)
    if directa.suffix == ".xlsx" and directa.exists():
        return directa
    candidata = carpeta() / f"{nombre}.xlsx"
    if candidata.exists():
        return candidata
    disponibles = listar()
    parecida = next((n for n in disponibles if _clave(n) == _clave(nombre)), None)
    if parecida:
        return carpeta() / f"{parecida}.xlsx"
    raise ValueError(f"No encontré la cartera '{nombre}' en {carpeta()}. Disponibles: {', '.join(disponibles) or 'ninguna'}.")


def leer(nombre: str) -> Cartera:
    from openpyxl import load_workbook
    archivo = ruta(nombre)
    libro = load_workbook(archivo, data_only=True, read_only=True)
    hoja = next((libro[h] for h in libro.sheetnames if _clave(h) == "cartera"), libro[libro.sheetnames[0]])
    filas = [list(f) for f in hoja.iter_rows(values_only=True)]
    inicio = next((i for i, f in enumerate(filas) if "ticker" in {_clave(c) for c in f}), None)
    if inicio is None:
        raise ValueError(f"{archivo.name}: no encontré la fila de encabezados con la columna Ticker.")
    encabezados = [_clave(c) for c in filas[inicio]]
    col = lambda *nombres: next((encabezados.index(n) for n in nombres if n in encabezados), None)
    i_ticker, i_nom = col("ticker"), col("nominales", "cantidad", "vn", "valornominal")
    i_tipo, i_desc = col("tipoactivo", "tipo"), col("descripcion")
    if i_nom is None:
        raise ValueError(f"{archivo.name}: falta la columna Nominales (o Cantidad).")
    posiciones = []
    for f in filas[inicio + 1:]:
        ticker = str(f[i_ticker] or "").strip().upper() if i_ticker < len(f) else ""
        if not ticker:
            continue
        try:
            nominales = float(f[i_nom])
        except (TypeError, ValueError):
            raise ValueError(f"{archivo.name}: los nominales de {ticker} no son un número ({f[i_nom]!r}).")
        posiciones.append(Posicion(ticker, nominales,
                                   (str(f[i_tipo]).strip() or None) if i_tipo is not None and f[i_tipo] else None,
                                   (str(f[i_desc]).strip() or None) if i_desc is not None and f[i_desc] else None))
    supuestos = {}
    hoja_s = next((libro[h] for h in libro.sheetnames if _clave(h) == "supuestos"), None)
    if hoja_s is not None:
        for fila in hoja_s.iter_rows(values_only=True):
            if len(fila) >= 2 and fila[0] and fila[1] and _clave(fila[0]) in {_clave(s) for s in SUPUESTOS}:
                variable = next(s for s in SUPUESTOS if _clave(s) == _clave(fila[0]))
                supuestos[variable] = str(fila[1]).strip()
    if not posiciones:
        raise ValueError(f"{archivo.name}: la cartera no tiene activos.")
    return Cartera(archivo.stem, posiciones, supuestos)


PROHIBIDOS = set('<>:"/\\|?*')


def validar_nombre(nombre: str) -> str:
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        raise ValueError("Poné un nombre para la cartera.")
    if PROHIBIDOS & set(nombre) or nombre.startswith((".", "~")):
        raise ValueError("El nombre no puede tener < > : \" / \\ | ? * ni empezar con punto.")
    return nombre


def guardar(cartera: Cartera, nombre_anterior: str | None = None) -> Path:
    """Escribe la cartera (hojas Cartera y Supuestos) en datos/carteras/<nombre>.xlsx. Si se renombró, el archivo
    anterior pasa a datos/carteras/anteriores/ (no se borra nada)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    nombre = validar_nombre(cartera.nombre)
    posiciones = [Posicion(str(p.ticker).strip().upper(), p.nominales, p.tipo, p.descripcion)
                  for p in cartera.posiciones if p.ticker and str(p.ticker).strip()]
    if not posiciones:
        raise ValueError("La cartera no tiene activos.")
    vistos = set()
    for p in posiciones:
        if p.ticker in vistos:
            raise ValueError(f"{p.ticker} está repetido: sumá los nominales en una sola fila.")
        vistos.add(p.ticker)
    carpeta().mkdir(parents=True, exist_ok=True)
    destino = carpeta() / f"{nombre}.xlsx"
    if nombre_anterior is not None and _clave(nombre_anterior) != _clave(nombre) and destino.exists():
        raise ValueError(f"Ya existe una cartera llamada {nombre}.")
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Cartera"
    hoja.append(["Tipo Activo", "Descripcion", "Ticker", "Nominales"])
    for p in posiciones:
        try:
            nominales = float(p.nominales)
        except (TypeError, ValueError):
            raise ValueError(f"Los nominales de {p.ticker} no son un número.") from None
        if nominales <= 0:
            raise ValueError(f"Los nominales de {p.ticker} tienen que ser mayores que cero.")
        hoja.append([p.tipo or "", p.descripcion or "", p.ticker, nominales])
    hoja_s = libro.create_sheet("Supuestos")
    hoja_s.append(["Variable", "Fuente"])
    for v in SUPUESTOS:
        hoja_s.append([v, cartera.supuestos.get(v) or "rem"])
    for h in (hoja, hoja_s):
        for c in h[1]:
            c.font = Font(bold=True)
    hoja.column_dimensions["A"].width = 16
    hoja.column_dimensions["B"].width = 30
    libro.save(destino)
    if nombre_anterior is not None and _clave(nombre_anterior) != _clave(nombre):
        archivar(nombre_anterior)
    return destino


def archivar(nombre: str) -> Path:
    """Saca una cartera de la lista sin borrarla: la mueve a datos/carteras/anteriores/ con la fecha y hora."""
    from datetime import datetime
    origen = ruta(nombre)
    destino = carpeta() / "anteriores" / f"{origen.stem}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    destino.parent.mkdir(parents=True, exist_ok=True)
    origen.rename(destino)
    return destino


def crear_plantilla(destino: Path = PLANTILLA) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Cartera"
    hoja.append(["Tipo Activo", "Descripcion", "Ticker", "Nominales"])
    for c in hoja[1]:
        c.font = Font(bold=True)
    for fila in (["", "", "TZXD7", 1_000_000], ["", "", "S29E7", 500_000], ["", "", "AL30", 10_000],
                 ["", "", "GD30", 10_000], ["Acción", "", "GGAL", 200]):
        hoja.append(fila)
    hoja.column_dimensions["A"].width = 16
    hoja.column_dimensions["B"].width = 30
    supuestos = libro.create_sheet("Supuestos")
    supuestos.append(["Variable", "Fuente", "Opciones"])
    for c in supuestos[1]:
        c.font = Font(bold=True)
    for v, f, o in (("inflacion", "rem", "rem, breakeven, mensual:2%, camino:2026-12=2%;2027=22%;resto=1.5%, escenario:<nombre>"),
                    ("tamar", "rem", "rem, actual, tna:30%, camino:..., escenario:<nombre>"),
                    ("dolar_oficial", "rem", "rem, breakeven, mensual:1.5%, camino:..., escenario:<nombre>"),
                    ("mep", "rem", "rem (brecha de hoy con el A3500 del REM), mensual:1.5%, camino:..., escenario:<nombre>"),
                    ("ccl", "rem", "rem (brecha de hoy con el A3500 del REM), mensual:1.5%, camino:..., escenario:<nombre>")):
        supuestos.append([v, f, o])
    supuestos.column_dimensions["A"].width = 16
    supuestos.column_dimensions["B"].width = 20
    supuestos.column_dimensions["C"].width = 90
    libro.save(destino)
    return destino


def guardar_valuacion(v: dict) -> Path:
    """Escribe la cartera valuada en datos/carteras/salidas/<nombre>_<fecha>_<moneda>.xlsx, con formato."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    destino = carpeta() / "salidas"
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"{v['nombre']}_{v['fecha']:%Y-%m-%d}_{v['moneda']}.xlsx"
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Cartera"
    hoja.append([f"Cartera {v['nombre']} — {v['fecha']:%d/%m/%Y} — valuada en {v['nombre_moneda']}"])
    hoja["A1"].font = Font(bold=True, size=13)
    hoja.append([v["nota_valuacion"]])
    hoja.append([])
    hoja.append(COLUMNAS)
    encabezado = hoja.max_row
    for c in hoja[encabezado]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="11523B")
        c.alignment = Alignment(wrap_text=True, vertical="center")
    for fila in v["filas"]:
        hoja.append([fila["tipo"], fila["descripcion"], fila["ticker"], fila["tir_propia"], fila["tir_proyectada"],
                     fila["nominales"], fila["precio"], fila["total"], fila["peso"], fila["duration"]])
        r = hoja.max_row
        if fila["tir_propia"] is not None:
            hoja.cell(r, 4).number_format = f'"{fila["referencia"]} + "0.00%' if fila["referencia"] else "0.00%"
        hoja.cell(r, 5).number_format = "0.00%"
        hoja.cell(r, 6).number_format = "#,##0"
        hoja.cell(r, 7).number_format = "#,##0.00"
        hoja.cell(r, 8).number_format = "#,##0.00"
        hoja.cell(r, 9).number_format = "0.00%"
        hoja.cell(r, 10).number_format = "0.00"
    t = v["totales"]
    hoja.append([])
    hoja.append(["Total cartera", "", "", None, None, None, None, t["total"], 1.0, None])
    hoja.append(["Renta fija", "", "", None, t["tir_proyectada_rf"], None, None, t["total_rf"], t["peso_rf"], t["duration_rf"]])
    if t["total_rv"]:
        hoja.append(["Renta variable", "", "", None, None, None, None, t["total_rv"], t["peso_rv"], None])
    for r in range(hoja.max_row - (2 if not t["total_rv"] else 3) + 1, hoja.max_row + 1):
        hoja.cell(r, 1).font = Font(bold=True)
        hoja.cell(r, 5).number_format = "0.00%"
        hoja.cell(r, 8).number_format = "#,##0.00"
        hoja.cell(r, 9).number_format = "0.00%"
        hoja.cell(r, 10).number_format = "0.00"
    for letra, ancho in zip("ABCDEFGHIJ", (18, 34, 10, 16, 18, 14, 14, 18, 11, 11)):
        hoja.column_dimensions[letra].width = ancho
    hoja.row_dimensions[encabezado].height = 32
    s = libro.create_sheet("Supuestos")
    s.append(["Variable", "Supuesto usado"])
    for c in s[1]:
        c.font = Font(bold=True)
    for variable, descripcion in v["supuestos"].items():
        s.append([variable, descripcion])
    s.column_dimensions["A"].width = 16
    s.column_dimensions["B"].width = 120
    if v["avisos"]:
        a = libro.create_sheet("Avisos")
        for aviso in v["avisos"]:
            a.append([aviso])
        a.column_dimensions["A"].width = 140
    libro.save(archivo)
    return archivo
