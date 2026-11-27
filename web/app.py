"""Panel web de Finianz: renta fija (prueba).

Correr desde la carpeta del proyecto, con el entorno virtual activo:
    streamlit run web/app.py
y abrir http://localhost:8501 en el navegador.

El panel no calcula nada propio: usa las mismas funciones que el agente de renta fija (tools/ y renta_fija/), con los
mismos precios de PPI y las mismas bases de datos/. Si algo da distinto que en la terminal, es un error del panel.
"""
import hmac
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para importar el proyecto al correr con streamlit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import config
from renta_fija import leer_fichas
from renta_fija.calculadoras import curva as calc_curva
from renta_fija.calculadoras import exit_yield as calc_exit
from renta_fija.calculadoras import forwards as calc_forwards
from renta_fija import curvas_mercado, metricas
from fuentes_datos import mercado
from tools import bonos, breakevens, curvas, proyeccion_cer, proyecciones
from web import carteras_panel, salidas

IMAGENES = Path(__file__).resolve().parent / "imagenes"
# Por ahora el producto se muestra sin nombre (Agustin, 20/11/2026): sin "Finianz" en la pestaña, el logo ni el acceso.
# Para volver a mostrarlo: MOSTRAR_NOMBRE = True.
MOSTRAR_NOMBRE = False
NOMBRE = "Finianz" if MOSTRAR_NOMBRE else ""
st.set_page_config(page_title=f"{NOMBRE} · Renta fija" if NOMBRE else "Renta fija", page_icon=str(IMAGENES / "icono.svg"), layout="wide")
NOMBRES_CURVA = {"tasa_fija": "Tasa fija (TEA)", "cer": "CER (TEA real)", "tamar": "TAMAR (spread sobre TAMAR)",
                 "dl": "Dollar linked (TEA en USD)", "hd": "Hard dollar (TEA en USD)"}
TITULOS = set(breakevens.NOMBRES.values())
AYUDA_TNA = {"tasa_fija": "TNA simple al vencimiento (las Boncap con cupón: semestral)",
             "cer": "TNA real: simple al vencimiento en los cero cupón, semestral en los que pagan cupón",
             "tamar": "TNA simple al vencimiento", "dl": "TNA en dólares, simple al vencimiento",
             "hd": "TNA semestral (la TIR que informa el mercado)"}
# Dos modos (detalle en .streamlit/config.toml). El tema lo aplica Streamlit en el navegador; acá se elige la misma
# paleta para lo que el tema no cubre: gráficos, encabezados, etiquetas y logo.
PALETAS = {
    "light": dict(fondo="#FFFFFF", tarjeta="#F4F6F8", borde="#E2E8F0", esmeralda="#11523B", esmeralda_hover="#16654A",
                  oro="#9E762A", texto="#0F141A", secundario="#525D6E", serie_extra="#2F6FAB", logo="logo_oscuro.svg"),
    "dark": dict(fondo="#090C10", tarjeta="#12171E", borde="#1F2733", esmeralda="#16654A", esmeralda_hover="#1E8260",
                 oro="#C59B4B", texto="#F4F5F7", secundario="#8E98A8", serie_extra="#4F8FD0", logo="logo_claro.svg"),
}
MODO = "dark" if st.context.theme.type == "dark" else "light"
P = PALETAS[MODO]
SUPERFICIE, GRILLA = P["tarjeta"], P["borde"]
ESMERALDA, ORO, TEXTO, GRIS = P["esmeralda"], P["oro"], P["texto"], P["secundario"]
SERIES = [ESMERALDA, ORO, GRIS, P["serie_extra"]]      # para varias líneas en un mismo gráfico

# El logo queda fijo arriba a la izquierda (con la barra lateral cerrada, se ve el ícono)
st.logo(str(IMAGENES / (P["logo"] if MOSTRAR_NOMBRE else "icono.svg")), size="large",
        icon_image=str(IMAGENES / "icono.svg"))

# Lo que el tema de Streamlit no cubre: etiquetas y textos secundarios, desplegables y contenedores como tarjetas (sin
# sombras ni bordes pesados), botones con el esmeralda y su tono al pasar el mouse, encabezado y números tabulares.
st.markdown(f"""
<style>
  [data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"], [data-testid="stMetricLabel"] p,
  .stCaption, small {{ color: {GRIS} !important; }}
  [data-testid="stExpander"] details {{ background: {SUPERFICIE}; border: 1px solid {GRILLA}; border-radius: 10px; }}
  [data-testid="stVerticalBlockBorderWrapper"]:has(> div > [data-testid="stVerticalBlock"]) {{
      background: {SUPERFICIE}; border: 1px solid {GRILLA} !important; box-shadow: none; }}
  [data-testid="stMetric"] {{ background: {SUPERFICIE}; border: 1px solid {GRILLA}; border-radius: 10px; padding: 12px 16px; }}
  [data-testid="stMetricValue"], [data-testid="stDataFrame"] {{ font-variant-numeric: tabular-nums; }}
  [data-testid="stMetricValue"] {{ color: {TEXTO}; }}
  .stButton button {{ background: {ESMERALDA}; color: #FFFFFF; border: none; }}
  .stButton button:hover {{ background: {P["esmeralda_hover"]}; color: #FFFFFF; border: none; }}
  .encabezado {{ background: {SUPERFICIE}; color: {TEXTO}; border: 1px solid {GRILLA}; border-left: 4px solid {ESMERALDA};
                 border-radius: 8px; padding: 14px 20px; margin-bottom: 18px; }}
  .encabezado .titulo {{ font-size: 1.9rem; font-weight: 700; line-height: 1.2; margin-bottom: 4px; color: {TEXTO}; }}
  .encabezado span {{ color: {GRIS}; font-size: 0.85rem; }}
  .rotulo-lateral {{ color: {GRIS}; font-size: 0.75rem; letter-spacing: 0.1em; font-weight: 600; }}
</style>
""", unsafe_allow_html=True)


def cambiar_modo(oscuro: bool):
    """Streamlit guarda el tema elegido en el navegador (el mismo ajuste que su menú ⋮ → Light/Dark): se escribe ahí
    y se recarga la página. La primera vez (sin elección guardada, "System") queda el modo Blanco."""
    deseado = "Dark" if oscuro else "Light"
    _script(f"""<script>
      const clave = "stActiveTheme-/-v2";
      const actual = JSON.parse(window.parent.localStorage.getItem(clave) || '"System"');
      const deseado = actual === "System" ? "Light" : "{deseado}";
      if (actual !== deseado) {{
        window.parent.localStorage.setItem(clave, JSON.stringify(deseado));
        window.parent.location.reload();
      }}
    </script>""")


def _script(codigo: str):
    """Corre un script en la página del panel (iframe del mismo origen, invisible)."""
    if hasattr(st, "iframe"):          # Streamlit nuevo: st.iframe reemplaza a components.html
        st.iframe(codigo, height=1)
    else:
        components.html(codigo, height=0)


