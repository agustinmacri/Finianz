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
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # para importar el proyecto al correr con streamlit

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

import config
from renta_fija import leer_fichas
from renta_fija.calculadoras import curva as calc_curva
from renta_fija import curvas_mercado, mercado, metricas
from tools import bonos, breakevens, curvas, proyeccion_cer, proyecciones
from web import carteras_panel, salidas

IMAGENES = Path(__file__).resolve().parent / "imagenes"
# Por ahora el producto se muestra sin nombre (Agustin, 20/11/2026): sin "Finianz" en la pestaña, el logo ni el acceso.
# Para volver a mostrarlo: MOSTRAR_NOMBRE = True.
MOSTRAR_NOMBRE = False
NOMBRE = "Finianz" if MOSTRAR_NOMBRE else ""
st.set_page_config(page_title=f"{NOMBRE} · Renta fija" if NOMBRE else "Renta fija", page_icon=str(IMAGENES / "icono.svg"), layout="wide")
NOMBRES_CURVA = {"tasa_fija": "Tasa fija (TEA)", "cer": "CER (TEA real)", "tamar": "TAMAR (TEA)",
                 "dl": "Dollar linked (TEA en USD)", "hd": "Bonares (TEA en USD)"}
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
COLORES = {c: ESMERALDA for c in ("tasa_fija", "cer", "tamar", "dl", "hd")}
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
def datos_curvas(fecha: date | None, _marca: int):
    operacion, liquidacion, fecha_precios = _contexto(fecha)
    puntos, contexto, errores = curvas_mercado.armar(operacion, liquidacion, fecha_precios)
    return puntos, contexto, errores, liquidacion


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

def _ficha_de_curva(ticker: str, curva: str) -> dict | None:
    return next((f for f in leer_fichas.fichas_de(ticker) if metricas.FAMILIAS_CURVA.get(f["familia"]) == curva
                 and "DUAL" not in f.get("tipo", "").upper()), None)


def _recalcular(ticker: str, curva: str, cambio: tuple[str, float], referencia: float) -> dict:
    """Precio, TEA, TNA y duration de un bono con el precio o la tasa que cargó el usuario."""
    operacion, liquidacion, _ = _contexto(fecha)
    calc = metricas.calculadora(_ficha_de_curva(ticker, curva), liquidacion, operacion)
    campo, valor = cambio
    precio = valor if campo == "precio" else metricas.precio_para(calc, valor, campo, referencia=referencia)
    m = calc(precio)
    return {"precio": precio, "tea": m["tea"], "tna": m["tna"], "x": m["duration"] * 365}


def _guardar_edicion(clave_editor: str, curva: str, filas: list[dict]):
    """Pasa lo que se escribió en la tabla a la lista de cambios del usuario (por ticker)."""
    cambios = st.session_state.setdefault("cambios_curva", {})
    columnas = {"Precio": "precio", "TEA (%)": "tea", "TNA (%)": "tna"}
    for fila, editado in st.session_state[clave_editor].get("edited_rows", {}).items():
        ticker = filas[int(fila)]["ticker"]
        for columna, valor in editado.items():
            if columna not in columnas:
                continue
            if valor is None:
                cambios.pop((curva, ticker), None)          # borrar la celda vuelve al precio de mercado
            else:
                campo = columnas[columna]
                cambios[(curva, ticker)] = (campo, valor if campo == "precio" else valor / 100)
    st.session_state["version_editor"] = st.session_state.get("version_editor", 0) + 1


