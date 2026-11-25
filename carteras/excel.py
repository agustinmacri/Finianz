"""Entrada y salida de carteras en Excel.

Cada cartera es un .xlsx en datos/carteras/ (esa carpeta no se sube al repo: son datos de clientes).
- Hoja "Cartera": una fila por activo con Ticker y Nominales (en acciones y CEDEARs, la cantidad). Opcionales:
  Tipo Activo y Descripcion (si faltan, salen de la ficha del bono o de PPI).
- Hoja "Liquidez" (opcional): liquidez, pasivos y créditos. Columnas: Tipo, Descripcion, Moneda (pesos, mep o ccl),
  Monto (en esa moneda; para pasivos, positivo: se resta solo), Tasa (TNA; opcional) y Vencimiento (opcional).
  Tipos: Liquidez (rinde 0), Money market, Caución colocadora, Plazo fijo, Crédito, Caución tomadora y Pasivo.
- Hoja "Supuestos" (opcional): Variable | Fuente, para la TIR nominal proyectada. Variables: inflacion, tamar,
  dolar_oficial, mep, ccl. Fuentes: las mismas del agente (rem, breakeven, mensual:2%, camino:..., escenario:<nombre>).
  Lo que no se indica usa el REM; para MEP y CCL, "rem" mantiene la brecha de hoy con el A3500 del REM.

La plantilla vacía está en carteras/plantilla_cartera.xlsx (python -m carteras plantilla la vuelve a generar).
"""
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import config

COLUMNAS = ["Tipo Activo", "Descripcion", "Ticker", "Tir Spread/Nominal", "Tir Nominal en base a proyeccion",
            "Nominales", "Precio", "Total", "% Cartera", "Duration Activo"]
SUPUESTOS = ("inflacion", "tamar", "dolar_oficial", "mep", "ccl")
# Liquidez, pasivos y créditos: subclase -> (categoría, signo). Los pasivos restan del patrimonio.
TIPOS_LIQUIDEZ = {"Liquidez": ("Liquidez", 1), "Money market": ("Liquidez", 1), "Caución colocadora": ("Liquidez", 1),
                  "Plazo fijo": ("Liquidez", 1), "Crédito": ("Créditos", 1), "Caución tomadora": ("Pasivos", -1),
                  "Pasivo": ("Pasivos", -1)}
MONEDAS_LIQUIDEZ = ("pesos", "mep", "ccl")
COLUMNAS_LIQUIDEZ = ["Tipo", "Descripcion", "Moneda", "Monto", "Tasa", "Vencimiento"]
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
class Liquidez:
    """Liquidez, pasivo o crédito. monto en su moneda y siempre positivo; tasa = TNA (None: 0)."""
    tipo: str
    moneda: str
    monto: float
    descripcion: str | None = None
    tasa: float | None = None
    vencimiento: date | None = None


@dataclass
class Cartera:
    nombre: str
    posiciones: list[Posicion]
    supuestos: dict[str, str] = field(default_factory=dict)
    liquidez: list[Liquidez] = field(default_factory=list)


def tipo_liquidez(texto) -> str:
    """El tipo de liquidez con su nombre oficial (sin importar acentos ni mayúsculas)."""
    tipo = next((t for t in TIPOS_LIQUIDEZ if _clave(t) == _clave(texto)), None)
    if tipo is None:
        raise ValueError(f"Tipo de liquidez desconocido '{texto}'. Opciones: {', '.join(TIPOS_LIQUIDEZ)}.")
    return tipo


def moneda_liquidez(texto) -> str:
    clave = _clave(texto) or "pesos"
    equivalencias = {"pesos": "pesos", "ars": "pesos", "peso": "pesos", "mep": "mep", "dolarmep": "mep", "usd": "mep",
                     "dolar": "mep", "ccl": "ccl", "cable": "ccl", "dolarccl": "ccl", "usdc": "ccl"}
    if clave not in equivalencias:
        raise ValueError(f"Moneda desconocida '{texto}': usá pesos, mep o ccl.")
    return equivalencias[clave]


def _tasa(valor) -> float | None:
    """TNA desde 0.35, 35, '35%' o '35,5%'. Vacío: None."""
    if valor in (None, ""):
        return None
    if isinstance(valor, str):
        texto = valor.strip().replace("%", "").replace(",", ".")
        if not texto:
            return None
        numero = float(texto)
        return numero / 100 if "%" in valor or numero > 1 else numero
    numero = float(valor)
    return numero / 100 if numero > 1 else numero