DESCRIPCIONES = {"Curvas": "TEA contra duration por familia, con tabla editable de precio y tasa",
                 "Bono": "Calculadora de un bono: precio ↔ tasa, métricas y flujo de fondos",
                 "Breakevens": "Inflación, devaluación, tipo de cambio real, brecha y TAMAR implícitos, contra el REM",
                 "Proyecciones": "El camino supuesto contra el breakeven y el REM, y su efecto en cada bono",
                 "Fichas": "Fichas técnicas aprobadas y borradores del lector de documentos",
                 "Carteras": "Carteras de clientes: valuación, edición y consultas a la IA"}


def estilo_grafico(fig: go.Figure, alto: int, **ejes):
    """Fondo transparente, grilla en el color de los bordes y textos en los colores del modo (Blanco u Oscuro)."""
    fig.update_layout(height=alto, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color=TEXTO), legend=dict(orientation="h", font=dict(color=GRIS)),
                      margin=dict(l=70, r=20, t=40, b=10), **ejes)
    fig.update_xaxes(gridcolor=GRILLA, zerolinecolor=GRILLA, tickfont=dict(color=GRIS), title_font=dict(color=GRIS))
    fig.update_yaxes(gridcolor=GRILLA, zerolinecolor=GRILLA, tickfont=dict(color=GRIS), title_font=dict(color=GRIS),
                     automargin=True)
    return fig


# ---------- Datos (con caché: se recalcula al cambiar la fecha o al vencer el intervalo de actualización) ----------

def _contexto(fecha: date | None):
    return mercado.contexto(fecha)


@st.cache_data(ttl=60, show_spinner="Trayendo precios y calculando las curvas…")
def datos_curvas(fecha: date | None, _marca: int, dolar: str = "mep"):
    """Todas las curvas del panel: con duales y Globales, y los hard dollar en dólares MEP o cable."""
    operacion, liquidacion, fecha_precios = _contexto(fecha)
    puntos, contexto, errores = curvas_mercado.armar(operacion, liquidacion, fecha_precios, todas=True, dolar=dolar)
    return puntos, contexto, errores, liquidacion


@st.cache_data(ttl=3600, show_spinner=False)
def datos_anteriores(operacion: date, dolar: str = "mep") -> tuple[dict, date]:
    """Los bonos al cierre del día hábil anterior, para las variaciones: {(curva, ticker, familia): punto}."""
    anterior, liquidacion, fecha_precios = mercado.contexto_anterior(operacion)
    puntos, _, _ = curvas_mercado.armar(anterior, liquidacion, fecha_precios, todas=True, dolar=dolar)
    return {(c, p["ticker"], p["familia"]): p for c, lista in puntos.items() for p in lista}, anterior


@st.cache_data(ttl=60, show_spinner="Calculando…")
def salida_herramienta(nombre: str, _marca: int, **argumentos) -> str:
    funciones = {"breakevens": breakevens.calcular_breakevens, "curva_tf": curvas.curva_tasa_fija,
                 "bono": bonos.calcular_bono, "cer": proyeccion_cer.proyectar_cer,
                 "tamar": proyecciones.proyectar_tamar, "dolar": proyecciones.proyectar_dolar}
    return funciones[nombre](**argumentos)


def mostrar(texto: str):
    """Muestra la salida de una herramienta: el texto como texto y las tablas como tablas."""
    for tipo, contenido in salidas.bloques(texto):
        if tipo == "tabla":
            st.dataframe(contenido, hide_index=True, width="stretch")
        elif contenido in TITULOS:
            st.markdown(f"#### {contenido}")
        else:
            st.markdown(contenido.replace("\n", "  \n"))


def grafico_camino(texto: str, titulo: str, porcentaje: bool = True):
    tabla = salidas.tabla_de_meses(texto)
    if tabla is None or tabla.empty:
        return
    fig = go.Figure()
    for i, columna in enumerate(tabla.columns):
        fig.add_trace(go.Scatter(x=tabla.index, y=tabla[columna], mode="lines+markers", name=columna,
                                 line=dict(color=SERIES[i % len(SERIES)])))
    estilo_grafico(fig, 380, title=dict(text=titulo, font=dict(color=TEXTO, size=15)),
                   yaxis_tickformat=".2%" if porcentaje else ",.2f")
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", theme=None)


# ---------- Acceso ----------

COOKIE_ACCESO = "panel_acceso"
HORAS_ACCESO = 12


def _ficha_de_acceso(clave: str) -> str:
    """Lo que se guarda en la cookie: deriva de la contraseña pero no la revela."""
    return hmac.new(clave.encode(), b"panel-renta-fija", "sha256").hexdigest()


def pedir_clave():
    """Si hay PANEL_CLAVE en el .env, el panel pide la contraseña. Al entrar se guarda una cookie por 12 horas en ese
    navegador, así la recarga del cambio de modo (o volver a abrir el link) no la vuelve a pedir. Sin PANEL_CLAVE abre
    directo (uso en tu compu), con un aviso en la barra lateral."""
    clave = config.PANEL_CLAVE
    if not clave or st.session_state.get("autenticado"):
        return
    ficha = _ficha_de_acceso(clave)
    if hmac.compare_digest(st.context.cookies.get(COOKIE_ACCESO, ""), ficha):
        st.session_state["autenticado"] = True
        return
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        st.markdown(f'<div class="encabezado"><div class="titulo">{NOMBRE or "Renta fija"}</div><span>Acceso restringido'
                    '</span></div>', unsafe_allow_html=True)
        with st.form("acceso"):
            intento = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Entrar", width="stretch"):
                if hmac.compare_digest(intento.encode(), clave.encode()):
                    st.session_state["autenticado"] = True
                    _script(f"""<script>window.parent.document.cookie = "{COOKIE_ACCESO}={ficha}; path=/; """
                            f"""max-age={HORAS_ACCESO * 3600}; SameSite=Strict" + (window.parent.location.protocol === "https:" ? "; Secure" : "");
                            </script>""")
                    time.sleep(0.5)                             # que el navegador llegue a guardar la cookie
                    st.rerun()
                time.sleep(1.5)                                 # frena a quien pruebe contraseñas de a muchas
                st.error("Contraseña incorrecta.")
    st.stop()


# La primera visita (sin modo elegido) recarga la página para dejar el modo Blanco: que pase antes del acceso
cambiar_modo(MODO == "dark")
pedir_clave()


# ---------- Barra lateral ----------

# Navegación: una sección a la vez (con pestañas, Streamlit calcularía todas en cada actualización)
SECCIONES = ["Curvas", "Bono", "Breakevens", "Proyecciones", "Fichas", "Carteras"]
ICONOS = {"Curvas": "📈", "Bono": "🧮", "Breakevens": "⚖️", "Proyecciones": "🔭", "Fichas": "🗂️", "Carteras": "💼"}
st.sidebar.markdown('<span class="rotulo-lateral">RENTA FIJA</span>', unsafe_allow_html=True)
# La sección va en la dirección (?seccion=Bono): así sobrevive a la recarga que hace el cambio de modo
inicial = st.query_params.get("seccion", "Curvas")
seccion = st.sidebar.radio("Calculadoras", SECCIONES, format_func=lambda s: f"{ICONOS[s]}  {s}",
                           index=SECCIONES.index(inicial) if inicial in SECCIONES else 0, label_visibility="collapsed")
st.query_params["seccion"] = seccion
try:                                     # novedades de la revisión automática de avisos del Tesoro
    from fuentes_datos.carga import novedades as novedades_tesoro
    _sin_ver = novedades_tesoro.sin_ver()