if seccion == "Curvas":
    @st.fragment(run_every=segundos)
    def panel_curvas():
        marca_actual = int(pd.Timestamp.now().timestamp() // segundos) if segundos else 0
        try:
            puntos, contexto, errores, liquidacion = datos_curvas(fecha, marca_actual)
        except Exception as e:                       # sin conexión, sin feriados, etc.
            st.error(f"No se pudieron armar las curvas: {e}")
            return
        st.caption(f"Liquidación {liquidacion:%d/%m/%Y} · actualizado {pd.Timestamp.now():%H:%M:%S}"
                   + (f" · se actualiza {refresco.lower()}" if segundos else ""))
        disponibles = [c for c in NOMBRES_CURVA if puntos.get(c)]
        if not disponibles:
            st.warning("No hay bonos con precio para armar curvas.")
            return
        if st.session_state.get("curva_elegida") not in disponibles:
            st.session_state["curva_elegida"] = disponibles[0]
        c = st.segmented_control("Curva", disponibles, format_func=NOMBRES_CURVA.get, key="curva_elegida") or disponibles[0]

        # Mercado y, encima, lo que cargó el usuario en la tabla (precio o tasa de un bono)
        de_mercado = sorted(puntos[c], key=lambda p: p["x"])
        cambios = st.session_state.get("cambios_curva", {})
        filas, avisos = [], []
        for p in de_mercado:
            fila = dict(p, editado=None)
            cambio = cambios.get((c, p["ticker"]))
            if cambio:
                try:
                    fila.update(_recalcular(p["ticker"], c, cambio, p["precio"]), editado=cambio[0])
                except (ValueError, ArithmeticError, TypeError) as e:
                    avisos.append(f"{p['ticker']}: {e}")
            filas.append(fila)

        fig = go.Figure()
        editados = [f for f in filas if f["editado"]]
        if editados:                                        # dónde estaban a precio de mercado
            originales = [p for p in de_mercado if (c, p["ticker"]) in cambios]
            fig.add_trace(go.Scatter(x=[p["x"] / 365 for p in originales], y=[p["tea"] for p in originales],
                                     mode="markers", name="A precio de mercado", hoverinfo="skip",
                                     marker=dict(size=9, color="rgba(0,0,0,0)", line=dict(color=GRIS, width=1.5))))
        xs = [f["x"] / 365 for f in filas]
        fig.add_trace(go.Scatter(x=xs, y=[f["tea"] for f in filas], mode="markers+text", name=NOMBRES_CURVA[c],
                                 text=[f["ticker"] for f in filas], textposition="top center", textfont=dict(size=10, color=GRIS),
                                 marker=dict(size=[12 if f["editado"] else 9 for f in filas],
                                             color=[ORO if f["editado"] else COLORES[c] for f in filas],
                                             line=dict(color=TEXTO, width=0.6),
                                             symbol=["diamond" if f["editado"] else "circle" for f in filas]),
                                 hovertemplate="%{text}<br>Duration %{x:.2f} años<br>TEA %{y:.2%}<extra></extra>"))
        if len(de_mercado) >= 3:                           # la curva ajustada es la de mercado: la referencia
            try:
                xs_mercado = [p["x"] / 365 for p in de_mercado]
                ajuste = calc_curva.ajustar_log([(x, p["tea"]) for x, p in zip(xs_mercado, de_mercado) if x > 0])
                grilla = [min(xs_mercado) + i * (max(xs_mercado) - min(xs_mercado)) / 60 for i in range(61)]
                fig.add_trace(go.Scatter(x=grilla, y=[calc_curva.tea_teorica(ajuste, x) for x in grilla], mode="lines",
                                         name=f"Curva de mercado (R² {ajuste['r2']:.2f})", hoverinfo="skip",
                                         line=dict(color=GRIS, dash="dot")))
            except Exception:
                pass
        estilo_grafico(fig, 480, xaxis_title="Duration (años)", yaxis_title="TEA", yaxis_tickformat=".1%")
        with st.container(border=True):
            st.plotly_chart(fig, width="stretch", theme=None)

        # La tabla se puede editar: precio, TEA o TNA de cualquier bono; lo demás se recalcula
        tabla = pd.DataFrame([{"Ticker": f["ticker"], "Precio": f["precio"], "TEA (%)": f["tea"] * 100,
                               "TNA (%)": f["tna"] * 100 if f.get("tna") is not None else None,
                               "Duration (años)": f["x"] / 365,
                               "": {"precio": "✎ precio", "tea": "✎ TEA", "tna": "✎ TNA"}.get(f["editado"], "")}
                              for f in filas])
        clave = f"editor_{c}_{st.session_state.get('version_editor', 0)}"
        st.data_editor(tabla, key=clave, hide_index=True, width="stretch", disabled=["Ticker", "Duration (años)", ""],
                       on_change=_guardar_edicion, args=(clave, c, filas),
                       column_config={"Precio": st.column_config.NumberColumn(format="%.2f", min_value=0.0001),
                                      "TEA (%)": st.column_config.NumberColumn(format="%.2f"),
                                      "TNA (%)": st.column_config.NumberColumn(format="%.2f", help=AYUDA_TNA.get(c, "")),
                                      "Duration (años)": st.column_config.NumberColumn(format="%.2f"),
                                      "": st.column_config.TextColumn(width="small")})
        col1, col2 = st.columns([3, 1])
        col1.caption("Escribí un precio, una TEA o una TNA en la tabla y se recalcula el resto del bono y su punto en "
                     "la curva (en dorado; el círculo gris es su lugar a precio de mercado, y la línea punteada, la "
                     "curva de mercado). Borrar la celda vuelve al mercado.")
        if editados and col2.button("Volver todo a mercado", width="stretch"):
            st.session_state["cambios_curva"] = {k: v for k, v in cambios.items() if k[0] != c}
            st.session_state["version_editor"] = st.session_state.get("version_editor", 0) + 1
            st.rerun(scope="fragment")
        for aviso in avisos:
            st.warning(f"No se pudo recalcular {aviso}")
        if c == "tasa_fija":
            with st.expander("Curva teórica de tasa fija (a precio de mercado): desvío de cada bono contra la curva y sus vecinos"):
                mostrar(salida_herramienta("curva_tf", marca_actual, fecha=fecha.isoformat() if fecha else None))
        if errores:
            with st.expander(f"{len(errores)} bonos sin precio o sin cálculo"):
                st.write("\n".join(f"- {e}" for e in errores))

    panel_curvas()


# ---------- Bono ----------

@st.cache_data(ttl=60, show_spinner=False)
def precio_de_mercado(ticker: str, familia: str, fecha: date | None, _marca: int) -> float:
    return mercado.precio(ticker + ("D" if familia == "hard_dollar" else ""), fecha)[0]


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
        calc = metricas.calculadora(ficha, liquidacion, operacion)
        try:
            precio_mkt = precio_de_mercado(ticker, ficha["familia"], fecha_precios, marca)
            m_mercado = calc(precio_mkt)
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
               + (f" · precio de mercado {precio_mkt:,.2f}" if precio_mkt else " · sin precio de mercado"))
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
    if ficha["familia"] == "tamar_capitalizable":
        st.caption("El pago final usa la TAMAR ya publicada y, para los días que faltan, la última TAMAR. Para otros "
                   "supuestos, la sección Proyecciones.")
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
    from carga_datos import fichas_documentos as fd
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
    col2.caption("Para aprobar: python -m carga_datos.fichas_documentos aprobar <TICKER>, o pedíselo al agente.")


# ---------- Carteras ----------

if seccion == "Carteras":
    carteras_panel.seccion(fecha, marca, estilo_grafico, {"series": SERIES, "texto": TEXTO, "gris": GRIS,
                                                         "superficie": SUPERFICIE, "grilla": GRILLA,
                                                         "esmeralda": ESMERALDA})
