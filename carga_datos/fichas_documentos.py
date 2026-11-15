"""Lector de fichas técnicas desde documentos oficiales (llamados a licitación del Tesoro, sus resultados,
resoluciones de emisión o prospectos).

Flujo:
1. leer(fuente): baja el texto del documento (URL, PDF, HTML o TXT), un modelo extrae cada instrumento con sus
   condiciones (salida estructurada), y:
   - los que ya tienen ficha (reaperturas de bonos cargados) se informan y no se tocan;
   - los nuevos se guardan como BORRADORES (revisado = false) en renta_fija/fichas/borradores/borradores.toml;
   - si ya había un borrador del mismo instrumento (por ejemplo, del llamado) se completan los datos que faltaban
     (por ejemplo, el cupón o el ticker que trae el resultado de la licitación).
2. Revisás el borrador: podés editar el archivo para completar o corregir datos.
3. aprobar(ticker): valida la ficha con las mismas reglas que las demás y la pasa al archivo de su familia con
   revisado = true. Los borradores no los usa ninguna calculadora.

Resultados de licitación: de cada instrumento se lee qué se licitó (precio, tasa/TEM o margen) y el valor de corte.
   - Un precio de corte es un dato de mercado: se informa y la ficha no cambia.
   - La TEM o el margen de un instrumento nuevo completa su borrador (que después aprobás).
   - Si un bono que ya tiene ficha trae un dato de condiciones distinto del cargado, queda como CAMBIO PROPUESTO en
     renta_fija/fichas/borradores/cambios.toml; la ficha cambia solo si lo aplicás (aplicar <TICKER>).

Desde la terminal:
    python -m carga_datos.fichas_documentos leer <url o archivo>
    python -m carga_datos.fichas_documentos pendientes
    python -m carga_datos.fichas_documentos aprobar <TICKER>
    python -m carga_datos.fichas_documentos descartar <TICKER o clave>
    python -m carga_datos.fichas_documentos completar <TICKER o clave> campo=valor   (ej.: ticker=TMY27)
    python -m carga_datos.fichas_documentos cambios
    python -m carga_datos.fichas_documentos aplicar <TICKER> [campo]
    python -m carga_datos.fichas_documentos rechazar <TICKER> [campo]
"""
import re
import sys
import tomllib
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from renta_fija import leer_fichas

BORRADORES = leer_fichas.CARPETA / "borradores" / "borradores.toml"
MAX_CARACTERES = 80_000
ARCHIVO_DE_FAMILIA = {
    "cer_cero_cupon": "cer.toml", "cer_cupon": "cer_cupon.toml", "tasa_fija_capitalizable": "tasa_fija.toml",
    "tasa_fija_cupon": "tasa_fija.toml", "tasa_fija_descuento": "tasa_fija.toml", "tamar_capitalizable": "tamar.toml",
    "dolar_linked_bullet": "dolar_linked.toml", "dolar_linked_cupon": "dolar_linked.toml", "hard_dollar": "hard_dollar.toml",
}
CAMBIOS = None   # se resuelve en tiempo de ejecución: carpeta de borradores / cambios.toml
CAMPOS_COMPARABLES = ("emision", "vencimiento", "cupon", "margen", "frecuencia", "base", "ley")   # escalares de condiciones
ORDEN = ["ticker", "tipo", "familia", "ley", "par", "emision", "vencimiento", "cupon", "margen", "frecuencia", "base",
         "tramos", "pagos", "tipo_cambio_pago", "revisado", "fuente", "nota", "pendiente", "cita", "clave"]
Familia = Literal["cer_cero_cupon", "cer_cupon", "tasa_fija_capitalizable", "tasa_fija_cupon", "tasa_fija_descuento",
                  "tamar_capitalizable", "dolar_linked_bullet", "dolar_linked_cupon", "hard_dollar"]


# --- Lo que extrae el modelo ---

class Pago(BaseModel):
    fecha: str = Field(description="AAAA-MM-DD")
    amortizacion: float = Field(0.0, description="% del valor nominal original que amortiza ese día")