except Exception:
    _sin_ver = []
if _sin_ver:
    st.sidebar.info(f"🆕 Licitación del Tesoro: {novedades_tesoro.resumen_texto(_sin_ver).split('. Revisalos')[0]}. "
                    "Miralo en Fichas.")
st.sidebar.divider()
st.sidebar.markdown('<span class="rotulo-lateral">PRECIOS</span>', unsafe_allow_html=True)
modo = st.sidebar.radio("Precios", ["Hoy (en vivo)", "Cierre de una fecha"], index=0, label_visibility="collapsed")
fecha = None
if modo == "Cierre de una fecha":
    fecha = st.sidebar.date_input("Fecha de operación", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
intervalos = {"Manual": None, "Cada 1 minuto": 60, "Cada 2 minutos": 120, "Cada 5 minutos": 300}
refresco = st.sidebar.selectbox("Actualizar precios", list(intervalos), index=2 if fecha is None else 0)
segundos = intervalos[refresco] if fecha is None else None
if st.sidebar.button("Actualizar ahora", width="stretch"):
    st.cache_data.clear()
# La "marca" cambia cada intervalo: fuerza a recalcular aunque la caché siga viva
marca = int(pd.Timestamp.now().timestamp() // segundos) if segundos else 0
st.sidebar.divider()
st.sidebar.markdown('<span class="rotulo-lateral">APARIENCIA</span>', unsafe_allow_html=True)
oscuro = st.sidebar.toggle("Modo oscuro", value=MODO == "dark",
                           help="Blanco: vista asesor y presentación a clientes (por defecto). Oscuro: fondo oscuro "
                                "para análisis intensivo.")
cambiar_modo(oscuro)
st.sidebar.divider()
if not config.PANEL_CLAVE:
    st.sidebar.warning("Sin contraseña (PANEL_CLAVE en el .env): no compartas el link así.")
st.sidebar.caption("Mismos cálculos que el agente de renta fija. Convenciones: T+1 BYMA, por 100 VN original, "
                   "TIR efectiva anual. Fuentes: PPI (precios), BCRA (CER, TAMAR, A3500, REM).")

st.markdown(f'<div class="encabezado"><div class="titulo">{seccion}</div><span>{DESCRIPCIONES[seccion]}</span></div>',
            unsafe_allow_html=True)


# ---------- Curvas ----------

def _ficha(ticker: str, familia: str) -> dict | None:
    """La ficha del bono para esa familia (en un dual, la de esa pata)."""
    return next((f for f in metricas.fichas_de(ticker) if f["familia"] == familia), None)


# La tasa que se grafica y se edita en cada curva: TEA, salvo en TAMAR, donde es el spread sobre la TAMAR de
# referencia (TNA 30 d − promedio de los últimos 5 días publicados; Agustin, 27/11/2026).
TASA_CURVA = {"tamar": ("spread", "Spread (%)")}
CAMPOS_EDITABLES = {"Precio": "precio", "TEA (%)": "tea", "TNA (%)": "tna", "Spread (%)": "spread"}


def _tasa(curva: str) -> tuple[str, str]:
    return TASA_CURVA.get(curva, ("tea", "TEA (%)"))


def _recalcular(fila: dict, cambio: tuple[str, float], operacion: date) -> dict:
    """Precio, TEA, TNA, spread y duration de un bono con el precio o la tasa que cargó el usuario."""
    calc = metricas.calculadora(_ficha(fila["ticker"], fila["familia"]), fila["liquidacion"], operacion)
    campo, valor = cambio
    precio = valor if campo == "precio" else metricas.precio_para(calc, valor, campo, referencia=fila["precio"])
    m = calc(precio)
    return {"precio": precio, "tea": m["tea"], "tna": m["tna"], "spread": m.get("spread"), "x": m["duration"] * 365}


def _clave_bono(curva: str, fila: dict) -> tuple:
    return (curva, fila["ticker"], fila["familia"])


def _guardar_edicion(clave_editor: str, curva: str, filas: list[dict]):
    """Pasa lo que se escribió en la tabla a la lista de cambios del usuario (por bono)."""
    cambios = st.session_state.setdefault("cambios_curva", {})
    for fila, editado in st.session_state[clave_editor].get("edited_rows", {}).items():
        clave = _clave_bono(curva, filas[int(fila)])
        for columna, valor in editado.items():
            campo = CAMPOS_EDITABLES.get(columna)
            if campo is None:
                continue
            if valor is None:
                cambios.pop(clave, None)                    # borrar la celda vuelve al precio de mercado
            else:
                cambios[clave] = (campo, valor if campo == "precio" else valor / 100)
    st.session_state["version_editor"] = st.session_state.get("version_editor", 0) + 1


CURVAS_FORWARD = ("tasa_fija", "cer", "tamar", "dl", "hd")
UNIDAD_CURVA = {"tasa_fija": ("TEA", "pesos"), "cer": ("TEA real (CER + x)", "pesos reales"),
                "tamar": ("TEA", "pesos (TAMAR estimada con la publicada y la última para lo que falta)"),
                "dl": ("TEA en dólares", "dólares"), "hd": ("TEA en dólares", "dólares")}
AYUDA_FORWARD = {c: f"{UNIDAD_CURVA[c][0]} entre el vencimiento del bono anterior de la misma curva y el de este bono: "
                    "la tasa a la que habría que renovar el anterior para rendir lo mismo que comprar este hoy. El más "
                    "corto de cada curva queda vacío." for c in CURVAS_FORWARD}
FLECHA_SUBE, FLECHA_BAJA = "▲", "▼"
COLOR_SUBE, COLOR_BAJA = "#15803D", "#B91C1C"


def _color_series() -> list[str]:
    """Un color por curva del gráfico: la principal en esmeralda; las demás, oro, azul y gris."""
    return [ESMERALDA, ORO, P["serie_extra"], GRIS]


def _var_precio(hoy: float | None, antes: float | None) -> str:
    if hoy is None or antes is None or not antes:
        return ""
    d = hoy - antes
    if abs(d) < 0.005:
        return "= 0.00 (0.00%)"
    return f"{FLECHA_SUBE if d > 0 else FLECHA_BAJA} {d:+,.2f} ({d / antes:+.2%})"


def _var_tasa(hoy: float | None, antes: float | None) -> str:
    if hoy is None or antes is None:
        return ""
    pb = round((hoy - antes) * 1e4)
    return "= 0 pb" if pb == 0 else f"{FLECHA_SUBE if pb > 0 else FLECHA_BAJA} {pb:+d} pb"


def _color_variacion(texto) -> str:
    """Verde con flecha hacia arriba si sube, rojo con flecha hacia abajo si baja (Agustin, 27/11/2026)."""
    texto = str(texto or "")
    if texto.startswith(FLECHA_SUBE):
        return f"color: {COLOR_SUBE}; font-weight: 600"
    if texto.startswith(FLECHA_BAJA):
        return f"color: {COLOR_BAJA}; font-weight: 600"
    return f"color: {GRIS}"


def _sin_vacios(df: pd.DataFrame) -> pd.DataFrame:
    """Las celdas sin dato quedan en blanco: columnas de números como números (vacío = NaN) y de texto con ""."""
    df = df.copy()
    for columna in df.columns:
        valores = [v for v in df[columna] if v is not None and not (isinstance(v, float) and pd.isna(v))]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in valores):
            df[columna] = pd.to_numeric(df[columna], errors="coerce").astype(float)
        elif df[columna].dtype == object:
            df[columna] = df[columna].map(lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else v)
    return df


def _numeros_como_texto(df: pd.DataFrame, columnas, formato: str = "{:,.2f}") -> pd.DataFrame:
    """Columnas de solo lectura con celdas sin dato: pasan a texto ya formateado, con "" donde no hay dato (la grilla
    muestra "None" en un número vacío)."""
    df = df.copy()
    for columna in columnas:
        if columna in df.columns:
            df[columna] = [("" if v is None or (isinstance(v, float) and pd.isna(v)) else formato.format(v))
                           for v in df[columna]]
    return df


def _estilo_tabla(df: pd.DataFrame, columnas_variacion: list[str], formatos: dict[str, str]):
    """Styler con las variaciones coloreadas y las celdas vacías en blanco (en vez de "None")."""
    estilo = df.style.format({c: f for c, f in formatos.items() if c in df.columns}, na_rep="")
    if columnas_variacion:
        estilo = estilo.map(_color_variacion, subset=[c for c in columnas_variacion if c in df.columns])
    return estilo


def _matriz_forwards(bonos: list[dict], liquidacion: date, curva: str, titulo: str = ""):
    """Forward entre cada par de bonos: el corto en las columnas y el largo en las filas (decisión de Agustin)."""
    tickers, celdas = calc_forwards.matriz(bonos, liquidacion)
    if len(tickers) < 2:
        return
    cortos, largos = tickers[:-1], tickers[1:]
    df = pd.DataFrame([[f"{celdas[(corto, largo)] * 100:.2f}" if (corto, largo) in celdas else "" for corto in cortos]
                       for largo in largos], index=pd.Index(largos, name="Largo ↓ / Corto →"), columns=cortos)
    real = {"cer": " real (CER + x)", "dl": " en dólares", "hd": " en dólares"}.get(curva, "")
    st.markdown(f"**Matriz de forwards{real} (TEA, %){' · ' + titulo if titulo else ''}**")
    st.dataframe(df, width="stretch", column_config={c: st.column_config.TextColumn(width="small") for c in cortos})


def _texto_matriz(curva: str) -> str:
    real = {"cer": " real (CER + x)", "dl": " en dólares", "hd": " en dólares"}.get(curva, "")
    return (f"Columnas: bono corto; filas: bono largo. Cada celda es la tasa{real} a la que habría que renovar el corto, "
            "a su vencimiento, hasta el vencimiento del largo para rendir lo mismo que comprar el largo hoy: "
            "f = [(1 + TIR largo)^t largo / (1 + TIR corto)^t corto]^(1 / (t largo − t corto)) − 1, con t en años "
            "desde la liquidación hasta cada vencimiento. Solo entre bonos de la misma curva, con los precios o tasas "
            "que hayas cargado en la tabla. En bonos con cupones es la aproximación con la TIR de cada bono."
            + (" En TAMAR, con la TEA de cada bono (no con el spread)." if curva == "tamar" else ""))


def _exit_bono(m: dict, ficha: dict, liquidacion: date):
    """Calculadora individual: retorno vendiendo en una fecha a una exit yield, y su sensibilidad."""
    st.markdown("#### Exit yield")
    futuros = [x for x in m["flujos"] if x["fecha"] > liquidacion]
    if not futuros:
        return
    col1, col2, _ = st.columns([1, 1, 2])
    clave = f"{ficha['ticker']}_{ficha['familia']}"
    vto = max(x["fecha"] for x in futuros)
    salida = col1.date_input("Fecha de salida", value=min(liquidacion + timedelta(days=182), vto),
                             min_value=liquidacion + timedelta(days=1), format="DD/MM/YYYY", key=f"bono_exit_fecha_{clave}")
    exit_tea = col2.number_input("Exit yield (TEA, %)", value=float(round(m["tea"] * 100, 2)), step=0.25,
                                 format="%.2f", key=f"bono_exit_tea_{clave}") / 100
    try:
        r = calc_exit.retorno(futuros, m["tea"], liquidacion, salida, exit_tea)
        sens = calc_exit.sensibilidad(futuros, m["tea"], liquidacion, salida, exit_tea)
    except Exception as e:
        st.error(f"No se pudo calcular: {e}")
        return
    a, b, c_, d = st.columns(4)
    a.metric("Precio de salida", f"{r['precio_salida']:,.2f}" if not r["vence_antes"] else "vence antes",
             help="Dirty teórico por 100 VN original, en la unidad del bono")
    b.metric("Cobrado hasta la salida", f"{r['cobrado']:,.2f}", help="Reinvertido a la exit yield hasta la salida")
    c_.metric("Retorno del período", f"{r['retorno']:.2%}", help=f"{r['dias']} días")
    d.metric("Retorno anualizado (TEA)", f"{r['anualizado']:.2%}" if r["anualizado"] is not None else "–",
             f"{round((r['anualizado'] - m['tea']) * 1e4):+d} pb vs TIR de hoy" if r["anualizado"] is not None else None,
             delta_color="normal")
    tabla = pd.DataFrame([{"Exit yield (%)": x["tea_salida"] * 100, "Cambio (pb)": x["pb"],
                           "Precio de salida": x["precio_salida"], "Retorno del período (%)": x["retorno"] * 100,
                           "Retorno anualizado (%)": x["anualizado"] * 100 if x["anualizado"] is not None else None}
                          for x in sens])
    st.dataframe(tabla, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%.2f") for c in tabla.columns if c != "Cambio (pb)"})
    st.caption(f"En {m['unidad']}. Precio de hoy en esa unidad: {r['precio_hoy']:,.2f} (valor presente de los flujos a "
               "la TIR de hoy). Cupones y amortizaciones hasta la salida reinvertidos a la exit yield; con exit yield "
               "igual a la TIR de hoy, el retorno anualizado es la TIR de hoy.")


@st.cache_data(ttl=60, show_spinner=False)
def _flujos_bono(ticker: str, familia: str, precio: float, liquidacion: date, operacion: date) -> list[dict]:
    ficha = _ficha(ticker, familia)
    return metricas.calculadora(ficha, liquidacion, operacion)(precio)["flujos"] if ficha else []


def _guardar_exit(clave_editor: str, curva: str, filas: list[dict]):
    """La exit yield o el precio de salida que se escribió para cada bono (se recuerdan aunque cambie la fecha)."""
    cambios = st.session_state.setdefault("cambios_exit", {})
    for fila, editado in st.session_state[clave_editor].get("edited_rows", {}).items():
        clave = _clave_bono(curva, filas[int(fila)])
        for columna, valor in editado.items():
            campo = {"Exit yield (%)": "tea", "Precio de salida": "precio"}.get(columna)
            if campo is None:
                continue
            if isinstance(valor, str):                      # el precio de salida se escribe como texto
                texto = valor.strip().replace(" ", "")
                texto = texto.replace(".", "").replace(",", ".") if "," in texto else texto.replace(",", "")
                try:
                    valor = float(texto) if texto else None
                except ValueError:
                    st.session_state["aviso_exit"] = f"'{valor}' no es un precio."
                    continue
            if valor is None:
                cambios.pop(clave, None)                    # borrar la celda vuelve a la TIR de hoy
            else:
                cambios[clave] = (campo, valor / 100 if campo == "tea" else valor)
    st.session_state["version_exit"] = st.session_state.get("version_exit", 0) + 1


def _tabla_exit(filas: list[dict], curva: str, operacion: date, con_curva: bool):
    """Retorno de cada bono si se vende en una fecha a la exit yield que se elija para él (o a un precio de salida,
    del que sale la exit yield). Sin dato cargado, la exit yield es la TIR de hoy (Agustin, 27/11/2026)."""
    st.markdown("**Retornos con exit yield**")
    liquidacion = min(f["liquidacion"] for f in filas)
    col1, col2, _ = st.columns([1, 1, 2])
    defecto = min(liquidacion + timedelta(days=182), max(f["vencimiento"] for f in filas))
    salida = col1.date_input("Fecha de salida", value=defecto, min_value=liquidacion + timedelta(days=1),
                             format="DD/MM/YYYY", key=f"exit_fecha_{curva}")
    cambios = st.session_state.get("cambios_exit", {})
    if any(k[0] == curva for k in cambios) and col2.button("Volver a la TIR de hoy", key=f"exit_reset_{curva}"):
        st.session_state["cambios_exit"] = {k: v for k, v in cambios.items() if k[0] != curva}
        st.session_state["version_exit"] = st.session_state.get("version_exit", 0) + 1
        st.rerun(scope="fragment")
    registros = []
    for f in filas:
        cambio = cambios.get(_clave_bono(curva, f))
        fila = {"Ticker": f["ticker"], **({"Curva": f["serie"] or NOMBRES_CURVA[curva].split(" (")[0]} if con_curva else {}),
                "TIR hoy (%)": f["tea"] * 100, "Exit yield (%)": None, "Precio de salida": "",
                "Cobrado hasta la salida": None, "Retorno del período (%)": None, "Retorno anualizado (%)": None,
                "": "✎ exit yield" if cambio and cambio[0] == "tea" else "✎ precio" if cambio else ""}
        fila["Exit yield (%)"] = (cambio[1] if cambio and cambio[0] == "tea" else f["tea"]) * 100
        try:
            flujos = _flujos_bono(f["ticker"], f["familia"], f["precio"], f["liquidacion"], operacion)
            if cambio and cambio[0] == "precio":
                tea_salida = calc_exit.tasa_para(flujos, f["liquidacion"], salida, cambio[1])
            else:
                tea_salida = cambio[1] if cambio else f["tea"]
            r = calc_exit.retorno(flujos, f["tea"], f["liquidacion"], salida, tea_salida)
            fila.update({"Exit yield (%)": tea_salida * 100,
                         "Precio de salida": f"{r['precio_salida']:,.2f}" if not r["vence_antes"] else "",
                         "Cobrado hasta la salida": r["cobrado"], "Retorno del período (%)": r["retorno"] * 100,
                         "Retorno anualizado (%)": r["anualizado"] * 100 if r["anualizado"] is not None else None})
            if r["vence_antes"]:
                fila[""] = "vence antes"
        except Exception as e:
            fila[""] = f"sin cálculo: {e}"
        registros.append(fila)
    tabla = _numeros_como_texto(_sin_vacios(pd.DataFrame(registros)),
                                ["Cobrado hasta la salida", "Retorno del período (%)", "Retorno anualizado (%)"])
    clave = f"exit_tabla_{curva}_{st.session_state.get('version_exit', 0)}"
    st.data_editor(_estilo_tabla(tabla, [], {"TIR hoy (%)": "{:.2f}"}), key=clave, hide_index=True,
                   width="stretch", on_change=_guardar_exit, args=(clave, curva, filas),
                   column_config={**{c: st.column_config.NumberColumn(format="%.2f") for c in ("TIR hoy (%)", "Exit yield (%)")},
                                  "Exit yield (%)": st.column_config.NumberColumn(
                                      format="%.2f", help="TEA de salida de este bono. Escribí una tasa, o un precio de "
                                                          "salida en la columna de al lado y sale la tasa."),
                                  "Precio de salida": st.column_config.TextColumn(
                                      help="Dirty teórico por 100 VN original, en la unidad del bono, a la fecha de "
                                           "salida. Escribí uno y sale la exit yield."),
                                  "Curva": st.column_config.TextColumn(width="medium"),
                                  "": st.column_config.TextColumn(width="medium")},
                   disabled=[c for c in tabla.columns if c not in ("Exit yield (%)", "Precio de salida")])
    if st.session_state.get("aviso_exit"):
        st.warning(st.session_state.pop("aviso_exit"))
    unidad = UNIDAD_CURVA.get(curva, ("", "su unidad"))[1]
    st.caption(f"Vendiendo el {salida:%d/%m/%Y}. Cada bono arranca con la TIR de hoy como exit yield: cambiala casilla por "
               "casilla, o escribí un precio de salida y se calcula la tasa a esa fecha. Borrar la celda vuelve a la TIR "
               f"de hoy. Precio de salida: dirty teórico por 100 VN original, en {unidad}. Cobrado: cupones y "
               "amortizaciones hasta la salida, reinvertidos a la exit yield. \"vence antes\": se cobra todo y se "
               "reinvierte a la exit yield hasta la fecha."
               + (" En TAMAR, la exit yield es la TEA del bono (no el spread)." if curva == "tamar" else ""))


if seccion == "Curvas":
    @st.fragment(run_every=segundos)
    def panel_curvas():
        marca_actual = int(pd.Timestamp.now().timestamp() // segundos) if segundos else 0
        dolar = "ccl" if st.session_state.get("dolar_hd") == "Cable" else "mep"
        try:
            puntos, contexto, errores, liquidacion = datos_curvas(fecha, marca_actual, dolar)
        except Exception as e:                       # sin conexión, sin feriados, etc.
            st.error(f"No se pudieron armar las curvas: {e}")
            return
        operacion = _contexto(fecha)[0]
        try:
            anteriores, dia_anterior = datos_anteriores(operacion, dolar)
        except Exception:
            anteriores, dia_anterior = {}, None
        st.caption(f"Liquidación {liquidacion:%d/%m/%Y} · actualizado {pd.Timestamp.now():%H:%M:%S}"
                   + (f" · se actualiza {refresco.lower()}" if segundos else "")
                   + (f" · variaciones contra el cierre del {dia_anterior:%d/%m/%Y}" if dia_anterior else ""))
        disponibles = [c for c in NOMBRES_CURVA if puntos.get(c)]
        if not disponibles:
            st.warning("No hay bonos con precio para armar curvas.")
            return
        if st.session_state.get("curva_elegida") not in disponibles:
            st.session_state["curva_elegida"] = disponibles[0]
        col_curva, col_dolar = st.columns([4, 1])
        c = col_curva.segmented_control("Curva", disponibles, format_func=NOMBRES_CURVA.get,
                                        key="curva_elegida") or disponibles[0]
        if c == "hd":
            col_dolar.segmented_control("Dólar", ["MEP", "Cable"], default="MEP", key="dolar_hd",
                                        help="Precio en dólares MEP (ticker D) o cable (ticker C)")
        clave_tasa, columna_tasa = _tasa(c)
        nombre_tasa = "spread" if clave_tasa == "spread" else "TEA"

        # Mercado y, encima, lo que cargó el usuario en la tabla (precio o tasa de un bono)
        de_mercado = sorted(puntos[c], key=lambda p: p["x"])
        cambios = st.session_state.get("cambios_curva", {})
        filas, avisos = [], []
        for p in de_mercado:
            fila = dict(p, editado=None, antes=anteriores.get(_clave_bono(c, p)))
            cambio = cambios.get(_clave_bono(c, p))
            if cambio:
                try:
                    fila.update(_recalcular(p, cambio, operacion), editado=cambio[0])
                except (ValueError, ArithmeticError, TypeError) as e:
                    avisos.append(f"{p['ticker']}: {e}")
            filas.append(fila)
        series = list(dict.fromkeys(f["serie"] for f in filas))
        series.sort(key=lambda s: (s is not None, s != curvas_mercado.SERIE_BONARES, str(s)))
        nombre_serie = lambda s: s or NOMBRES_CURVA[c].split(" (")[0]
        colores = dict(zip(series, _color_series() * 3))
        varias = len(series) > 1

        fig = go.Figure()
        editados = [f for f in filas if f["editado"]]
        if editados:                                        # dónde estaban a precio de mercado
            originales = [p for p in de_mercado if _clave_bono(c, p) in cambios]
            fig.add_trace(go.Scatter(x=[p["x"] / 365 for p in originales], y=[p[clave_tasa] for p in originales],
                                     mode="markers", name="A precio de mercado", hoverinfo="skip",
                                     marker=dict(size=9, color="rgba(0,0,0,0)", line=dict(color=GRIS, width=1.5))))
        for serie in series:
            de_serie = [f for f in filas if f["serie"] == serie]
            color = colores[serie]
            fig.add_trace(go.Scatter(
                x=[f["x"] / 365 for f in de_serie], y=[f[clave_tasa] for f in de_serie], mode="markers+text",
                name=nombre_serie(serie), text=[f["ticker"] for f in de_serie], textposition="top center",
                textfont=dict(size=10, color=GRIS),
                marker=dict(size=[12 if f["editado"] else 9 for f in de_serie], color=color,
                            line=dict(color=TEXTO, width=[1.6 if f["editado"] else 0.6 for f in de_serie]),
                            symbol=["diamond" if f["editado"] else "circle" for f in de_serie]),
                hovertemplate="%{text}<br>Duration %{x:.2f} años<br>" + nombre_tasa + " %{y:.2%}<extra>"
                              + nombre_serie(serie) + "</extra>"))
            mercado_serie = [p for p in de_mercado if p["serie"] == serie and p["x"] > 0]
            if len(mercado_serie) >= 3:                    # cada curva se ajusta aparte, con sus bonos a mercado
                try:
                    xs = [p["x"] / 365 for p in mercado_serie]
                    ajuste = calc_curva.ajustar_log([(x, p[clave_tasa]) for x, p in zip(xs, mercado_serie)])
                    grilla = [min(xs) + i * (max(xs) - min(xs)) / 60 for i in range(61)]
                    fig.add_trace(go.Scatter(x=grilla, y=[calc_curva.tea_teorica(ajuste, x) for x in grilla],
                                             mode="lines", hoverinfo="skip", line=dict(color=color, dash="dot"),
                                             name=f"Curva {nombre_serie(serie)} (R² {ajuste['r2']:.2f})"))
                except Exception:
                    pass
        estilo_grafico(fig, 500, xaxis_title="Duration (años)",
                       yaxis_title="Spread sobre TAMAR" if clave_tasa == "spread" else "TEA", yaxis_tickformat=".1%")
        fig.update_layout(legend=dict(orientation="h", y=1.02, yanchor="bottom", x=0, font=dict(color=GRIS)),
                          margin=dict(t=60, b=50))
        with st.container(border=True):
            st.plotly_chart(fig, width="stretch", theme=None)

        # La tabla se puede editar: precio, tasa o TNA de cualquier bono; lo demás se recalcula (también las forwards)
        con_forwards = c in CURVAS_FORWARD
        anterior = {}
        if con_forwards:
            for serie in series:
                bonos_serie = [{"ticker": f["ticker"], "vencimiento": f["vencimiento"], "tea": f["tea"]}
                               for f in filas if f["serie"] == serie]
                anterior.update({(serie, t): v for t, v in calc_forwards.al_anterior(bonos_serie, liquidacion).items()})
        registros = []
        for f in filas:
            antes = f["antes"] or {}
            marca_fila = {"precio": "✎ precio", "tea": "✎ TEA", "tna": "✎ TNA", "spread": "✎ spread"}.get(f["editado"], "")
            if f.get("sin_emitir"):
                marca_fila = (marca_fila + " · " if marca_fila else "") + "precio de corte, sin cotizar"
            registros.append({
                "Ticker": f["ticker"], **({"Curva": nombre_serie(f["serie"])} if varias else {}),
                "Precio": f["precio"], "Var. precio": _var_precio(f["precio"], antes.get("precio")),
                columna_tasa: f[clave_tasa] * 100 if f.get(clave_tasa) is not None else None,
                f"Var. {nombre_tasa} (pb)": _var_tasa(f.get(clave_tasa), antes.get(clave_tasa)),
                "TNA (%)": f["tna"] * 100 if f.get("tna") is not None else None,
                "Var. TNA (pb)": _var_tasa(f.get("tna"), antes.get("tna")),
                "Duration (años)": f["x"] / 365,
                **({"Forwards (%)": anterior[(f["serie"], f["ticker"])] * 100
                    if anterior.get((f["serie"], f["ticker"])) is not None else None} if con_forwards else {}),
                "": marca_fila})
        tabla = _numeros_como_texto(_sin_vacios(pd.DataFrame(registros)), ["Forwards (%)"], "{:.2f}")
        variaciones = ["Var. precio", f"Var. {nombre_tasa} (pb)", "Var. TNA (pb)"]
        clave = f"editor_{c}_{st.session_state.get('version_editor', 0)}"
        st.data_editor(_estilo_tabla(tabla, variaciones, {}),
                       key=clave, hide_index=True, width="stretch",
                       disabled=[col for col in tabla.columns if col not in ("Precio", columna_tasa, "TNA (%)")],
                       on_change=_guardar_edicion, args=(clave, c, filas),
                       column_config={"Precio": st.column_config.NumberColumn(format="%.2f", min_value=0.0001),
                                      columna_tasa: st.column_config.NumberColumn(
                                          format="%.2f", help="TNA de 30 días menos la TAMAR de referencia (promedio de "
                                                              "los últimos 5 días hábiles publicados)"
                                          if clave_tasa == "spread" else None),
                                      "TNA (%)": st.column_config.NumberColumn(format="%.2f", help=AYUDA_TNA.get(c, "")),
                                      "Duration (años)": st.column_config.NumberColumn(format="%.2f"),
                                      "Forwards (%)": st.column_config.TextColumn(help=AYUDA_FORWARD[c] if con_forwards
                                                                                  else None),
                                      "Curva": st.column_config.TextColumn(width="medium"),
                                      "": st.column_config.TextColumn(width="medium")})
        col1, col2 = st.columns([3, 1])
        col1.caption(f"Escribí un precio, {'un spread' if clave_tasa == 'spread' else 'una TEA'} o una TNA en la tabla y "
                     "se recalcula el resto del bono y su punto en la curva (rombo; el círculo gris es su lugar a precio "
                     "de mercado, y la línea punteada, la curva de mercado). Borrar la celda vuelve al mercado. "
                     "Variaciones contra el cierre del día hábil anterior: en verde con ▲ si suben, en rojo con ▼ si "
                     "bajan." + (" Cada curva del gráfico se ajusta con sus propios bonos (desde 3)." if varias else ""))
        if editados and col2.button("Volver todo a mercado", width="stretch"):
            st.session_state["cambios_curva"] = {k: v for k, v in cambios.items() if k[0] != c}
            st.session_state["version_editor"] = st.session_state.get("version_editor", 0) + 1
            st.rerun(scope="fragment")
        for aviso in avisos:
            st.warning(f"No se pudo recalcular {aviso}")
        if con_forwards:
            for serie in series:
                bonos_serie = [{"ticker": f["ticker"], "vencimiento": f["vencimiento"], "tea": f["tea"]}
                               for f in filas if f["serie"] == serie]
                _matriz_forwards(bonos_serie, liquidacion, c, nombre_serie(serie) if varias else "")
            if any(sum(1 for f in filas if f["serie"] == s) >= 2 for s in series):
                st.caption(_texto_matriz(c))
        _tabla_exit(filas, c, operacion, varias)
        if c == "tasa_fija":
            with st.expander("Curva teórica de tasa fija (a precio de mercado): desvío de cada bono contra la curva y sus vecinos"):
                mostrar(salida_herramienta("curva_tf", marca_actual, fecha=fecha.isoformat() if fecha else None))
        if errores:
            with st.expander(f"{len(errores)} bonos sin precio o sin cálculo"):
                st.write("\n".join(f"- {e}" for e in errores))

    panel_curvas()


# ---------- Bono ----------

@st.cache_data(ttl=60, show_spinner=False)
def precio_de_mercado(ticker: str, familia: str, fecha: date | None, liquidacion: date, _marca: int) -> tuple[float, str, date]:
    """(precio, de dónde salió, liquidación): un bono todavía no emitido va al precio de corte, liquidando en la emisión."""
    return mercado.precio_bono(_ficha(ticker, familia), fecha, liquidacion, "D" if familia == "hard_dollar" else "")


NOMBRES_DETALLE = {"valor_tecnico": "Valor técnico", "paridad": "Paridad", "interes_corrido": "Interés corrido",
                   "duration_modificada": "Duration modificada", "current_yield": "Current yield",
                   "precio_usd": "Precio en USD", "tipo_cambio": "A3500", "pago_final": "Pago final",
                   "tamar_bono": "TAMAR del bono", "tem": "TEM", "tem_bono": "TEM del bono", "convexidad": "Convexidad"}
PORCENTAJES = {"paridad", "current_yield", "tamar_bono", "tem", "tem_bono"}

if seccion == "Bono":
    fichas_calculables = [f for f in leer_fichas.todas() if f["familia"] in metricas.UNIDAD]
    tickers = sorted({f["ticker"].upper() for f in fichas_calculables})
    col1, col2, col3 = st.columns([1, 1, 2])
    ticker = col1.selectbox("Bono", tickers, index=tickers.index("TZXD7") if "TZXD7" in tickers else 0)
    patas = [f for f in fichas_calculables if f["ticker"].upper() == ticker]
    ficha = patas[0]
    if len(patas) > 1:
        familia = col2.selectbox("Pata", [f["familia"] for f in patas], help="Bono dual: cada pata se calcula aparte")
        ficha = next(f for f in patas if f["familia"] == familia)
    modo = col3.radio("Calcular", ["La tasa, a partir de un precio", "El precio, a partir de una tasa"],
                      horizontal=True, key="bono_modo")
    try:
        operacion, liquidacion, fecha_precios = _contexto(fecha)
        origen_precio = None
        try:
            precio_mkt, origen_precio, liquidacion = precio_de_mercado(ticker, ficha["familia"], fecha_precios,
                                                                       liquidacion, marca)
        except Exception:
            precio_mkt = None
            liquidacion = max(liquidacion, ficha["emision"])     # sin emitir y sin corte: desde la emisión
        calc = metricas.calculadora(ficha, liquidacion, operacion)
        try:
            m_mercado = calc(precio_mkt) if precio_mkt else None
        except Exception:
            precio_mkt, m_mercado = None, None
        col1, col2, col3 = st.columns([1, 1, 2])
        if modo.startswith("La tasa"):
            precio = col1.number_input("Precio", value=float(round(precio_mkt, 2)) if precio_mkt else 100.0, min_value=0.0001,
                                       step=0.5, format="%.2f", key=f"bono_precio_{ticker}_{ficha['familia']}")
        else:
            tipo = col1.radio("Tasa", ["TEA", "TNA"], horizontal=True, key="bono_tipo")
            base = (m_mercado[tipo.lower()] if m_mercado and m_mercado[tipo.lower()] is not None else 0.30)
            objetivo = col2.number_input(f"{tipo} (%)", value=float(round(base * 100, 2)), step=0.25, format="%.2f",
                                         key=f"bono_tasa_{ticker}_{ficha['familia']}_{tipo}") / 100
            precio = metricas.precio_para(calc, objetivo, tipo.lower(), referencia=precio_mkt or 100.0)
        m = calc(precio)
    except Exception as e:
        st.error(f"No se pudo calcular: {e}")
        st.stop()

    st.caption(f"{ficha.get('tipo', '')} · {ficha['familia'].replace('_', ' ')} · vence {ficha['vencimiento']:%d/%m/%Y} · "
               f"liquidación {liquidacion:%d/%m/%Y}"
               + (f" · precio de mercado {precio_mkt:,.2f}" if precio_mkt and not (origen_precio or "").startswith("precio de corte")
                  else f" · {origen_precio}: {precio_mkt:,.2f}" if precio_mkt else " · sin precio de mercado"))
    def _delta(valor, referencia, pb=False):
        if referencia is None or valor is None or abs(valor - referencia) < (5e-5 if pb else 0.005):
            return None
        return (f"{round((valor - referencia) * 1e4) + 0:+d} pb vs mercado" if pb
                else f"{round(valor - referencia, 2) + 0:+,.2f} vs mercado")
    a, b, c_, d = st.columns(4)
    a.metric("Precio", f"{precio:,.2f}", _delta(precio, precio_mkt), delta_color="off")
    b.metric("TEA", f"{m['tea']:.2%}", _delta(m["tea"], m_mercado and m_mercado["tea"], True), delta_color="inverse")
    c_.metric("TNA", f"{m['tna']:.2%}" if m["tna"] is not None else "–",
              _delta(m["tna"], m_mercado and m_mercado["tna"], True), delta_color="inverse", help=None)
    d.metric("Duration", f"{m['duration']:.2f} años")
    extras = [(k, v) for k, v in m["detalle"].items() if k in NOMBRES_DETALLE and isinstance(v, (int, float))]
    if extras:
        columnas = st.columns(min(len(extras), 6))
        for (k, v), col in zip(extras[:6], columnas):
            col.metric(NOMBRES_DETALLE[k], f"{v:.2%}" if k in PORCENTAJES else f"{v:,.4f}" if abs(v) < 10 else f"{v:,.2f}")

    st.markdown(f"#### Flujo de fondos (por 100 VN original, en {m['unidad']})")
    flujos = pd.DataFrame([{"Fecha de pago": fl["fecha"], "Cupón": fl["cupon"], "Amortización": fl["amortizacion"],
                            "Total": fl["total"], "Residual después del pago": fl["residual"]} for fl in m["flujos"]])
    formato = {c: st.column_config.NumberColumn(format="%.4f") for c in ("Cupón", "Amortización", "Total")}
    formato["Residual después del pago"] = st.column_config.NumberColumn(format="%.2f")
    formato["Fecha de pago"] = st.column_config.DateColumn(format="DD/MM/YYYY")
    if m["ajuste"]:
        nombre, factor = m["ajuste"]
        flujos[f"Total {nombre}"] = flujos["Total"] * factor
        formato[f"Total {nombre}"] = st.column_config.NumberColumn(format="%.2f")
    st.dataframe(flujos, hide_index=True, width="stretch", column_config=formato)
    _exit_bono(m, ficha, liquidacion)
    if ficha["familia"] == "tamar_capitalizable":
        st.caption("El pago final usa la TAMAR ya publicada y, para los días que faltan, la última TAMAR. Para otros "
                   "supuestos, la sección Proyecciones.")
    elif m.get("pago_conocido") and not m.get("cer_conocido"):
        st.caption(f"El pago final ya está fijo en pesos ({m['extra']['pago_final']:,.4f} por 100 VN): "
                   + ("el A3500 de pago ya está publicado" if "tipo_cambio_pago" in m["extra"]
                      else "ya se publicó la TAMAR de toda la ventana")
                   + ". El bono se valúa como tasa fija y figura en esa curva.")
    elif m.get("cer_conocido"):
        st.caption(f"El CER final ya está publicado ({m['extra']['cer_final']:,.4f}): el pago queda fijo en pesos y el "
                   "bono se valúa como tasa fija (TEA nominal)."
                   + (f" TEA real: {m['detalle']['tea_real']:.2%}." if m["detalle"].get("tea_real") is not None else ""))
    elif ficha["familia"] in ("cer_cero_cupon", "cer_cupon"):
        st.caption("Los flujos están en términos reales: se cobran multiplicados por el coeficiente CER del pago. La "
                   "última columna los muestra con el CER de hoy; para proyectarlos, la sección Proyecciones.")

# ---------- Breakevens ----------

if seccion == "Breakevens":
    tipo = st.radio("Breakeven", ["todos", *breakevens.TIPOS], horizontal=True,
                    format_func=lambda t: "Todos" if t == "todos" else breakevens.NOMBRES[t].split(" (")[0])
    mostrar(salida_herramienta("breakevens", marca, tipo=tipo, fecha=fecha.isoformat() if fecha else None))


# ---------- Proyecciones ----------

if seccion == "Proyecciones":
    variable = st.radio("Variable", ["Inflación (CER)", "TAMAR", "Dólar oficial (A3500)", "Dólar MEP", "Dólar CCL"],
                        horizontal=True)
    clave = {"TAMAR": "tamar", "Dólar oficial (A3500)": "oficial", "Dólar MEP": "mep", "Dólar CCL": "ccl"}.get(variable)
    opciones = {"Inflación (CER)": ["breakeven", "rem", "mensual:2%"], "TAMAR": ["rem", "actual", "tna:30%"],
                "Dólar oficial (A3500)": ["rem", "breakeven", "mensual:1.5%"], "Dólar MEP": ["mensual:1.5%"],
                "Dólar CCL": ["mensual:1.5%"]}[variable]
    if clave:
        opciones += [f"escenario:{n}" for n in proyecciones.escenarios(clave)]
    else:
        opciones += [f"escenario:{n}" for n in proyeccion_cer.escenarios()]
    col1, col2, col3 = st.columns([2, 3, 1])
    elegida = col1.selectbox("Supuesto", opciones + ["otro (escribilo)"])
    fuente = col2.text_input("Camino propio", placeholder="camino:2026-12=2.5%;2027=25%;resto=1.5%",
                             disabled=elegida != "otro (escribilo)") if elegida == "otro (escribilo)" else elegida
    filtro = col3.text_input("Ticker (opcional)") or None
    if fuente:
        fecha_texto = fecha.isoformat() if fecha else None
        if variable == "Inflación (CER)":
            texto = salida_herramienta("cer", marca, fuente=fuente, ticker=filtro, fecha=fecha_texto)
        elif clave == "tamar":
            texto = salida_herramienta("tamar", marca, fuente=fuente, ticker=filtro, fecha=fecha_texto)
        else:
            texto = salida_herramienta("dolar", marca, tipo=clave, fuente=fuente, ticker=filtro, fecha=fecha_texto)
        grafico_camino(texto, f"Camino de {variable.lower()}: el usado contra el breakeven y el REM",
                       porcentaje=not variable.startswith("Dólar"))
        mostrar(texto)


# ---------- Fichas ----------

if seccion == "Fichas":
    from fuentes_datos.carga import fichas_documentos as fd
    if _sin_ver:
        with st.container(border=True):
            st.markdown(f"**🆕 Novedades de la revisión automática ({len(_sin_ver)} aviso{'s' if len(_sin_ver) > 1 else ''})**")
            for n in _sin_ver:
                detalle = []
                for clave, nombre in (("nuevos", "Borradores nuevos"), ("completados", "Completados"),
                                      ("cortes", "Valores de corte"), ("cambios", "Cambios propuestos")):
                    if n[clave]:
                        detalle.append(f"{nombre}: {'; '.join(map(str, n[clave]))}")
                st.markdown(f"- {n['cuando'].replace('T', ' ')} · [{n['documento']} del {n['fecha']}]({n['url']})  \n  "
                            + "  \n  ".join(detalle))
            if st.button("Marcar como vistas"):
                novedades_tesoro.marcar_vistas()
                st.rerun()
    todas = leer_fichas.todas()
    resumen = pd.Series([f["familia"] for f in todas]).value_counts().rename_axis("Familia").reset_index(name="Bonos")
    col1, col2 = st.columns([1, 2])
    col1.subheader(f"{len(todas)} fichas aprobadas")
    col1.dataframe(resumen, hide_index=True, width="stretch")
    col2.subheader(f"{len(fd.pendientes())} borradores pendientes")
    try:
        col2.code(fd.describir_borradores(), language="toml")
    except ValueError as e:
        col2.error(str(e))
    col2.caption("Para aprobar: python -m fuentes_datos.carga.fichas_documentos aprobar <TICKER>, o pedíselo al agente.")


# ---------- Carteras ----------

if seccion == "Carteras":
    carteras_panel.seccion(fecha, marca, estilo_grafico, {"series": SERIES, "texto": TEXTO, "gris": GRIS,
                                                         "superficie": SUPERFICIE, "grilla": GRILLA,
                                                         "esmeralda": ESMERALDA})
