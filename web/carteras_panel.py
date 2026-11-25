"""Sección Carteras del panel: crear y editar carteras, verlas valuadas y preguntarle a la IA sobre ellas.

Usa el módulo carteras/ (lectura, guardado y valuación) y el mismo sistema de agentes que main.py: el panel no
calcula nada propio. Las carteras viven en datos/carteras/ (fuera del repo).
"""
import hmac
import inspect
import time
import uuid
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import config
from carteras import excel, valuar

MONEDAS = {"pesos": "Pesos", "mep": "Dólar MEP", "ccl": "Dólar CCL"}
NUEVA = "➕ Nueva cartera"
NOMBRES_SUPUESTOS = {"inflacion": "Inflación (CER)", "tamar": "TAMAR", "dolar_oficial": "Dólar oficial (A3500)",
                     "mep": "Dólar MEP", "ccl": "Dólar CCL"}


# ---------- Acceso ----------

def acceso() -> bool:
    """Las carteras son datos de clientes. Con el panel compartido (PANEL_CLAVE) hace falta CARTERAS_CLAVE: sin ella la
    sección queda cerrada; con ella se pide una vez por sesión. Sin PANEL_CLAVE (uso en tu compu) abre directo."""
    if not config.PANEL_CLAVE and not config.CARTERAS_CLAVE:
        return True
    if st.session_state.get("carteras_autenticado"):
        return True
    if not config.CARTERAS_CLAVE:
        st.info("La sección Carteras está cerrada porque el panel tiene contraseña para compartir (PANEL_CLAVE) y "
                "las carteras son datos de clientes. Para abrirla, agregá CARTERAS_CLAVE=<otra contraseña> al .env y "
                "reiniciá el panel.")
        return False
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro, st.form("acceso_carteras"):
        intento = st.text_input("Contraseña de carteras", type="password")
        if st.form_submit_button("Entrar", width="stretch"):
            if hmac.compare_digest(intento.encode(), config.CARTERAS_CLAVE.encode()):
                st.session_state["carteras_autenticado"] = True
                st.rerun()
            time.sleep(1.5)
            st.error("Contraseña incorrecta.")
    return False


# ---------- Datos ----------

def _version(nombre: str) -> float:
    """Cambia cuando se edita el archivo: invalida la caché de la valuación."""
    try:
        return excel.ruta(nombre).stat().st_mtime
    except ValueError:
        return 0.0


@st.cache_data(ttl=60, show_spinner="Valuando la cartera…")
def valuacion(nombre: str, moneda: str, fecha: date | None, marca: int, version: float) -> dict:
    return valuar.valuar(excel.leer(nombre), moneda, fecha)


@st.cache_resource(show_spinner="Preparando los agentes…")
def grafo():
    from graph.builder import construir_grafo
    return construir_grafo()


def _opciones_supuesto(variable: str) -> list[str]:
    from tools import proyeccion_cer, proyecciones
    base = {"inflacion": ["rem", "breakeven", "mensual:2%"], "tamar": ["rem", "actual", "tna:30%"],
            "dolar_oficial": ["rem", "breakeven", "mensual:1.5%"], "mep": ["rem", "mensual:1.5%"],
            "ccl": ["rem", "mensual:1.5%"]}[variable]
    try:
        nombres = proyeccion_cer.escenarios() if variable == "inflacion" else \
            proyecciones.escenarios({"dolar_oficial": "oficial"}.get(variable, variable))
    except Exception:
        nombres = {}
    return base + [f"escenario:{n}" for n in nombres]


# ---------- Vistas ----------

def _propia(f: dict) -> str | None:
    if f["tir_propia"] is None:
        return None
    return f"{f['referencia']} + {f['tir_propia']:.2%}" if f["referencia"] else f"{f['tir_propia']:.2%}"


def _indicador(titulo: str, valor: str, paleta: dict, ayuda: str = ""):
    """Tarjeta de indicador que no corta el número (st.metric lo trunca si la columna es angosta)."""
    st.markdown(f'''<div style="background:{paleta['superficie']};border:1px solid {paleta['grilla']};border-radius:10px;
        padding:12px 18px;margin-bottom:10px" title="{ayuda}">
        <div style="color:{paleta['gris']};font-size:0.85rem">{titulo}</div>
        <div style="color:{paleta['texto']};font-size:1.7rem;font-weight:600;font-variant-numeric:tabular-nums;
             white-space:nowrap">{valor}</div></div>''', unsafe_allow_html=True)