class Tramo(BaseModel):
    desde: str = Field(description="AAAA-MM-DD")
    tasa: float = Field(description="Tasa anual en fracción (0.06 = 6%)")


class Instrumento(BaseModel):
    nombre: str = Field(description="Nombre del instrumento como figura en el texto")
    ticker: str | None = Field(None, description="Ticker, si el texto lo dice")
    reapertura: bool = Field(False, description="True si es la reapertura de un instrumento existente")
    familia: Familia | None = None
    tipo: str | None = Field(None, description="LECAP, BONCAP, LEDE, BONTE, BONCER, LECER, BONO TAMAR, DUAL ..., BONO DL, LETRA DL, BONAR, GLOBAL u ON")
    emision: str | None = Field(None, description="Fecha de emisión AAAA-MM-DD")
    vencimiento: str | None = Field(None, description="Fecha de vencimiento AAAA-MM-DD")
    cupon: float | None = Field(None, description="TEM de emisión (capitalizables) o tasa anual del cupón, en fracción")
    margen: float | None = Field(None, description="Margen sobre la TAMAR, en fracción")
    frecuencia: int | None = Field(None, description="Pagos de interés por año")
    base: str | None = Field(None, description="30/360, actual/365 o actual/360")
    ley: str | None = Field(None, description="AR o NY (hard dollar)")
    pagos: list[Pago] = Field(default_factory=list)
    tramos: list[Tramo] = Field(default_factory=list)
    tipo_cambio_pago: str | None = Field(None, description="Tipo de cambio con el que se paga (dollar linked)")
    variable_licitada: Literal["precio", "tasa", "margen"] | None = Field(
        None, description="Solo en resultados: qué se licitó (precio, tasa/TEM o margen sobre la TAMAR)")
    valor_corte: float | None = Field(None, description="Solo en resultados: el valor de corte de la variable licitada. "
                                      "Precio tal cual figura (por 1.000 VNO); tasa o margen en fracción")
    tirea: float | None = Field(None, description="Solo en resultados: TIREA de corte, en fracción")
    pendiente: list[str] = Field(default_factory=list, description="Datos que faltan o se definen en la licitación")
    notas: str | None = None
    cita: str = Field("", description="Fragmento del texto con las condiciones")


class Documento(BaseModel):
    tipo_documento: str = Field(description="llamado a licitación, resultado de licitación, resolución, prospecto u otro")
    fecha_documento: str | None = Field(None, description="AAAA-MM-DD")
    instrumentos: list[Instrumento]


# --- Texto del documento ---