def _fecha(valor) -> date | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha inválida '{valor}': usá AAAA-MM-DD o DD/MM/AAAA.")


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
    liquidez = _leer_liquidez(libro, archivo.name)
    if inicio is None and liquidez:
        filas, inicio = [["Ticker", "Nominales"]], 0       # solo liquidez
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
    if not posiciones and not liquidez:
        raise ValueError(f"{archivo.name}: la cartera no tiene activos.")
    return Cartera(archivo.stem, posiciones, supuestos, liquidez)


def _leer_liquidez(libro, nombre_archivo: str) -> list[Liquidez]:
    hoja = next((libro[h] for h in libro.sheetnames if _clave(h) == "liquidez"), None)
    if hoja is None:
        return []
    filas = [list(f) for f in hoja.iter_rows(values_only=True)]
    inicio = next((i for i, f in enumerate(filas) if {"tipo", "monto"} <= {_clave(c) for c in f}), None)
    if inicio is None:
        return []
    enc = [_clave(c) for c in filas[inicio]]
    col = lambda nombre: enc.index(nombre) if nombre in enc else None
    i = {n: col(n) for n in ("tipo", "descripcion", "moneda", "monto", "tasa", "vencimiento")}
    dato = lambda f, n: f[i[n]] if i[n] is not None and i[n] < len(f) else None
    lista = []
    for f in filas[inicio + 1:]:
        if not dato(f, "tipo") and dato(f, "monto") in (None, ""):
            continue
        donde = f"{nombre_archivo}, hoja Liquidez, {dato(f, 'tipo') or 'fila sin tipo'}"
        try:
            monto = abs(float(dato(f, "monto")))
            lista.append(Liquidez(tipo_liquidez(dato(f, "tipo")), moneda_liquidez(dato(f, "moneda")), monto,
                                  (str(dato(f, "descripcion")).strip() or None) if dato(f, "descripcion") else None,
                                  _tasa(dato(f, "tasa")), _fecha(dato(f, "vencimiento"))))
        except (TypeError, ValueError) as e:
            raise ValueError(f"{donde}: {e}") from None
    return lista


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
    liquidez = [x for x in cartera.liquidez if x.tipo]
    if not posiciones and not liquidez:
        raise ValueError("La cartera no tiene activos.")
    for x in liquidez:
        x.tipo, x.moneda = tipo_liquidez(x.tipo), moneda_liquidez(x.moneda)
        try:
            x.monto = abs(float(x.monto))
        except (TypeError, ValueError):
            raise ValueError(f"El monto de {x.tipo} no es un número.") from None
        if x.monto == 0:
            raise ValueError(f"El monto de {x.tipo} {x.descripcion or ''} es cero.".replace("  ", " "))
        x.tasa = _tasa(x.tasa)
        x.vencimiento = _fecha(x.vencimiento)
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
    hoja_l = libro.create_sheet("Liquidez")
    hoja_l.append(COLUMNAS_LIQUIDEZ)
    for x in liquidez:
        hoja_l.append([x.tipo, x.descripcion or "", x.moneda, x.monto, x.tasa, x.vencimiento])
        hoja_l.cell(hoja_l.max_row, 5).number_format = "0.00%"
        hoja_l.cell(hoja_l.max_row, 6).number_format = "dd/mm/yyyy"
    hoja_l.column_dimensions["A"].width = 18
    hoja_l.column_dimensions["B"].width = 28
    hoja_s = libro.create_sheet("Supuestos")
    hoja_s.append(["Variable", "Fuente"])
    for v in SUPUESTOS:
        hoja_s.append([v, cartera.supuestos.get(v) or "rem"])
    for h in (hoja, hoja_l, hoja_s):
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
    liq = libro.create_sheet("Liquidez")
    liq.append(COLUMNAS_LIQUIDEZ + ["Tipos posibles"])
    for c in liq[1]:
        c.font = Font(bold=True)
    for fila in (["Liquidez", "Saldo en cuenta", "pesos", 500_000, None, None, ", ".join(TIPOS_LIQUIDEZ)],
                 ["Money market", "FCI money market", "pesos", 1_000_000, 0.30, None, "Moneda: pesos, mep o ccl"],
                 ["Liquidez", "Dólares MEP", "mep", 2_000, None, None, "Tasa: TNA (vacío = 0)"],
                 ["Caución tomadora", "Caución a 7 días", "pesos", 300_000, 0.32, None,
                  "Pasivos con monto positivo: se restan solos"]):
        liq.append(fila)
        liq.cell(liq.max_row, 5).number_format = "0.00%"
    for letra, ancho in zip("ABCDEFG", (18, 24, 9, 14, 9, 13, 60)):
        liq.column_dimensions[letra].width = ancho
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
    hoja.append(["Patrimonio", "", "", None, t["tir_proyectada_rf"], None, None, t["total"], 1.0, t["duration_rf"]])
    r = hoja.max_row
    hoja.cell(r, 1).font = Font(bold=True)
    hoja.cell(r, 5).number_format = "0.00%"
    hoja.cell(r, 8).number_format = "#,##0.00"
    hoja.cell(r, 9).number_format = "0.00%"
    hoja.cell(r, 10).number_format = "0.00"
    hoja.append(["TIR y duration ponderadas por monto: renta fija, liquidez, créditos y pasivos (la liquidez sin colocar "
                 "rinde 0 con duration 0). La renta variable no pondera."])
    for letra, ancho in zip("ABCDEFGHIJ", (18, 34, 10, 16, 18, 14, 14, 18, 11, 11)):
        hoja.column_dimensions[letra].width = ancho
    hoja.row_dimensions[encabezado].height = 32
    _hoja_composicion(libro, v)
    _hoja_cobros(libro, v)
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


