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

Reaperturas: si el bono ya tiene ficha, se ignora. Si no la tiene, queda como borrador SIN fecha de emisión (la del
   aviso es la de esta licitación, no la original) y con la emisión original como pendiente: se completa leyendo la
   resolución o el prospecto de la primera emisión.

   La búsqueda del documento de la primera emisión (búsqueda web con el modelo) está en pausa: corre solo a pedido
   (emision <clave>). Lo que funciona: leer <URL> --solo <clave> con el link de la primera emisión.

Posibles duplicados: un borrador cuya familia, vencimiento y cupón o margen coinciden con un bono ya cargado (pasa con
   emisiones viejas en las que el bono todavía no tenía ticker) no se aprueba solo: o es el mismo (vincular) o es otro
   y lo confirmás como nuevo (aprobar --nuevo).

Tickers: el Tesoro asigna el ticker cerca de la liquidación. Para los borradores sin ticker se prueban los nombres
   que salen de la convención del Tesoro (S14G6, X29E7, D31M7, TZXD7, M30A7...) contra el buscador de PPI (solo
   datos de mercado); si aparece uno solo, se completa y queda anotado para que lo verifiques al aprobar.

Resultados de licitación: de cada instrumento se lee qué se licitó (precio, tasa/TEM o margen) y el valor de corte.
   - Un precio de corte es un dato de mercado: se informa y la ficha no cambia.
   - La TEM o el margen de un instrumento nuevo completa su borrador (que después aprobás).
   - Si un bono que ya tiene ficha trae un dato de condiciones distinto del cargado, queda como CAMBIO PROPUESTO en
     renta_fija/fichas/borradores/cambios.toml; la ficha cambia solo si lo aplicás (aplicar <TICKER>).

Desde la terminal:
    python -m fuentes_datos.carga.fichas_documentos leer <url o archivo>
    python -m fuentes_datos.carga.fichas_documentos pendientes
    python -m fuentes_datos.carga.fichas_documentos aprobar <TICKER>
    python -m fuentes_datos.carga.fichas_documentos descartar <TICKER o clave>
    python -m fuentes_datos.carga.fichas_documentos completar <TICKER o clave> campo=valor   (ej.: ticker=TMY27)
    python -m fuentes_datos.carga.fichas_documentos aprobar <TICKER> --nuevo   (si parece un bono ya cargado y no lo es)
    python -m fuentes_datos.carga.fichas_documentos vincular <clave> <TICKER>  (el borrador es un bono ya cargado: se descarta)
    python -m fuentes_datos.carga.fichas_documentos tickers                    (busca en PPI el ticker de los borradores sin ticker)
    python -m fuentes_datos.carga.fichas_documentos emision <clave> [--detalle] (busca y lee el documento de la primera emisión)
    python -m fuentes_datos.carga.fichas_documentos leer <URL> --solo <clave>  (de ese documento, solo los datos de ese bono)
    python -m fuentes_datos.carga.fichas_documentos cambios
    python -m fuentes_datos.carga.fichas_documentos aplicar <TICKER> [campo]
    python -m fuentes_datos.carga.fichas_documentos rechazar <TICKER> [campo]