class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.partes, self._saltar = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._saltar += 1
        elif tag in ("p", "br", "li", "tr", "h1", "h2", "h3", "h4", "div", "td"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._saltar:
            self._saltar -= 1

    def handle_data(self, data):
        if not self._saltar:
            self.partes.append(data)


def _html_a_texto(html: str) -> str:
    lector = _TextoHTML()
    lector.feed(html)
    return re.sub(r"\n\s*\n+", "\n\n", re.sub(r"[ \t]+", " ", "".join(lector.partes))).strip()


def _pdf_a_texto(datos: bytes) -> str:
    import io
    from pypdf import PdfReader
    return "\n".join(pagina.extract_text() or "" for pagina in PdfReader(io.BytesIO(datos)).pages)


def obtener_texto(fuente: str) -> str:
    """Texto de una URL (página o PDF) o de un archivo local (.pdf, .html, .txt)."""
    if re.match(r"https?://", fuente):
        import requests
        respuesta = requests.get(fuente, timeout=60, headers={"User-Agent": "Mozilla/5.0 (Finianz)"})
        respuesta.raise_for_status()
        es_pdf = "pdf" in respuesta.headers.get("content-type", "") or fuente.lower().endswith(".pdf")
        texto = _pdf_a_texto(respuesta.content) if es_pdf else _html_a_texto(respuesta.text)
    else:
        ruta = Path(fuente).expanduser()
        if not ruta.exists():
            raise ValueError(f"No existe el archivo {ruta}.")
        if ruta.suffix.lower() == ".pdf":
            texto = _pdf_a_texto(ruta.read_bytes())
        else:
            contenido = ruta.read_text(encoding="utf-8", errors="replace")
            texto = _html_a_texto(contenido) if ruta.suffix.lower() in (".html", ".htm") else contenido
    if len(texto.strip()) < 200:
        raise ValueError("El documento casi no tiene texto (¿es una imagen escaneada?).")
    return texto[:MAX_CARACTERES]


def extraer_con_modelo(texto: str) -> Documento:
    """Le pide al modelo los instrumentos del documento con salida estructurada."""
    from graph.nodes import cargar_prompt, crear_modelos, invocar_con_respaldo, mensaje_sistema
    from langchain_core.messages import HumanMessage
    modelos = crear_modelos(preparar=lambda llm: llm.with_structured_output(Documento))
    return invocar_con_respaldo(modelos, [mensaje_sistema(cargar_prompt("lector_fichas.md")),
                                          HumanMessage(f"Documento:\n\n{texto}")])


# --- Borradores ---

def _fecha(texto: str | None) -> date | None:
    try:
        return date.fromisoformat(texto[:10]) if texto else None
    except ValueError:
        return None


def a_ficha(ins: Instrumento, origen: str, tipo_documento: str, fecha_documento: str | None) -> dict:
    """Convierte lo extraído en una ficha borrador."""
    if ins.valor_corte is not None and not ins.reapertura:      # la TEM o el margen de corte de un instrumento nuevo
        if ins.variable_licitada == "margen" and ins.margen is None:
            ins.margen = ins.valor_corte
        elif ins.variable_licitada == "tasa" and ins.cupon is None:
            ins.cupon = ins.valor_corte
    ficha = {"ticker": (ins.ticker or "").upper() or None, "tipo": ins.tipo, "familia": ins.familia, "ley": ins.ley,
             "emision": _fecha(ins.emision), "vencimiento": _fecha(ins.vencimiento), "cupon": ins.cupon,
             "margen": ins.margen, "frecuencia": ins.frecuencia, "base": ins.base,
             "tramos": [{"desde": _fecha(t.desde), "tasa": t.tasa} for t in ins.tramos] or None,
             "pagos": [{"fecha": _fecha(p.fecha), **({"amortizacion": p.amortizacion} if p.amortizacion else {})}
                       for p in ins.pagos] or None,
             "tipo_cambio_pago": ins.tipo_cambio_pago, "revisado": False,
             "fuente": f"{tipo_documento}{' del ' + fecha_documento if fecha_documento else ''} ({origen}); borrador del lector de fichas",
             "nota": ins.notas, "pendiente": ins.pendiente or None, "cita": ins.cita or None}
    ficha = {k: v for k, v in ficha.items() if v not in (None, "", [])}
    ficha["clave"] = ficha.get("ticker") or f"{ficha.get('familia', 'sin_familia')}-{ficha.get('vencimiento', 'sin_vto')}"
    return ficha


def _valor_toml(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {_valor_toml(x)}" for k, x in v.items()) + " }"
    if isinstance(v, list):
        if v and all(isinstance(x, dict) for x in v):
            return "[\n" + "".join(f"    {_valor_toml(x)},\n" for x in v) + "]"
        return "[" + ", ".join(_valor_toml(x) for x in v) + "]"
    raise ValueError(f"No sé escribir {type(v)} en TOML.")


def a_toml(ficha: dict) -> str:
    claves = [k for k in ORDEN if k in ficha] + [k for k in ficha if k not in ORDEN]
    return "[[bono]]\n" + "".join(f"{k} = {_valor_toml(ficha[k])}\n" for k in claves)


def _leer_borradores(ruta: Path | None = None) -> list[dict]:
    ruta = ruta or BORRADORES
    if not ruta.exists():
        return []
    return tomllib.loads(ruta.read_text(encoding="utf-8")).get("bono", [])


def _guardar_borradores(borradores: list[dict], ruta: Path | None = None):
    ruta = ruta or BORRADORES
    ruta.parent.mkdir(parents=True, exist_ok=True)
    encabezado = ("# Borradores de fichas del lector de documentos (carga_datos/fichas_documentos.py).\n"
                  "# No los usa ninguna calculadora. Revisalos, completá lo pendiente y aprobalos con:\n"
                  "#     python -m carga_datos.fichas_documentos aprobar <TICKER>\n\n")
    ruta.write_text(encabezado + "\n".join(a_toml(b) for b in borradores), encoding="utf-8")


def _ruta_cambios() -> Path:
    return CAMBIOS or BORRADORES.parent / "cambios.toml"


def _leer_cambios() -> list[dict]:
    ruta = _ruta_cambios()
    return tomllib.loads(ruta.read_text(encoding="utf-8")).get("cambio", []) if ruta.exists() else []


def _guardar_cambios(cambios: list[dict]):
    ruta = _ruta_cambios()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    encabezado = ("# Cambios propuestos a fichas ya aprobadas (datos de un documento que no coinciden con la ficha).\n"
                  "# La ficha no cambia hasta que los aplicás:  python -m carga_datos.fichas_documentos aplicar <TICKER>\n\n")
    cuerpo = "\n".join("[[cambio]]\n" + "".join(f"{k} = {_valor_toml(v)}\n" for k, v in c.items() if v is not None)
                       for c in cambios)
    ruta.write_text(encabezado + cuerpo, encoding="utf-8")


def _iguales(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) < 1e-9
    return str(a).strip().upper() == str(b).strip().upper()


def _proponer_cambios(ficha_nueva: dict, cargada: dict, cambios: list[dict]) -> list[str]:
    """Compara los datos de condiciones del documento con la ficha cargada y propone los que difieren."""
    propuestos = []
    obligatorios = leer_fichas.CAMPOS.get(cargada["familia"], ())
    for campo in CAMPOS_COMPARABLES:
        if campo not in ficha_nueva or (campo not in obligatorios and campo not in cargada):
            continue
        actual = cargada.get(campo)
        if actual is not None and _iguales(actual, ficha_nueva[campo]):
            continue
        previo = next((c for c in cambios if c["ticker"] == cargada["ticker"] and c["familia"] == cargada["familia"]
                       and c["campo"] == campo), None)
        if previo is not None:
            cambios.remove(previo)
        cambios.append({"ticker": cargada["ticker"], "familia": cargada["familia"], "campo": campo,
                        "actual": actual if actual is not None else "(vacío)", "nuevo": ficha_nueva[campo],
                        "fuente": ficha_nueva["fuente"].replace("; borrador del lector de fichas", ""),
                        "cita": ficha_nueva.get("cita")})
        propuestos.append(f"{cargada['ticker']} {campo}: {actual if actual is not None else '(vacío)'} → {ficha_nueva[campo]}")
    return propuestos


def _numero_ar(x: float, decimales: int = 2) -> str:
    return f"{x:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _texto_corte(ins: Instrumento) -> str | None:
    if ins.valor_corte is None and ins.tirea is None:
        return None
    nombre = ins.ticker or ins.nombre
    partes = []
    if ins.variable_licitada == "precio" and ins.valor_corte is not None:
        partes.append(f"precio de corte {_numero_ar(ins.valor_corte)}")
    elif ins.variable_licitada in ("tasa", "margen") and ins.valor_corte is not None:
        partes.append(f"{'TEM' if ins.variable_licitada == 'tasa' else 'margen'} de corte {_numero_ar(ins.valor_corte * 100)}%")
    if ins.tirea is not None:
        partes.append(f"TIREA {_numero_ar(ins.tirea * 100)}%")
    return f"{nombre}: " + ", ".join(partes)


def _mismo(a: dict, b: dict) -> bool:
    if a.get("ticker") and b.get("ticker"):
        return a["ticker"].upper() == b["ticker"].upper() and a.get("familia") == b.get("familia")
    return a.get("familia") == b.get("familia") and a.get("vencimiento") == b.get("vencimiento")


def _vencido(ficha: dict, hoy: date) -> bool:
    vto = ficha.get("vencimiento")
    return isinstance(vto, date) and vto < hoy


def leer(fuente: str, extractor=extraer_con_modelo, hoy: date | None = None) -> dict:
    """Lee un documento y actualiza los borradores. Devuelve el resumen de lo que hizo.

    Los instrumentos ya vencidos (vencimiento anterior a hoy) no se cargan: se informan y listo. Los borradores que
    vencieron mientras esperaban aprobación también se sacan."""
    hoy = hoy or date.today()
    texto = obtener_texto(fuente)
    documento = extractor(texto)
    existentes = leer_fichas.leer_todas()
    borradores = _leer_borradores()
    cambios = _leer_cambios()
    resumen = {"documento": documento.tipo_documento, "fecha": documento.fecha_documento, "ya_cargados": [],
               "vencidos": [], "nuevos": [], "completados": [], "sin_familia": [], "descartados": [],
               "cortes": [], "cambios": []}
    for b in [b for b in borradores if _vencido(b, hoy)]:
        borradores.remove(b)
        resumen["vencidos"].append(f"{b['clave']} (borrador, venció el {b['vencimiento']:%d/%m/%Y})")
    origen = fuente if re.match(r"https?://", fuente) else Path(fuente).name
    for ins in documento.instrumentos:
        corte = _texto_corte(ins)
        ficha = a_ficha(ins, origen, documento.tipo_documento, documento.fecha_documento)
        ticker = ficha.get("ticker")
        if corte:
            resumen["cortes"].append(corte)
        if _vencido(ficha, hoy):
            resumen["vencidos"].append(f"{ticker or ins.nombre} (venció el {ficha['vencimiento']:%d/%m/%Y})")
            continue
        cargadas = [f for f in existentes.get(ticker, []) if f["familia"] == ficha.get("familia") or not ficha.get("familia")] if ticker else []
        if cargadas:
            resumen["ya_cargados"].append(ticker)
            for cargada in cargadas if ficha.get("familia") else []:
                resumen["cambios"] += _proponer_cambios(ficha, cargada, cambios)
            sobrantes = [b for b in borradores if _mismo(b, {**ficha, "ticker": None})]   # el del llamado, sin ticker
            for b in sobrantes:
                borradores.remove(b)
                resumen["descartados"].append(b["clave"])
            continue
        if not ficha.get("familia"):
            resumen["sin_familia"].append(ins.nombre)
        previo = next((b for b in borradores if _mismo(b, ficha)), None)
        if previo is None:
            borradores.append(ficha)
            resumen["nuevos"].append(ficha["clave"])
            continue
        agregados = [k for k, v in ficha.items() if k not in previo and k not in ("clave",)]
        for k in agregados:
            previo[k] = ficha[k]
        if "pendiente" in previo:          # lo que ahora está deja de estar pendiente
            previo["pendiente"] = [p for p in previo["pendiente"] if p.split(":")[0].strip() not in previo]
            if not previo["pendiente"]:
                del previo["pendiente"]
        previo["fuente"] = f"{previo['fuente']}; completado con {ficha['fuente']}" if agregados else previo["fuente"]
        if previo.get("ticker"):
            previo["clave"] = previo["ticker"]
        resumen["completados"].append((previo["clave"], agregados))
    _guardar_borradores(borradores)
    if cambios or _ruta_cambios().exists():
        _guardar_cambios(cambios)
    return resumen


def pendientes() -> list[dict]:
    return _leer_borradores()


def aprobar(clave: str, carpeta: Path | None = None, por: str = "Agustin", hoy: date | None = None) -> str:
    """Valida el borrador y lo pasa al archivo de su familia con revisado = true."""
    hoy = hoy or date.today()
    borradores = _leer_borradores()
    elegido = next((b for b in borradores if b.get("clave", "").upper() == clave.upper()
                    or (b.get("ticker") or "").upper() == clave.upper()), None)
    if elegido is None:
        raise ValueError(f"No hay ningún borrador '{clave}'. Pendientes: {', '.join(b.get('clave', '?') for b in borradores) or 'ninguno'}.")
    ficha = {k: v for k, v in elegido.items() if k not in ("pendiente", "cita", "clave")}
    if not ficha.get("ticker"):
        raise leer_fichas.ErrorFicha("Al borrador le falta el ticker: completalo en el archivo de borradores.")
    if _vencido(ficha, hoy):
        raise leer_fichas.ErrorFicha(f"{ficha['ticker']} ya venció ({ficha['vencimiento']:%d/%m/%Y}): no hace falta cargarlo. Descartalo.")
    leer_fichas.validar(ficha, f"borrador {clave}")
    if any(f["familia"] == ficha["familia"] for f in leer_fichas.fichas_de(ficha["ticker"])):
        raise leer_fichas.ErrorFicha(f"{ficha['ticker']} ya tiene ficha en la familia {ficha['familia']}.")
    ficha["revisado"] = True
    ficha["fuente"] = f"{ficha.get('fuente', '')}; aprobado por {por} el {hoy:%d/%m/%Y}"
    destino = (carpeta or leer_fichas.CARPETA) / ARCHIVO_DE_FAMILIA[ficha["familia"]]
    with open(destino, "a", encoding="utf-8") as archivo:
        archivo.write("\n" + a_toml(ficha))
    _guardar_borradores([b for b in borradores if b is not elegido])
    return f"{ficha['ticker']} aprobado y agregado a {destino.name}."


def _convertir(valor: str):
    v = valor.strip()
    try:
        return date.fromisoformat(v)
    except ValueError:
        pass
    try:
        numero = float(v.replace(",", "."))
        return int(numero) if numero.is_integer() and "." not in v and "," not in v else numero
    except ValueError:
        return v.upper() if v.isalnum() and len(v) <= 6 else v


def completar(clave: str, campo: str, valor) -> str:
    """Completa o corrige un dato de un borrador (por ejemplo, el ticker que no venía en el resultado)."""
    campo = campo.strip()
    if campo not in CAMPOS_COMPARABLES + ("ticker", "tipo", "familia", "tipo_cambio_pago", "nota"):
        raise ValueError(f"'{campo}' no se completa así; editá el archivo de borradores.")
    valor = _convertir(valor) if isinstance(valor, str) else valor
    borradores = _leer_borradores()
    elegido = next((b for b in borradores if b.get("clave", "").upper() == clave.upper()
                    or (b.get("ticker") or "").upper() == clave.upper()), None)
    if elegido is None:
        raise ValueError(f"No hay ningún borrador '{clave}'.")
    elegido[campo] = valor
    if elegido.get("pendiente"):
        elegido["pendiente"] = [p for p in elegido["pendiente"] if p.split(":")[0].strip() != campo] or None
        if elegido["pendiente"] is None:
            del elegido["pendiente"]
    if campo == "ticker":
        elegido["clave"] = valor
    _guardar_borradores(borradores)
    return f"Borrador {elegido['clave']}: {campo} = {valor}."


def cambios_propuestos() -> list[dict]:
    return _leer_cambios()


def describir_cambios() -> str:
    lista = _leer_cambios()
    if not lista:
        return "No hay cambios propuestos a fichas aprobadas."
    return "\n".join(f"{c['ticker']} ({c['familia']}) {c['campo']}: {c['actual']} → {c['nuevo']} | {c['fuente']}"
                     + (f" | cita: {c['cita']}" if c.get("cita") else "") for c in lista)


def _elegir_cambios(ticker: str, campo: str | None) -> tuple[list[dict], list[dict]]:
    todos = _leer_cambios()
    elegidos = [c for c in todos if c["ticker"].upper() == ticker.upper() and (campo is None or c["campo"] == campo)]
    if not elegidos:
        raise ValueError(f"No hay cambios propuestos para {ticker}{' en ' + campo if campo else ''}.")
    return elegidos, [c for c in todos if c not in elegidos]


def _reemplazar_en_bloque(texto: str, ticker: str, familia: str, nuevos: dict, agregado_fuente: str) -> str:
    """Cambia campos escalares del [[bono]] de ese ticker en el texto del archivo, sin tocar el resto."""
    lineas = texto.split("\n")
    inicios = [i for i, l in enumerate(lineas) if l.strip() == "[[bono]]"] + [len(lineas)]
    for a, b in zip(inicios, inicios[1:]):
        bloque = lineas[a:b]
        if f'ticker = "{ticker}"' in bloque and f'familia = "{familia}"' in bloque:
            break
    else:
        raise leer_fichas.ErrorFicha(f"No encontré la ficha de {ticker} ({familia}) en el archivo.")
    for campo, valor in {**nuevos, "fuente": None}.items():
        posicion = next((i for i in range(a, b) if lineas[i].startswith(f"{campo} = ")), None)
        if campo == "fuente":
            actual = tomllib.loads(lineas[posicion])["fuente"] if posicion is not None else ""
            linea = f"fuente = {_valor_toml((actual + '; ' if actual else '') + agregado_fuente)}"
        else:
            linea = f"{campo} = {_valor_toml(valor)}"
        if posicion is not None:
            lineas[posicion] = linea
        else:
            ultimo = max(i for i in range(a, b) if lineas[i].strip())
            lineas.insert(ultimo + 1, linea)
            b += 1
    return "\n".join(lineas)


def aplicar(ticker: str, campo: str | None = None, carpeta: Path | None = None, por: str = "Agustin",
            hoy: date | None = None) -> str:
    """Aplica a la ficha aprobada los cambios propuestos de ese ticker (o solo uno), y los valida."""
    hoy = hoy or date.today()
    elegidos, resto = _elegir_cambios(ticker, campo)
    mensajes = []
    for familia in dict.fromkeys(c["familia"] for c in elegidos):
        delta = {c["campo"]: c["nuevo"] for c in elegidos if c["familia"] == familia}
        fuentes = "; ".join(dict.fromkeys(c["fuente"] for c in elegidos if c["familia"] == familia))
        archivo = (carpeta or leer_fichas.CARPETA) / ARCHIVO_DE_FAMILIA[familia]
        original = archivo.read_text(encoding="utf-8")
        nuevo = _reemplazar_en_bloque(original, elegidos[0]["ticker"], familia, delta,
                                      f"{', '.join(delta)} según {fuentes}, aprobado por {por} el {hoy:%d/%m/%Y}")
        archivo.write_text(nuevo, encoding="utf-8")
        try:
            leer_fichas.validar(leer_fichas.ficha(elegidos[0]["ticker"], familia), f"{archivo.name}, {ticker}")
            leer_fichas.leer_todas()
        except Exception:
            archivo.write_text(original, encoding="utf-8")
            raise
        mensajes.append(f"{elegidos[0]['ticker']} ({familia}): " + ", ".join(f"{k} = {v}" for k, v in delta.items()))
    _guardar_cambios(resto)
    return "Aplicado: " + "; ".join(mensajes) + "."


def rechazar(ticker: str, campo: str | None = None) -> str:
    elegidos, resto = _elegir_cambios(ticker, campo)
    _guardar_cambios(resto)
    return f"Rechazado{'s' if len(elegidos) > 1 else ''}: " + ", ".join(f"{c['ticker']} {c['campo']}" for c in elegidos) + ". La ficha no cambia."


def describir_borradores() -> str:
    """Texto con cada borrador completo, para revisarlo antes de aprobar."""
    lista = pendientes()
    texto = "\n\n".join(a_toml(b) for b in lista) if lista else "No hay borradores pendientes."
    return texto + "\n\nCambios propuestos a fichas aprobadas:\n" + describir_cambios()


def descartar(clave: str) -> str:
    borradores = _leer_borradores()
    quedan = [b for b in borradores if b.get("clave", "").upper() != clave.upper()
              and (b.get("ticker") or "").upper() != clave.upper()]
    if len(quedan) == len(borradores):
        raise ValueError(f"No hay ningún borrador '{clave}'.")
    _guardar_borradores(quedan)
    return f"Borrador {clave} descartado."


def describir(resumen: dict) -> str:
    lineas = [f"Documento: {resumen['documento']}{' del ' + resumen['fecha'] if resumen['fecha'] else ''}"]
    if resumen["ya_cargados"]:
        lineas.append("Ya tienen ficha (no se tocan): " + ", ".join(resumen["ya_cargados"]))
    if resumen.get("cortes"):
        lineas.append("Resultado de la licitación: " + "; ".join(resumen["cortes"])
                      + ". Los precios de corte son datos de mercado: no cambian las fichas.")
    if resumen.get("cambios"):
        lineas.append("Datos distintos de fichas ya aprobadas (cambios propuestos, la ficha NO cambia hasta que los apliques): "
                      + "; ".join(resumen["cambios"]))
    if resumen["vencidos"]:
        lineas.append("Ya vencidos, no se cargan: " + ", ".join(resumen["vencidos"]))
    if resumen["nuevos"]:
        lineas.append("Borradores nuevos: " + ", ".join(resumen["nuevos"]))
    for clave, campos in resumen["completados"]:
        lineas.append(f"Borrador {clave} completado" + (f" con: {', '.join(campos)}" if campos else " (sin datos nuevos)"))
    if resumen["descartados"]:
        lineas.append("Borradores descartados porque el bono ya tiene ficha: " + ", ".join(resumen["descartados"]))
    if resumen["sin_familia"]:
        lineas.append("Sin familia reconocida (revisar a mano): " + ", ".join(resumen["sin_familia"]))
    for b in pendientes():
        if b.get("pendiente"):
            lineas.append(f"  {b['clave']}: pendiente → " + "; ".join(b["pendiente"]))
    if resumen.get("cambios"):
        lineas.append("Aplicalos con: python -m carga_datos.fichas_documentos aplicar <TICKER> (o rechazar <TICKER>)")
    if pendientes():
        lineas.append(f"Revisá {BORRADORES.relative_to(leer_fichas.CARPETA.parent.parent)} y aprobá con: "
                      "python -m carga_datos.fichas_documentos aprobar <TICKER> (o pedíselo al agente de renta fija)")
    return "\n".join(lineas)


def main(argv: list[str]):
    if len(argv) < 1 or argv[0] not in ("leer", "pendientes", "aprobar", "descartar", "completar", "cambios",
                                        "aplicar", "rechazar"):
        print(__doc__)
        return
    try:
        if argv[0] == "leer":
            print(describir(leer(argv[1])))
        elif argv[0] == "pendientes":
            lista = pendientes()
            print("\n".join(f"{b['clave']}: {b.get('tipo', '?')} {b.get('familia', '?')} vence {b.get('vencimiento', '?')}"
                            + (f" | pendiente: {'; '.join(b['pendiente'])}" if b.get("pendiente") else "")
                            for b in lista) or "No hay borradores pendientes.")
        elif argv[0] == "aprobar":
            print(aprobar(argv[1]))
        elif argv[0] == "descartar":
            print(descartar(argv[1]))
        elif argv[0] == "completar":
            campo, _, valor = argv[2].partition("=")
            print(completar(argv[1], campo, valor))
        elif argv[0] == "cambios":
            print(describir_cambios())
        elif argv[0] == "aplicar":
            print(aplicar(argv[1], argv[2] if len(argv) > 2 else None))
        else:
            print(rechazar(argv[1], argv[2] if len(argv) > 2 else None))
    except (ValueError, leer_fichas.ErrorFicha, IndexError) as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main(sys.argv[1:])