def _encabezado(nombre: str, detalle: str, paleta: dict):
    st.markdown(f'''<div style="font-size:2.3rem;font-weight:700;line-height:1.15;color:{paleta['texto']}">{nombre}</div>
        <div style="color:{paleta['gris']};font-size:0.9rem;margin-bottom:14px">{detalle}</div>''',
                unsafe_allow_html=True)


COLUMNAS_TABLA = {"Tir Nominal en base a proyeccion": st.column_config.NumberColumn(format="percent"),
                  "Nominales": st.column_config.NumberColumn(format="localized"),
                  "Precio": st.column_config.NumberColumn(format="%.2f"),
                  "Total": st.column_config.NumberColumn(format="localized"),
                  "% Cartera": st.column_config.NumberColumn(format="percent"),
                  "Duration Activo": st.column_config.NumberColumn(format="%.2f")}
EDITABLES = ["Tipo Activo", "Descripcion", "Ticker", "Nominales"]
AYUDA_PONDERADO = ("Promedio ponderado por monto de la renta fija, la liquidez, los créditos y los pasivos (la liquidez "
                   "sin colocar rinde 0 con duration 0). La renta variable no pondera.")


def _filas_tabla(cartera, v: dict | None) -> pd.DataFrame:
    """Una fila por posición de la cartera (también las que no se pudieron valuar), con lo calculado al lado."""
    por_ticker = {f["ticker"]: f for f in (v or {}).get("filas", [])}
    filas = []
    for p in cartera.posiciones:
        f = por_ticker.get(p.ticker)
        filas.append({"Tipo Activo": p.tipo or (f["tipo"] if f else ""),
                      "Descripcion": p.descripcion or (f["descripcion"] if f else ""), "Ticker": p.ticker,
                      "Tir Spread/Nominal": _propia(f) if f else None,
                      "Tir Nominal en base a proyeccion": f["tir_proyectada"] if f else None,
                      "Nominales": float(p.nominales), "Precio": f["precio"] if f else None,
                      "Total": f["total"] if f else None, "% Cartera": f["peso"] if f else None,
                      "Duration Activo": f["duration"] if f else None})
    return pd.DataFrame(filas, columns=excel.COLUMNAS).astype({"Tipo Activo": str, "Descripcion": str, "Ticker": str})


def _filas_liquidez(v: dict | None) -> pd.DataFrame:
    filas = [{"Tipo Activo": f["tipo"], "Descripcion": f["descripcion"], "Ticker": "",
              "Tir Spread/Nominal": f"{f['tir_propia']:.2%}", "Tir Nominal en base a proyeccion": f["tir_proyectada"],
              "Nominales": f["nominales"], "Precio": None, "Total": f["total"], "% Cartera": f["peso"],
              "Duration Activo": f["duration"]} for f in (v or {}).get("filas", []) if f.get("liquidez")]
    return pd.DataFrame(filas, columns=excel.COLUMNAS)


def _tabla_simple(filas: list[dict], columnas: dict, alto: int | None = None):
    """Un cuadro de composición: columnas = {clave del dato: (título, formato o None)}."""
    df = pd.DataFrame([{titulo: x.get(clave) for clave, (titulo, _) in columnas.items()} for x in filas])
    config_col = {titulo: st.column_config.NumberColumn(format=formato)
                  for _, (titulo, formato) in columnas.items() if formato}
    st.dataframe(df, hide_index=True, width="stretch", column_config=config_col, **({"height": alto} if alto else {}))