"""
import re
import sys
import tomllib
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from renta_fija import leer_fichas

BORRADORES = leer_fichas.CARPETA / "borradores" / "borradores.toml"
MAX_CARACTERES = 300_000   # los avisos con muchos instrumentos y cupones mensuales pasan los 100.000
ARCHIVO_DE_FAMILIA = {
    "cer_cero_cupon": "cer.toml", "cer_cupon": "cer_cupon.toml", "tasa_fija_capitalizable": "tasa_fija.toml",
    "tasa_fija_cupon": "tasa_fija.toml", "tasa_fija_descuento": "tasa_fija.toml", "tamar_capitalizable": "tamar.toml",
    "dolar_linked_bullet": "dolar_linked.toml", "dolar_linked_cupon": "dolar_linked.toml", "hard_dollar": "hard_dollar.toml",
}
CAMBIOS = None   # se resuelve en tiempo de ejecución: carpeta de borradores / cambios.toml
CAMPOS_COMPARABLES = ("emision", "vencimiento", "cupon", "margen", "frecuencia", "base", "ley")   # escalares de condiciones
MARGEN_EMISION_ORIGINAL = 7   # días: una "emisión" posterior a (aviso − 7 días) en una reapertura es la de esta licitación
LETRAS_MES = "EFMAYJLGSOND"   # convención del Tesoro: ene=E, feb=F, mar=M, abr=A, may=Y, jun=J, jul=L, ago=G, ...
BUSCADOR = None               # función ticker -> lista de instrumentos (PPI); se resuelve en tiempo de ejecución
SOLO_BORRADOR = ("pendiente", "cita", "clave", "reapertura", "posible_duplicado", "emision_buscada", "dual_con",
                 "confirmado_nuevo")
# Duales: un borrador por pata, con la clave TICKER-PATA (TMVE8-DL y TMVE8-TAMAR); cada uno se aprueba por separado
SUFIJO_PATA = {"cer_cero_cupon": "CER", "cer_cupon": "CER", "tasa_fija_capitalizable": "TF", "tasa_fija_cupon": "TF",
               "tasa_fija_descuento": "TF", "tamar_capitalizable": "TAMAR", "dolar_linked_bullet": "DL",
               "dolar_linked_cupon": "DL", "hard_dollar": "HD"}
BUSCADOR_WEB = None           # función consulta -> lista de URLs; por defecto, el modelo con búsqueda de Google
DOMINIOS_OFICIALES = ("argentina.gob.ar", "boletinoficial.gob.ar", "economia.gob.ar")
NAVEGADOR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/126.0 Safari/537.36", "Accept-Language": "es-AR,es;q=0.9"}   # algunos sitios bloquean otros
MAX_CANDIDATOS = 4
# En pausa (Agustin, 15/11/2026): el modelo no llega a buscar en Google y escribe links de memoria. Mientras tanto,
# la búsqueda de la emisión original solo corre a pedido (emision <clave>) y no al leer cada reapertura.
BUSCAR_EMISION_AUTOMATICA = False
BUSQUEDAS_REALES: list[int] = []   # cuántos resultados de Google trajo cada pedido (0 = el modelo no buscó)
MESES_LARGOS = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
                "noviembre", "diciembre")
ORDEN = ["ticker", "tipo", "familia", "reapertura", "ley", "par", "emision", "vencimiento", "cupon", "margen", "frecuencia", "base",
         "tramos", "pagos", "tipo_cambio_pago", "fecha_tipo_cambio_inicial", "revisado", "fuente", "nota", "pendiente", "posible_duplicado", "emision_buscada", "cita", "clave"]
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
    familia_dual: Familia | None = Field(None, description="Solo si es dual: la familia de la otra pata (en 'familia' va "
                                         "la de una pata y acá la de la otra; paga la que más rinde)")
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
    fecha_tipo_cambio_inicial: str | None = Field(None, description="Solo duales TAMAR/dollar linked con VN en dólares: "
                                                  "fecha AAAA-MM-DD del A3500 del tipo de cambio inicial, si el texto la dice")
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
        respuesta = requests.get(fuente, timeout=60, headers=NAVEGADOR)
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
             "tipo_cambio_pago": ins.tipo_cambio_pago,
             "fecha_tipo_cambio_inicial": _fecha(ins.fecha_tipo_cambio_inicial), "revisado": False,
             "fuente": f"{tipo_documento}{' del ' + fecha_documento if fecha_documento else ''} ({origen}); borrador del lector de fichas",
             "nota": ins.notas, "pendiente": ins.pendiente or None, "cita": ins.cita or None}
    if ins.reapertura:
        ficha["reapertura"] = True
        emision, aviso = ficha.get("emision"), _fecha(fecha_documento) if fecha_documento else None
        # La fecha de esta licitación no es la emisión original: se descarta salvo que sea claramente anterior al aviso.
        if emision is None or aviso is None or emision >= aviso - timedelta(days=MARGEN_EMISION_ORIGINAL):
            ficha["emision"] = None
            ficha["pendiente"] = [p for p in (ficha["pendiente"] or []) if p.split(":")[0].strip() != "emision"] + [
                "emision: es una reapertura; falta la fecha de emisión original (leé la resolución o el prospecto de la "
                "primera emisión, o completala a mano)"]
    ficha = {k: v for k, v in ficha.items() if v not in (None, "", [])}
    ficha["clave"] = clave_de(ficha)
    return ficha


# Datos de condiciones que usa cada familia (en un dual, cada pata se queda con los suyos)
DATOS_DE_PATA = {"tasa_fija_capitalizable": {"cupon"}, "tasa_fija_cupon": {"cupon", "frecuencia", "base", "pagos"},
                 "tasa_fija_descuento": set(), "cer_cero_cupon": set(), "cer_cupon": {"cupon", "frecuencia", "pagos"},
                 "tamar_capitalizable": {"margen", "fecha_tipo_cambio_inicial"}, "dolar_linked_bullet": {"tipo_cambio_pago"},
                 "dolar_linked_cupon": {"cupon", "base", "pagos", "tipo_cambio_pago"},
                 "hard_dollar": {"cupon", "ley", "tramos", "pagos", "base"}}


def a_fichas(ins: Instrumento, origen: str, tipo_documento: str, fecha_documento: str | None) -> list[dict]:
    """Los borradores de un instrumento: uno, o uno por pata si es dual (mismo ticker, emisión y vencimiento; cada
    pata con sus propias condiciones, como las fichas de los duales cargados)."""
    ficha = a_ficha(ins, origen, tipo_documento, fecha_documento)
    if not ins.familia_dual or ins.familia_dual == ins.familia or not ins.familia:
        return [ficha]
    patas = []
    for familia, otra in ((ins.familia, ins.familia_dual), (ins.familia_dual, ins.familia)):
        pata = {k: v for k, v in ficha.items()
                if k not in set().union(*DATOS_DE_PATA.values()) or k in DATOS_DE_PATA[familia]}
        pata["familia"], pata["dual_con"] = familia, otra
        if "DUAL" not in str(pata.get("tipo") or "").upper():     # las curvas dejan afuera a los duales por el tipo
            pata["tipo"] = f"DUAL {SUFIJO_PATA[ins.familia]}/{SUFIJO_PATA[ins.familia_dual]}"
        if pata.get("pendiente"):                  # lo pendiente de la otra pata no es de esta
            ajenos = DATOS_DE_PATA[otra] - DATOS_DE_PATA[familia]
            pata["pendiente"] = [p for p in pata["pendiente"] if p.split(":")[0].strip() not in ajenos] or None
            if pata["pendiente"] is None:
                del pata["pendiente"]
        pata["clave"] = clave_de(pata)
        patas.append(pata)
    return patas


def clave_de(ficha: dict) -> str:
    """TICKER (o familia-vencimiento si todavía no tiene); en un dual, TICKER-PATA."""
    base = ficha.get("ticker") or f"{ficha.get('familia', 'sin_familia')}-{ficha.get('vencimiento', 'sin_vto')}"
    if ficha.get("dual_con") and ficha.get("ticker"):
        return f"{base}-{SUFIJO_PATA.get(ficha.get('familia'), ficha.get('familia'))}"
    return base


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
    return _cargar_toml(ruta).get("bono", [])


def _cargar_toml(ruta: Path) -> dict:
    """Lee un TOML; si está mal escrito (típicamente por una edición a mano), dice dónde y qué renglón."""
    texto = ruta.read_text(encoding="utf-8")
    try:
        return tomllib.loads(texto)
    except tomllib.TOMLDecodeError as e:
        linea = re.search(r"line (\d+)", str(e))
        renglon = texto.splitlines()[int(linea.group(1)) - 1] if linea else ""
        raise ValueError(
            f"{ruta.name} está mal escrito en la línea {linea.group(1) if linea else '?'}: «{renglon.strip()}». "
            "Corregilo a mano: fechas como 2025-10-29 (sin comillas), tasas en fracción con punto (0.06), textos entre "
            f"comillas, listas como [\"a\", \"b\"]. Detalle: {e}") from None


def _guardar_borradores(borradores: list[dict], ruta: Path | None = None):
    ruta = ruta or BORRADORES
    ruta.parent.mkdir(parents=True, exist_ok=True)
    encabezado = ("# Borradores de fichas del lector de documentos (fuentes_datos/carga/fichas_documentos.py).\n"
                  "# No los usa ninguna calculadora. Revisalos, completá lo pendiente y aprobalos con:\n"
                  "#     python -m fuentes_datos.carga.fichas_documentos aprobar <TICKER>\n\n")
    ruta.write_text(encabezado + "\n".join(a_toml(b) for b in borradores), encoding="utf-8")


def _ruta_cambios() -> Path:
    return CAMBIOS or BORRADORES.parent / "cambios.toml"


def _leer_cambios() -> list[dict]:
    ruta = _ruta_cambios()
    return _cargar_toml(ruta).get("cambio", []) if ruta.exists() else []


def _guardar_cambios(cambios: list[dict]):
    ruta = _ruta_cambios()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    encabezado = ("# Cambios propuestos a fichas ya aprobadas (datos de un documento que no coinciden con la ficha).\n"
                  "# La ficha no cambia hasta que los aplicás:  python -m fuentes_datos.carga.fichas_documentos aplicar <TICKER>\n\n")
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


def _ya_cargado(ficha: dict, existentes: dict[str, list[dict]]) -> tuple[str, list[dict]] | None:
    """Si el instrumento ya está en la base: (cómo informarlo, las fichas con las que comparar datos). None si no."""
    ticker = (ficha.get("ticker") or "").upper()
    if ticker and ticker in existentes:
        misma = [f for f in existentes[ticker] if f["familia"] == ficha.get("familia")]
        if misma:
            return ticker, misma
        if not ficha.get("dual_con"):           # el ticker existe con otra familia: es ese bono (revisar la familia)
            familias = ", ".join(f["familia"] for f in existentes[ticker])
            return f"{ticker} (cargado como {familias})", []
        return None                              # la pata de un dual que falta: va al borrador
    if not ticker:
        duplicados = posibles_duplicados(ficha, existentes)
        if duplicados:
            return (f"{ficha.get('clave')} = {duplicados[0]} (mismas condiciones: familia, vencimiento"
                    f"{', cupón' if 'cupon' in ficha else ''}{', margen' if 'margen' in ficha else ''})",
                    [f for f in existentes[duplicados[0]] if f["familia"] == ficha.get("familia")])
    return None


def posibles_duplicados(ficha: dict, existentes: dict[str, list[dict]]) -> list[str]:
    """Bonos ya cargados con la misma familia y vencimiento (y, si ambos lo tienen, el mismo cupón y margen)."""
    salida = []
    for ticker, lista in existentes.items():
        if ficha.get("ticker") and ficha["ticker"].upper() == ticker.upper():
            continue
        for f in lista:
            if f["familia"] != ficha.get("familia") or f["vencimiento"] != ficha.get("vencimiento"):
                continue
            if any(c in ficha and c in f and not _iguales(ficha[c], f[c]) for c in ("cupon", "margen")):
                continue
            salida.append(ticker)
    return sorted(set(salida))


def candidatos_ticker(familia: str | None, vencimiento: date | None) -> list[str]:
    """Tickers posibles según la convención de nombres del Tesoro (día, letra del mes y año del vencimiento)."""
    if not familia or not isinstance(vencimiento, date):
        return []
    d, l, y, yy = f"{vencimiento.day:02d}", LETRAS_MES[vencimiento.month - 1], vencimiento.year % 10, f"{vencimiento.year % 100:02d}"
    junio = vencimiento.month == 6
    por_familia = {
        "tasa_fija_capitalizable": [f"S{d}{l}{y}", f"T{d}{l}{y}"],
        "tasa_fija_descuento": [f"S{d}{l}{y}"],
        "tasa_fija_cupon": [f"T{d}{l}{y}"],
        "cer_cero_cupon": [f"X{d}{l}{y}", f"TZX{l}{y}"] + ([f"TZX{yy}"] if junio else []),
        "cer_cupon": [f"TX{yy}"],
        "dolar_linked_bullet": [f"D{d}{l}{y}", f"TZV{l}{y}"] + ([f"TZV{yy}"] if junio else []),
        "dolar_linked_cupon": [f"D{d}{l}{y}"],
        "tamar_capitalizable": [f"M{d}{l}{y}", f"TM{l}{yy}"],
    }
    return por_familia.get(familia, [])


def _buscar(ticker: str) -> list[dict]:
    if BUSCADOR is not None:
        return BUSCADOR(ticker)
    from fuentes_datos.conexiones import ppi
    return ppi.buscar_instrumento(ticker)


def actualizar_borradores(hoy: date | None = None) -> list[str]:
    """Para cada borrador: busca el ticker si no lo tiene y marca si parece un bono ya cargado. Devuelve lo que hizo."""
    borradores = _leer_borradores()
    if not borradores:
        return []
    existentes = leer_fichas.leer_todas()
    usados = set(existentes)
    avisos, sin_conexion, descartar = [], None, []
    for b in borradores:
        if not b.get("ticker") and sin_conexion is None:
            encontrados = []
            for candidato in candidatos_ticker(b.get("familia"), b.get("vencimiento")):
                if candidato in usados:
                    continue      # ya tiene ficha: si es este mismo bono, lo marca el chequeo de duplicados de abajo
                try:
                    hallados = [i for i in _buscar(candidato) if str(i.get("ticker", "")).upper() == candidato]
                except Exception as e:           # sin credenciales o sin conexión: se reintenta la próxima vez
                    sin_conexion = str(e)
                    break
                if hallados:
                    encontrados.append((candidato, hallados[0].get("description") or ""))
            if len(encontrados) == 1:
                ticker, descripcion = encontrados[0]
                b["ticker"] = ticker
                b["clave"] = clave_de(b)
                nota = (f"ticker {ticker} encontrado en PPI por la convención de nombres"
                        + (f" ({descripcion})" if descripcion else "") + ": verificalo antes de aprobar")
                b["nota"] = f"{b['nota']}. {nota}" if b.get("nota") else nota
                if b.get("pendiente"):
                    b["pendiente"] = [p for p in b["pendiente"] if p.split(":")[0].strip() != "ticker"]
                avisos.append(f"{ticker}: ticker encontrado en PPI{' (' + descripcion + ')' if descripcion else ''}")
            elif len(encontrados) > 1:
                opciones = ", ".join(t for t, _ in encontrados)
                b["pendiente"] = [p for p in b.get("pendiente", []) if p.split(":")[0].strip() != "ticker"] + [
                    f"ticker: más de un candidato en PPI ({opciones}); elegí con completar"]
                avisos.append(f"{b['clave']}: varios tickers posibles ({opciones})")
        if not b.get("pendiente"):
            b.pop("pendiente", None)
        if b.get("confirmado_nuevo"):            # un humano dijo que es otro bono: no se descarta
            b.pop("posible_duplicado", None)
            continue
        ya = _ya_cargado(b, existentes)
        if ya:
            descartar.append(b)
            avisos.append(f"{b['clave']}: descartado, ya está en la base ({ya[0]})")
            continue
        duplicados = posibles_duplicados(b, existentes)
        if duplicados:                            # con ticker propio pero mismas condiciones que otro: decide un humano
            if b.get("posible_duplicado") != duplicados:
                avisos.append(f"{b['clave']}: parece el mismo bono que {', '.join(duplicados)} (misma familia, vencimiento y "
                              "condiciones). Si lo es: vincular; si es otro: aprobar --nuevo")
            b["posible_duplicado"] = duplicados
        else:
            b.pop("posible_duplicado", None)
    borradores = [b for b in borradores if b not in descartar]
    _guardar_borradores(borradores)
    if sin_conexion:
        avisos.append(f"No se pudo buscar tickers en PPI ({sin_conexion}); se reintenta en la próxima lectura.")
    return avisos


def vincular(clave: str, ticker: str) -> str:
    """El borrador es un bono que ya tiene ficha: se descarta y, si algún dato difiere, queda como cambio propuesto."""
    borradores = _leer_borradores()
    elegido = _elegir_borrador(borradores, clave)
    cargadas = [f for f in leer_fichas.fichas_de(ticker.upper()) if f["familia"] == elegido.get("familia")]
    if not cargadas:
        raise ValueError(f"{ticker.upper()} no tiene ficha en la familia {elegido.get('familia')}.")
    cambios = _leer_cambios()
    propuestos = _proponer_cambios(elegido, cargadas[0], cambios)
    if propuestos:
        _guardar_cambios(cambios)
    _guardar_borradores([b for b in borradores if b is not elegido])
    return (f"Borrador {elegido['clave']} vinculado a {ticker.upper()} y descartado."
            + (f" Datos distintos, quedan como cambios propuestos: {'; '.join(propuestos)}." if propuestos else
               " Las condiciones coinciden con la ficha."))


def _elegir_borrador(borradores: list[dict], clave: str) -> dict:
    elegido = next((b for b in borradores if b.get("clave", "").upper() == clave.upper()
                    or (b.get("ticker") or "").upper() == clave.upper()), None)
    if elegido is None:
        raise ValueError(f"No hay ningún borrador '{clave}'. Pendientes: "
                         f"{', '.join(b.get('clave', '?') for b in borradores) or 'ninguno'}.")
    return elegido


def _vencido(ficha: dict, hoy: date) -> bool:
    vto = ficha.get("vencimiento")
    return isinstance(vto, date) and vto < hoy


def leer(fuente: str, extractor=extraer_con_modelo, hoy: date | None = None, solo: str | None = None,
         buscar_emision: bool | None = None, texto: str | None = None) -> dict:
    """Lee un documento y actualiza los borradores. Devuelve el resumen de lo que hizo.

    Los instrumentos ya vencidos (vencimiento anterior a hoy) no se cargan: se informan y listo. Los borradores que
    vencieron mientras esperaban aprobación también se sacan.

    solo: clave o ticker de un borrador; del documento se toman únicamente los datos de ese bono (para completar la
    emisión original desde un aviso viejo sin cargar el resto de sus instrumentos)."""
    hoy = hoy or date.today()
    texto = texto or obtener_texto(fuente)
    documento = extractor(texto)
    existentes = leer_fichas.leer_todas()
    borradores = _leer_borradores()
    cambios = _leer_cambios()
    resumen = {"documento": documento.tipo_documento, "fecha": documento.fecha_documento, "ya_cargados": [],
               "vencidos": [], "nuevos": [], "completados": [], "sin_familia": [], "descartados": [],
               "cortes": [], "cambios": [], "reaperturas": [], "avisos": []}
    for b in [b for b in borradores if _vencido(b, hoy)]:
        borradores.remove(b)
        resumen["vencidos"].append(f"{b['clave']} (borrador, venció el {b['vencimiento']:%d/%m/%Y})")
    origen = fuente if re.match(r"https?://", fuente) else Path(fuente).name
    objetivo = _elegir_borrador(borradores, solo) if solo else None
    for ins, ficha in [(ins, f) for ins in documento.instrumentos
                       for f in a_fichas(ins, origen, documento.tipo_documento, documento.fecha_documento)]:
        corte = _texto_corte(ins)
        ticker = ficha.get("ticker")
        if objetivo is not None and not _mismo(objetivo, ficha) and not _mismo({**objetivo, "ticker": None}, ficha):
            continue
        if corte:
            resumen["cortes"].append(corte)
        if _vencido(ficha, hoy):
            resumen["vencidos"].append(f"{ticker or ins.nombre} (venció el {ficha['vencimiento']:%d/%m/%Y})")
            continue
        # Reglas de Agustin (26/11/2026): (1) si el ticker ya está en la base, no va al borrador (los datos distintos
        # quedan como cambios propuestos); la excepción es la pata de un dual que todavía no está cargada. (2) Sin
        # ticker (un aviso viejo o un llamado de un bono nuevo), si las condiciones coinciden con un bono cargado, se
        # descarta también: es ese bono.
        ya = _ya_cargado(ficha, existentes)
        if ya:
            resumen["ya_cargados"].append(ya[0])
            for cargada in ya[1]:
                resumen["cambios"] += _proponer_cambios(ficha, cargada, cambios)
            sobrantes = [b for b in borradores if _mismo(b, {**ficha, "ticker": None})
                         or (ticker and (b.get("ticker") or "").upper() == ticker and b.get("familia") == ficha.get("familia"))]
            for b in sobrantes:
                borradores.remove(b)
                resumen["descartados"].append(b["clave"])
            continue
        if not ficha.get("familia"):
            resumen["sin_familia"].append(ins.nombre)
        if ficha.get("reapertura"):
            resumen["reaperturas"].append(ficha["clave"])
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
            previo["clave"] = clave_de(previo)
        resumen["completados"].append((previo["clave"], agregados))
    _guardar_borradores(borradores)
    if cambios or _ruta_cambios().exists():
        _guardar_cambios(cambios)
    resumen["avisos"] = actualizar_borradores(hoy)
    if (BUSCAR_EMISION_AUTOMATICA if buscar_emision is None else buscar_emision) and solo is None:
        for clave in resumen["reaperturas"]:
            resumen["avisos"].append(buscar_emision_original(clave, extractor=extractor, hoy=hoy))
    return resumen


def _fecha_larga(d: date) -> str:
    return f"{d.day} de {MESES_LARGOS[d.month - 1]} de {d.year}"


def _resolver_redireccion(url: str) -> str | None:
    """Los resultados de la búsqueda de Google llegan como links de redirección: se lee a dónde apuntan."""
    import requests
    try:
        r = requests.get(url, allow_redirects=False, timeout=20)
        if r.headers.get("Location"):
            return r.headers["Location"]
        return requests.get(url, timeout=20, stream=True).url
    except Exception:
        return None


def _buscar_en_web(consulta: str, detalle: list | None = None) -> list[str]:
    """URLs oficiales candidatas para una consulta: el modelo busca en Google y se juntan los resultados."""
    if BUSCADOR_WEB is not None:
        return BUSCADOR_WEB(consulta)
    from graph.nodes import crear_modelos, invocar_con_respaldo
    from langchain_core.messages import HumanMessage
    modelos = crear_modelos(preparar=lambda llm: llm.bind_tools([{"google_search": {}}]))
    respuesta = invocar_con_respaldo(modelos, [HumanMessage(consulta)])
    metadatos = (respuesta.response_metadata or {}).get("grounding_metadata") or {}
    trozos = [c.get("web") or {} for c in metadatos.get("grounding_chunks") or []]
    escritos = re.findall(r"https?://[^\s)\]>\"'<]+", respuesta.text or "")
    BUSQUEDAS_REALES.append(len(trozos))
    if detalle is not None:
        detalle.append(f"Consulta: {consulta}")
        detalle.append(f"  Búsquedas que hizo el modelo: {metadatos.get('web_search_queries')}")
        detalle += [f"  Resultado de Google: {w.get('title')} → {w.get('uri')}" for w in trozos]
        detalle += [f"  Link escrito por el modelo: {u}" for u in escritos]
    # Primero los resultados reales de la búsqueda; después los links que escribió el modelo (pueden ser inventados)
    salida = []
    for url in [w.get("uri") for w in trozos if w.get("uri")] + escritos:
        if "grounding-api-redirect" in url or "vertexaisearch" in url:
            url = _resolver_redireccion(url)
            if detalle is not None:
                detalle.append(f"  Redirección → {url}")
            if not url:
                continue
        url = url.rstrip(".,;")
        dominio = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        if any(dominio.endswith(d) for d in DOMINIOS_OFICIALES) and url not in salida:
            salida.append(url)
    return salida


def _sin_acentos(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def menciona_vencimiento(texto: str, vencimiento: date) -> bool:
    """Chequeo barato antes de gastar el modelo: el documento nombra la fecha de vencimiento del bono."""
    plano = re.sub(r"\s+", " ", _sin_acentos(texto))
    d, m, a = vencimiento.day, vencimiento.month, vencimiento.year
    formas = [f"{d} de {MESES_LARGOS[m - 1]} de {a}", f"{d:02d} de {MESES_LARGOS[m - 1]} de {a}",
              f"{d:02d}/{m:02d}/{a}", f"{d}/{m}/{a}", f"{d:02d}/{m:02d}/{a % 100:02d}", f"{d:02d}-{m:02d}-{a}",
              f"{a}-{m:02d}-{d:02d}", f"{d:02d}.{m:02d}.{a}"]
    return any(f in plano for f in formas)


def _consultas_emision(b: dict) -> list[str]:
    """Pedidos al modelo con las búsquedas de Google ya armadas (operadores site: y frases exactas): así no busca
    "a ojo" ni trae notas de medios. Sin filetype:pdf, porque los llamados y el Boletín Oficial son páginas HTML."""
    descripcion = (b.get("cita") or f"{b.get('tipo', '')} {b.get('ticker', '')}").split("(")[0].strip()
    ticker = b.get("ticker")
    vto = b.get("vencimiento") if isinstance(b.get("vencimiento"), date) else None
    frase_vto = f'"vencimiento {_fecha_larga(vto)}"' if vto else ""
    fechas = sorted(re.findall(r"\d{4}-\d{2}-\d{2}", b.get("fuente", "")))
    antes = (f" El documento correcto es anterior al {_fecha_larga(date.fromisoformat(fechas[0]))} (en esa fecha el bono "
             "ya era una reapertura)." if fechas else "")
    pedido = ("Hacé exactamente estas búsquedas en Google, en este orden, y devolvé solo las direcciones (URL) completas "
              "de los resultados de argentina.gob.ar o boletinoficial.gob.ar que correspondan, una por renglón, la más "
              f"probable primero. Busco el documento de la PRIMERA emisión (instrumento nuevo, no reapertura) de: "
              f"{descripcion}{' (' + ticker + ')' if ticker else ''}.{antes}\n")
    return [
        pedido + f'1. site:argentina.gob.ar/noticias "llamado a licitación" {frase_vto} "(nuevo)"\n'
                 f'2. site:argentina.gob.ar "llamado a licitación" {frase_vto}' + (f" {ticker}" if ticker else ""),
        pedido + f'1. site:boletinoficial.gob.ar "resolución conjunta" "dispónese la emisión" {frase_vto}\n'
                 f'2. site:argentina.gob.ar/normativa "resolución conjunta" {frase_vto} "fecha de emisión"',
    ]


def resolucion_original(texto: str, vencimiento: date) -> tuple[str, str] | None:
    """Si el documento amplía el bono, las resoluciones dicen "emitido originalmente mediante el artículo N de la
    resolución conjunta X del <fecha>": devuelve (X, fecha) para buscar esa resolución."""
    plano = re.sub(r"\s+", " ", _sin_acentos(texto))
    vto = f"vencimiento {vencimiento.day} de {MESES_LARGOS[vencimiento.month - 1]} de {vencimiento.year}"
    patron = (re.escape(vto) + r"\W{0,4}(?:\([^)]{0,30}\)\W{0,3})?,? emitid[oa] originalmente mediante el articulo \d+\W{0,2} "
              r"de la resolucion conjunta (\d+) del (\d{1,2} de [a-z]+ de \d{4})")
    m = re.search(patron, plano)
    return (m.group(1), m.group(2)) if m else None