def _encabezar(hoja, fila: int):
    from openpyxl.styles import Font, PatternFill
    for c in hoja[fila]:
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor="11523B")


def _hoja_composicion(libro, v: dict):
    from openpyxl.styles import Font
    h = libro.create_sheet("Composicion")
    c = v["cuadros"]
    moneda = v["nombre_moneda"]

    def bloque(titulo, encabezados, filas, formatos):
        h.append([titulo])
        h.cell(h.max_row, 1).font = Font(bold=True, size=12)
        h.append(encabezados)
        _encabezar(h, h.max_row)
        for valores, negrita in filas:
            h.append(valores)
            for col, formato in formatos.items():
                h.cell(h.max_row, col).number_format = formato
            if negrita:
                h.cell(h.max_row, 1).font = Font(bold=True)
        h.append([])

    bloque(f"Por clase de activo ({moneda})", ["Categoría", "Subclase", "Total", "% Cartera"],
           [([x["categoria"] if x["subclase"] is None else "", x["subclase"] or "", x["total"], x["peso"]],
             x["subclase"] is None) for x in c["categoria"]], {3: "#,##0.00", 4: "0.00%"})
    bloque(f"Por moneda ({moneda})", ["Moneda", "Total", "% Cartera"],
           [([x["moneda"], x["total"], x["peso"]], False) for x in c["moneda"]], {2: "#,##0.00", 3: "0.00%"})
    n = len(c["monedas"])
    bloque(f"Clase de activo y moneda ({moneda})", ["Categoría", "Subclase", *c["monedas"], "Total", "% Cartera"],
           [([x["categoria"], x["subclase"], *[x[m] or None for m in c["monedas"]], x["total"], x["peso"]], False)
            for x in c["clase_moneda"]], {**{3 + i: "#,##0.00" for i in range(n + 1)}, 4 + n: "0.00%"})
    bloque(f"Por emisor ({moneda})", ["Emisor", "Total", "% Cartera"],
           [([x["emisor"], x["total"], x["peso"]], False) for x in c["emisor"]], {2: "#,##0.00", 3: "0.00%"})
    for letra, ancho in zip("ABCDEFGHI", (30, 26, 18, 18, 18, 18, 18, 18, 12)):
        h.column_dimensions[letra].width = ancho


def _hoja_cobros(libro, v: dict):
    h = libro.create_sheet("Cobros")
    h.append([f"Cobros y vencimientos de los próximos {v['dias_cobros']} días"])
    h.append(["Fecha", "Ticker", "Concepto", "Moneda de pago", "Monto", f"Monto en {v['nombre_moneda']}", "Nota"])
    _encabezar(h, 2)
    for x in v["cobros"]:
        h.append([x["fecha"], x["ticker"], x["concepto"], x["moneda_pago"], x["monto"], x["monto_vista"], x["nota"]])
        h.cell(h.max_row, 1).number_format = "dd/mm/yyyy"
        h.cell(h.max_row, 5).number_format = "#,##0.00"
        h.cell(h.max_row, 6).number_format = "#,##0.00"
    if not v["cobros"]:
        h.append(["Sin cobros ni vencimientos en el período."])
    for letra, ancho in zip("ABCDEFG", (12, 14, 22, 15, 16, 20, 30)):
        h.column_dimensions[letra].width = ancho