def _cuadros(v: dict, estilo, paleta: dict):
    c = v["cuadros"]
    st.markdown(f"#### Composición ({MONEDAS[v['moneda']].lower()})")
    izquierda, derecha = st.columns(2)
    with izquierda:
        st.markdown("**Por clase de activo**")
        filas = [{"categoria": x["categoria"] if x["subclase"] is None else "",
                  "subclase": "" if x["subclase"] is None else x["subclase"], "total": x["total"], "peso": x["peso"]}
                 for x in c["categoria"]]
        _tabla_simple(filas, {"categoria": ("Categoría", None), "subclase": ("Subclase", None),
                              "total": ("Total", "localized"), "peso": ("% Cartera", "percent")})
    with derecha:
        st.markdown("**Por moneda**")
        _tabla_simple(c["moneda"], {"moneda": ("Moneda", None), "total": ("Total", "localized"),
                                    "peso": ("% Cartera", "percent")})
        series = paleta["series"]
        fig = go.Figure(go.Pie(labels=[x["moneda"] for x in c["moneda"]], values=[max(x["total"], 0) for x in c["moneda"]],
                               hole=0.55, sort=False, textinfo="percent",
                               marker=dict(colors=[series[i % len(series)] for i in range(len(c["moneda"]))]),
                               hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>"))
        estilo(fig, 260)
        fig.update_layout(margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, width="stretch", theme=None)
    st.markdown("**Clase de activo y moneda**")
    columnas = {"categoria": ("Categoría", None), "subclase": ("Subclase", None)}
    columnas |= {m: (m, "localized") for m in c["monedas"]}
    columnas |= {"total": ("Total", "localized"), "peso": ("% Cartera", "percent")}
    _tabla_simple([{k: (x[k] if x.get(k) else None) if k in c["monedas"] else x[k] for k in columnas}
                   for x in c["clase_moneda"]], columnas)
    st.markdown("**Emisores**")
    _tabla_simple(c["emisor"], {"emisor": ("Emisor", None), "total": ("Total", "localized"),
                                "peso": ("% Cartera", "percent")})


def _cobros(v: dict):
    st.markdown(f"#### Cobros y vencimientos de los próximos {v['dias_cobros']} días")
    if not v["cobros"]:
        st.caption("Sin cobros de cupón, amortizaciones ni vencimientos en el período.")
        return
    vencen = [x for x in v["cobros"] if x["concepto"].startswith("Vencimiento")]
    for x in vencen:
        st.warning(f"{x['ticker']}: {x['concepto'].lower()} el {x['fecha']:%d/%m/%Y} "
                   f"({x['moneda_pago']} {abs(x['monto']):,.2f}).")
    _tabla_simple([x | {"fecha_txt": f"{x['fecha']:%d/%m/%Y}"} for x in v["cobros"]],
                  {"fecha_txt": ("Fecha", None), "ticker": ("Ticker", None), "concepto": ("Concepto", None),
                   "moneda_pago": ("Moneda", None), "cupon": ("Renta", "localized"),
                   "amortizacion": ("Amortización", "localized"), "monto": ("Monto", "localized"),
                   "monto_vista": (f"En {MONEDAS[v['moneda']].lower()}", "localized"), "nota": ("Nota", None)})
    st.caption("Montos para la tenencia de la cartera. CER y dollar linked: estimados con el CER o el A3500 de hoy.")


def _graficos(v: dict, estilo, paleta: dict, donde):
    series = paleta["series"]
    composicion = pd.DataFrame(v["filas"]).groupby("subclase")["total"].sum().clip(lower=0).sort_values(ascending=False)
    fig = go.Figure(go.Pie(labels=composicion.index, values=composicion.values, hole=0.55, sort=False,
                           marker=dict(colors=[series[i % len(series)] for i in range(len(composicion))]),
                           textinfo="percent", hovertemplate="%{label}: %{value:,.0f} (%{percent})<extra></extra>"))
    estilo(fig, 330, title=dict(text="Composición por clase de activo", font=dict(color=paleta["texto"], size=15)))
    with donde.container(border=True):
        st.plotly_chart(fig, width="stretch", theme=None)


def _dispersion(v: dict, estilo, paleta: dict):
    rf = [f for f in v["filas"] if f["renta_fija"] and f["tir_proyectada"] is not None]
    if not rf:
        return
    fig = go.Figure(go.Scatter(
        x=[f["duration"] for f in rf], y=[f["tir_proyectada"] for f in rf], mode="markers+text",
        text=[f["ticker"] for f in rf], textposition="top center",
        marker=dict(size=[12 + 40 * (f["peso"] or 0) ** 0.5 for f in rf], color=paleta["series"][0], opacity=0.8),
        customdata=[f["peso"] for f in rf],
        hovertemplate="%{text}: TIR %{y:.2%}, duration %{x:.2f}, %{customdata:.1%} de la cartera<extra></extra>"))
    estilo(fig, 360, title=dict(text="TIR nominal proyectada contra duration (tamaño: % de la cartera)",
                                font=dict(color=paleta["texto"], size=15)),
           yaxis_tickformat=".0%", xaxis_title="Duration (años)")
    with st.container(border=True):
        st.plotly_chart(fig, width="stretch", theme=None)


def _supuestos_editables(cartera, clave: str) -> dict:
    st.markdown("**Supuestos para la TIR nominal proyectada.** Elegí una opción o escribí otra (por ejemplo "
                "`camino:2026-12=2%;2027=22%;resto=1.5%`).")
    nuevos = {}
    acepta_nuevas = "accept_new_options" in inspect.signature(st.selectbox).parameters
    for col, variable in zip(st.columns(len(excel.SUPUESTOS)), excel.SUPUESTOS):
        opciones = _opciones_supuesto(variable)
        actual = cartera.supuestos.get(variable) or "rem"
        if actual not in opciones:
            opciones = [actual] + opciones
        extra = {"accept_new_options": True} if acepta_nuevas else {}
        nuevos[variable] = col.selectbox(NOMBRES_SUPUESTOS[variable], opciones, index=opciones.index(actual),
                                         key=f"sup_{clave}_{variable}", **extra)
    return nuevos


def _liquidez_de(df: pd.DataFrame | None) -> list:
    lista = []
    for f in ([] if df is None else df.to_dict("records")):
        if not f.get("Tipo") or pd.isna(f.get("Monto")):
            continue
        tasa = f.get("Tasa")
        venc = f.get("Vencimiento")
        lista.append(excel.Liquidez(f["Tipo"], f.get("Moneda") or "pesos", f["Monto"],
                                    str(f.get("Descripcion") or "").strip() or None,
                                    None if tasa is None or pd.isna(tasa) else tasa / 100,
                                    None if venc is None or pd.isna(venc) else pd.Timestamp(venc).date()))
    return lista


def _guardar(editado: pd.DataFrame, automaticos: dict, nombre_nuevo: str, supuestos: dict, nombre: str | None,
             liquidez: pd.DataFrame | None = None) -> bool:
    """Guarda lo editado. Tipo y descripción se guardan solo si los cambiaste (si no, siguen saliendo de la ficha)."""
    posiciones = []
    for f in editado.to_dict("records"):
        ticker = str(f.get("Ticker") or "").strip().upper()
        if ticker in ("", "NAN", "NONE"):
            continue
        tipo_auto, desc_auto = automaticos.get(ticker, (None, None))
        tipo = str(f.get("Tipo Activo") or "").strip()
        desc = str(f.get("Descripcion") or "").strip()
        posiciones.append(excel.Posicion(ticker, f.get("Nominales"),
                                         tipo if tipo and tipo not in ("nan", tipo_auto) else None,
                                         desc if desc and desc not in ("nan", desc_auto) else None))
    try:
        excel.guardar(excel.Cartera(nombre_nuevo, posiciones, supuestos, _liquidez_de(liquidez)), nombre_anterior=nombre)
    except PermissionError:
        st.error("No se pudo escribir el archivo: cerralo en Excel y volvé a guardar.")
        return False
    except ValueError as e:
        st.error(str(e))
        return False
    st.session_state["cartera_pendiente"] = excel.validar_nombre(nombre_nuevo)
    st.toast("Cartera guardada")
    return True


def ver_cartera(nombre: str | None, moneda: str, fecha: date | None, marca: int, estilo, paleta: dict):
    """La cartera en una sola vista. Con "Editar", la misma tabla pasa a ser editable (ticker, nominales, tipo y
    descripción), junto con los supuestos y el nombre. nombre=None: cartera nueva (directo en edición)."""
    clave_edicion = f"editando_{nombre or NUEVA}"
    editando = nombre is None or st.session_state.get(clave_edicion, False)
    if nombre:
        try:
            cartera = excel.leer(nombre)
        except ValueError as e:
            st.error(str(e))
            return
    else:
        cartera = excel.Cartera("", [], {})
    v, error = None, None
    if nombre:
        try:
            v = valuacion(nombre, moneda, fecha, marca, _version(nombre))
        except Exception as e:
            error = str(e).splitlines()[0]

    # Encabezado: nombre grande y el botón de editar (o guardar / cancelar)
    izquierda, derecha = st.columns([5, 2], vertical_alignment="center")
    with izquierda:
        detalle = (f"Valuada en {MONEDAS[moneda].lower()} al {v['fecha']:%d/%m/%Y}" if v else
                   "Cartera nueva: cargá los activos y guardala" if not nombre else "")
        _encabezado(nombre or "Nueva cartera", detalle, paleta)
    if nombre and not editando:
        if derecha.button("✏️ Editar", width="stretch"):
            st.session_state[clave_edicion] = True
            st.rerun()

    if error:
        st.error(f"No se pudo valuar la cartera: {error}")

    # Indicadores, uno debajo del otro: patrimonio, TIR proyectada y duration
    if v and not editando:
        t = v["totales"]
        unidad = {"pesos": "$", "mep": "US$ MEP", "ccl": "US$ CCL"}[moneda]
        indicadores, grafico = st.columns([2, 3])
        with indicadores:
            _indicador("Patrimonio", f"{unidad} {t['total']:,.2f}", paleta)
            _indicador("TIR nominal proyectada", f"{t['tir_proyectada_rf']:.2%}" if t["tir_proyectada_rf"] is not None
                       else "–", paleta, AYUDA_PONDERADO)
            _indicador("Duration", f"{t['duration_rf']:.2f} años" if t["duration_rf"] is not None else "–", paleta,
                       AYUDA_PONDERADO)
        if v["filas"]:
            _graficos(v, estilo, paleta, grafico)

    tabla = _filas_tabla(cartera, v)
    if not editando:
        completa = pd.concat([tabla, _filas_liquidez(v)], ignore_index=True) if v and any(
            f.get("liquidez") for f in v["filas"]) else tabla
        st.dataframe(completa, hide_index=True, width="stretch", column_config=COLUMNAS_TABLA)
        if v:
            st.caption(v["nota_valuacion"] + " Calculadora de Finianz.")
            for aviso in v["avisos"]:
                st.warning(aviso)
            _cobros(v)
            _cuadros(v, estilo, paleta)
            _dispersion(v, estilo, paleta)
            if v["supuestos"]:
                with st.expander("Supuestos de la proyección"):
                    for variable, descripcion in v["supuestos"].items():
                        st.markdown(f"**{NOMBRES_SUPUESTOS.get(variable, variable)}:** {descripcion}")
            if st.button("Preparar Excel de la valuación"):
                archivo = excel.guardar_valuacion(v)
                st.download_button("Descargar Excel", archivo.read_bytes(), file_name=archivo.name,
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        return

    # Edición sobre la misma tabla: lo calculado queda fijo y se actualiza al guardar
    st.caption("Editá ticker y nominales (en acciones y CEDEARs, la cantidad); tipo y descripción son opcionales. "
               "Para sumar un activo usá la fila vacía del final; para borrarlo, seleccioná la fila y tocá el tacho. "
               "Las columnas calculadas se actualizan al guardar.")
    automaticos = {f["ticker"]: (f["tipo"], f["descripcion"]) for f in (v or {}).get("filas", [])}
    editado = st.data_editor(
        tabla, num_rows="dynamic", hide_index=True, width="stretch", key=f"editor_{nombre or NUEVA}",
        disabled=[c for c in excel.COLUMNAS if c not in EDITABLES],
        column_config=COLUMNAS_TABLA | {
            "Ticker": st.column_config.TextColumn(required=True, help="Ej.: TZXD7, AL30, GD30, GGAL"),
            "Nominales": st.column_config.NumberColumn(required=True, min_value=0, format="localized")})
    st.markdown("**Liquidez, pasivos y créditos.** Monto en su moneda y siempre positivo (los pasivos se restan solos). "
                "Tasa: TNA, solo para money market, cauciones, plazos fijos, créditos y pasivos; la liquidez sin colocar "
                "rinde 0.")
    liquidez = pd.DataFrame([{"Tipo": x.tipo, "Descripcion": x.descripcion or "", "Moneda": x.moneda, "Monto": x.monto,
                              "Tasa": x.tasa * 100 if x.tasa is not None else None, "Vencimiento": x.vencimiento}
                             for x in cartera.liquidez], columns=excel.COLUMNAS_LIQUIDEZ)
    liquidez = liquidez.astype({"Descripcion": str, "Monto": float, "Tasa": float})
    liquidez["Vencimiento"] = pd.to_datetime(liquidez["Vencimiento"])
    liquidez_editada = st.data_editor(
        liquidez, num_rows="dynamic", hide_index=True, width="stretch", key=f"liquidez_{nombre or NUEVA}",
        column_config={"Tipo": st.column_config.SelectboxColumn(options=list(excel.TIPOS_LIQUIDEZ), required=True),
                       "Moneda": st.column_config.SelectboxColumn(options=list(excel.MONEDAS_LIQUIDEZ), required=True,
                                                                  default="pesos"),
                       "Monto": st.column_config.NumberColumn(required=True, min_value=0, format="localized"),
                       "Tasa": st.column_config.NumberColumn("Tasa (TNA %)", min_value=0, format="%.2f%%"),
                       "Vencimiento": st.column_config.DateColumn(format="DD/MM/YYYY")})
    supuestos = _supuestos_editables(cartera, nombre or NUEVA)
    col_nombre, col_guardar, col_cancelar, col_archivar = st.columns([3, 1, 1, 1], vertical_alignment="bottom")
    nombre_nuevo = col_nombre.text_input("Nombre de la cartera", value=nombre or "", placeholder="Ej.: Pérez Juan")
    if col_guardar.button("Guardar", width="stretch", type="primary"):
        if _guardar(editado, automaticos, nombre_nuevo, supuestos, nombre, liquidez_editada):
            st.session_state.pop(clave_edicion, None)
            st.rerun()
    if nombre:
        if col_cancelar.button("Cancelar", width="stretch"):
            st.session_state.pop(clave_edicion, None)
            st.session_state.pop(f"editor_{nombre}", None)
            st.rerun()
        with col_archivar.popover("Archivar", width="stretch"):
            st.caption("La saca de la lista sin borrarla: queda en datos/carteras/anteriores/.")
            if st.button("Confirmar", key="archivar"):
                excel.archivar(nombre)
                st.session_state.pop(clave_edicion, None)
                st.session_state["cartera_pendiente"] = None
                st.rerun()


def preguntar(nombre: str, moneda: str):
    """Chat con el sistema de agentes sobre una cartera. Oculto por ahora (decisión de Agustin, 25/11/2026)."""
    if not config.GEMINI_API_KEY:
        st.error("Falta GEMINI_API_KEY en el .env.")
        return
    chats = st.session_state.setdefault("chats_carteras", {})
    chat = chats.setdefault(nombre, {"hilo": str(uuid.uuid4()), "mensajes": []})
    if st.button("Nueva conversación"):
        chats[nombre] = {"hilo": str(uuid.uuid4()), "mensajes": []}
        st.rerun()
    for rol, texto in chat["mensajes"]:
        st.chat_message(rol).markdown(texto)
    pregunta = st.chat_input(f"Preguntá sobre la cartera {nombre}…")
    if pregunta:
        st.chat_message("user").markdown(pregunta)
        chat["mensajes"].append(("user", pregunta))
        contexto = (f"[Pregunta sobre la cartera de cliente \"{nombre}\". Para verla usá ver_cartera con "
                    f"nombre=\"{nombre}\" y moneda=\"{moneda}\" (u otra moneda si la pregunta la pide).] ")
        from main import preguntar as preguntar_grafo
        with st.chat_message("assistant"), st.spinner("Pensando…"):
            respuesta = preguntar_grafo(grafo(), contexto + pregunta, chat["hilo"])
            st.markdown(respuesta)
        chat["mensajes"].append(("assistant", respuesta))


MOSTRAR_CHAT = False      # el chat con la IA sobre la cartera queda oculto por ahora


def seccion(fecha: date | None, marca: int, estilo, paleta: dict):
    if not acceso():
        return
    if "cartera_pendiente" in st.session_state:
        pendiente = st.session_state.pop("cartera_pendiente")
        st.session_state["cartera_sel"] = pendiente or NUEVA
    opciones = excel.listar() + [NUEVA]
    if st.session_state.get("cartera_sel") not in opciones:
        st.session_state["cartera_sel"] = opciones[0]
    col1, col2, _ = st.columns([2, 3, 2])
    elegida = col1.selectbox("Cartera", opciones, key="cartera_sel")
    moneda = col2.radio("Ver en", list(MONEDAS), format_func=MONEDAS.get, horizontal=True, key="moneda_carteras")
    ver_cartera(None if elegida == NUEVA else elegida, moneda, fecha, marca, estilo, paleta)
    if MOSTRAR_CHAT and elegida != NUEVA:
        st.divider()
        preguntar(elegida, moneda)