def buscar_emision_original(clave: str, extractor=extraer_con_modelo, hoy: date | None = None,
                            detalle: list | None = None) -> str:
    """Busca el documento de la primera emisión de un borrador sin emisión y completa de ahí solo ese bono.

    Hasta dos búsquedas, más una tercera si algún documento cita la resolución que emitió originalmente el bono. De
    cada link se baja el texto y, si no nombra el vencimiento del bono, se descarta sin llamar al modelo. Solo sirve
    un documento que traiga el bono como nuevo y con su fecha de emisión. detalle: lista donde se anota todo (diagnóstico)."""
    hoy = hoy or date.today()
    borradores = _leer_borradores()
    b = _elegir_borrador(borradores, clave)
    if b.get("emision"):
        return f"{b['clave']}: ya tiene fecha de emisión ({b['emision']})."
    vencimiento = b.get("vencimiento") if isinstance(b.get("vencimiento"), date) else None
    consultas = _consultas_emision(b)
    BUSQUEDAS_REALES.clear()
    intentos, probados, error, citada = [], set(), None, None
    while consultas:
        consulta = consultas.pop(0)
        try:
            encontrados = _buscar_en_web(consulta, detalle) if BUSCADOR_WEB is None else _buscar_en_web(consulta)
        except Exception as e:
            error = str(e).splitlines()[0][:200]
            continue
        for url in [u for u in encontrados if u not in probados][:MAX_CANDIDATOS]:
            probados.add(url)
            try:
                texto = obtener_texto(url)
            except Exception as e:
                intentos.append(f"{url} (no se pudo leer: {str(e).splitlines()[0][:80]})")
                continue
            if vencimiento and not menciona_vencimiento(texto, vencimiento):
                intentos.append(f"{url} (no menciona el vencimiento del bono)")
                continue
            if vencimiento and citada is None:
                citada = resolucion_original(texto, vencimiento)
                if citada:
                    numero, fecha = citada
                    consultas.insert(0, (
                        "Hacé exactamente estas búsquedas en Google y devolvé solo las direcciones (URL) completas de los "
                        "resultados oficiales, una por renglón. Busco el texto de la Resolución Conjunta "
                        f"{numero} del {fecha} de la Secretaría de Finanzas y la Secretaría de Hacienda "
                        f"(RESFC-{fecha[-4:]}-{numero}-APN-SH#MEC).\n"
                        f'1. site:boletinoficial.gob.ar "Resolución Conjunta {numero}/{fecha[-4:]}" "Secretaría de Finanzas"\n'
                        f'2. site:argentina.gob.ar/normativa "Resolución Conjunta {numero}/{fecha[-4:]}"'))
                    if detalle is not None:
                        detalle.append(f"  {url} cita la emisión original: resolución conjunta {numero} del {fecha}")
            try:
                leer(url, extractor=extractor, hoy=hoy, solo=b["clave"], buscar_emision=False, texto=texto)
            except Exception as e:
                intentos.append(f"{url} (no se pudo leer: {str(e).splitlines()[0][:80]})")
                continue
            actual = next((x for x in _leer_borradores() if _mismo(x, b) or x.get("clave") == b["clave"]), None)
            if actual and actual.get("emision"):
                return (f"{actual['clave']}: encontré la primera emisión en {url} y completé el borrador "
                        f"(emisión {actual['emision']}). Revisalo antes de aprobar.")
            intentos.append(f"{url} (lo nombra, pero no como emisión nueva)")
    borradores = _leer_borradores()
    b = _elegir_borrador(borradores, clave)
    b["emision_buscada"] = hoy
    _guardar_borradores(borradores)
    motivo = ("probé " + "; ".join(intentos) if intentos else
              f"la búsqueda falló ({error})" if error else "la búsqueda no devolvió documentos oficiales")
    if BUSQUEDAS_REALES and not any(BUSQUEDAS_REALES):
        motivo += (". Ojo: Google no devolvió ningún resultado, el modelo no llegó a buscar y los links los escribió "
                   "de memoria (por eso dan 404)")
    elif BUSQUEDAS_REALES:
        motivo += f". Google devolvió {sum(BUSQUEDAS_REALES)} resultados en {len(BUSQUEDAS_REALES)} pedidos"
    return (f"{b['clave']}: no encontré la primera emisión ({motivo}). Si tenés el link: "
            f"python -m fuentes_datos.carga.fichas_documentos leer <URL> --solo {b['clave']}")


def pendientes() -> list[dict]:
    return _leer_borradores()


def aprobar(clave: str, carpeta: Path | None = None, por: str = "Agustin", hoy: date | None = None,
            nuevo: bool = False) -> str:
    """Valida el borrador y lo pasa al archivo de su familia con revisado = true.

    nuevo=True confirma que no es ninguno de los bonos ya cargados con las mismas condiciones."""
    hoy = hoy or date.today()
    borradores = _leer_borradores()
    elegido = _elegir_borrador(borradores, clave)
    ficha = {k: v for k, v in elegido.items() if k not in SOLO_BORRADOR}
    if not ficha.get("ticker"):
        raise leer_fichas.ErrorFicha("Al borrador le falta el ticker: completalo en el archivo de borradores.")
    if _vencido(ficha, hoy):
        raise leer_fichas.ErrorFicha(f"{ficha['ticker']} ya venció ({ficha['vencimiento']:%d/%m/%Y}): no hace falta cargarlo. Descartalo.")
    if elegido.get("reapertura") and not ficha.get("emision"):
        raise leer_fichas.ErrorFicha(f"{ficha['ticker']} es una reapertura y falta su fecha de emisión original: leé la "
                                     "resolución o el prospecto de la primera emisión, o completala (completar ... emision=AAAA-MM-DD).")
    leer_fichas.validar(ficha, f"borrador {clave}")
    if any(f["familia"] == ficha["familia"] for f in leer_fichas.fichas_de(ficha["ticker"])):
        raise leer_fichas.ErrorFicha(f"{ficha['ticker']} ya tiene ficha en la familia {ficha['familia']}.")
    duplicados = posibles_duplicados(ficha, leer_fichas.leer_todas())
    if duplicados and not nuevo:
        raise leer_fichas.ErrorFicha(
            f"{ficha['ticker']} parece el mismo bono que {', '.join(duplicados)} (misma familia, vencimiento y condiciones). "
            f"Si es el mismo: vincular {elegido['clave']} {duplicados[0]}. Si es otro bono: aprobar {elegido['clave']} --nuevo.")
    ficha["revisado"] = True
    confirmacion = f"; confirmado como bono distinto de {', '.join(duplicados)}" if duplicados else ""
    ficha["fuente"] = f"{ficha.get('fuente', '')}{confirmacion}; aprobado por {por} el {hoy:%d/%m/%Y}"
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
        elegido["clave"] = clave_de(elegido)
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
    if resumen.get("reaperturas"):
        lineas.append("Reaperturas de bonos que no teníamos: quedan como borrador sin la emisión original (pendiente): "
                      + ", ".join(resumen["reaperturas"]))
    for aviso in resumen.get("avisos", []):
        lineas.append(aviso)
    if resumen["sin_familia"]:
        lineas.append("Sin familia reconocida (revisar a mano): " + ", ".join(resumen["sin_familia"]))
    for b in pendientes():
        if b.get("pendiente"):
            lineas.append(f"  {b['clave']}: pendiente → " + "; ".join(b["pendiente"]))
    if resumen.get("cambios"):
        lineas.append("Aplicalos con: python -m fuentes_datos.carga.fichas_documentos aplicar <TICKER> (o rechazar <TICKER>)")
    if pendientes():
        lineas.append(f"Revisá {BORRADORES.relative_to(leer_fichas.CARPETA.parent.parent)} y aprobá con: "
                      "python -m fuentes_datos.carga.fichas_documentos aprobar <TICKER> (o pedíselo al agente de renta fija)")
    return "\n".join(lineas)


def main(argv: list[str]):
    if len(argv) < 1 or argv[0] not in ("leer", "pendientes", "aprobar", "descartar", "completar", "cambios",
                                        "aplicar", "rechazar", "vincular", "tickers", "emision"):
        print(__doc__)
        return
    try:
        if argv[0] == "leer":
            solo = argv[argv.index("--solo") + 1] if "--solo" in argv else None
            print(describir(leer(argv[1], solo=solo)))
        elif argv[0] == "emision":
            detalle = [] if "--detalle" in argv else None
            salida = buscar_emision_original(argv[1], detalle=detalle)
            if detalle is not None:
                print("\n".join(detalle) + "\n")
            print(salida)
        elif argv[0] == "tickers":
            print("\n".join(actualizar_borradores()) or "Nada nuevo: no aparecieron tickers ni posibles duplicados.")
        elif argv[0] == "vincular":
            print(vincular(argv[1], argv[2]))
        elif argv[0] == "pendientes":
            for aviso in actualizar_borradores():
                print(aviso)
            lista = pendientes()
            print("\n".join(f"{b['clave']}: {b.get('tipo', '?')} {b.get('familia', '?')} vence {b.get('vencimiento', '?')}"
                            + (" | REAPERTURA" if b.get("reapertura") else "")
                            + (f" | ¿es {', '.join(b['posible_duplicado'])}?" if b.get("posible_duplicado") else "")
                            + (f" | pendiente: {'; '.join(b['pendiente'])}" if b.get("pendiente") else "")
                            for b in lista) or "No hay borradores pendientes.")
        elif argv[0] == "aprobar":
            print(aprobar(argv[1], nuevo="--nuevo" in argv[2:]))
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
