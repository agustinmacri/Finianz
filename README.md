# Finianz

Sistema multiagente en Python para asistir a un portfolio manager o asesor financiero en Argentina. Los agentes consultan datos oficiales y noticias, los analizan y responden en lenguaje natural, citando siempre la fuente y la fecha de cada dato.

Construido con [LangGraph](https://langchain-ai.github.io/langgraph/) y modelos Gemini de Google. Todas las fuentes de datos son gratuitas.

## Qué puede hacer hoy

| Agente | Qué hace | Fuentes |
|---|---|---|
| **Macro** | Busca y analiza indicadores: inflación, expectativas del REM, reservas, tipo de cambio, tasas, CER, UVA, actividad. De EE. UU.: CPI, PCE, empleo, PBI, tasa de la Fed, bonos del Tesoro. Precios de acciones y CEDEARs. Calcula acumulados, tasas reales y proyecciones. | API del BCRA, Series de Tiempo de datos.gob.ar, FRED, API de PPI |
| **Renta fija** | Calculadora propia de bonos: tasa fija, CER, TAMAR, duales (con las dos formas de pago), dollar linked y hard dollar. Breakevens entre curvas (inflación, devaluación, tipo de cambio real, brecha, TAMAR) y comparación con el REM. Proyecciones de rendimiento con el REM, el breakeven o escenarios propios de inflación, TAMAR, dólar oficial, MEP y CCL. Carteras de clientes: valuación con tasa propia, TIR nominal proyectada, % de la cartera y duration, en pesos o en dólares MEP/CCL. | API de PPI (precios), BCRA (CER, TAMAR, A3500), REM, FRED (Treasuries) |
| **Noticias** | Busca noticias sobre un tema y resume los titulares del día, con su implicancia para el mercado. | Google News (RSS), feeds de Ámbito |

Los agentes consultan además un **calendario de feriados** de Argentina y EE. UU. (nacionales, bancos, BYMA, NYSE y bonos del Tesoro) desde 2016 hasta el año próximo, y calculan días hábiles por mercado (por ejemplo, la liquidación T+2).

También consultan un **calendario de publicaciones** con las fechas de los datos oficiales que sigue el proyecto (IPC, EMAE, salarios y balanza de pagos del INDEC; recaudación de ARCA; CPI, empleo, PCE, PBI, ISM y otras de EE. UU.), para saber cuándo sale el próximo dato. Las del BCRA, el Tesoro y la Fed se suman en el próximo paso.

Un **router** decide qué agente o agentes responden cada pregunta. Si hacen falta varios, corren en paralelo y sus respuestas se integran en una sola.

Ejemplos de preguntas:

- *¿Cuál fue la última inflación y qué espera el REM?*
- *¿Cuánto da la inflación acumulada en el año?*
- *¿Cuál fue el último dato de inflación en EE. UU. y cuándo sale el próximo?*
- *¿Qué pasó hoy en el mercado?*
- *¿Cómo viene la inflación y qué se dice de la próxima licitación?*
- *¿Cuánto rinde el TXMJ8? ¿Qué pata paga con el REM?*
- *¿Qué inflación descuentan los bonos CER contra las Lecap?*
- *Mostrame la cartera de Pérez en dólares MEP.*

## Cómo funciona

```
                       ┌→ agente_macro ──────┐
    pregunta → router ─┼→ agente_renta_fija ─┼→ responder → respuesta
                       └→ agente_noticias ───┘   (saludos: directo a responder)
```

- **Router:** una sola llamada al modelo, con salida estructurada. Elige uno o varios agentes (`macro`, `renta_fija`, `noticias`), o ninguno para saludos y preguntas sobre la conversación.
- **Agentes:** cada uno es un subgrafo con su propio prompt y **solo sus herramientas**. Iteran entre el modelo y las herramientas hasta tener la respuesta. El de renta fija trabaja solo con lo que está en el sistema (calculadoras, base propia, precios); lo que le falta, o un supuesto macro, se lo pide al agente macro.
- **Responder:** si respondió un solo agente, devuelve su informe tal cual, sin otra llamada al modelo. Si respondieron varios, los integra.
- **Memoria:** la conversación guarda solo las preguntas y las respuestas finales. Las consultas internas de cada agente no se acumulan, y así el contexto se mantiene chico.

Principios de diseño:

- **De afuera, solo datos.** Las fuentes externas aportan datos (precios, series, fechas); todos los cálculos los hace el proyecto, para no depender de cálculos ajenos. Las excepciones se deciden explícitamente.
- **No todo es un agente.** Los cálculos con una forma correcta (como la inflación acumulada) se hacen en código, no los resuelve el modelo.
- **Los datos nunca pasan por el modelo para calcular.** El código Python que escribe el agente trae los datos directamente de las APIs.
- **Siempre con fecha.** Cada respuesta indica la fecha del último dato disponible.

## Estructura del proyecto

```
Finianz/
├── main.py              # chat por terminal
├── actualizar.py        # actualiza las bases locales (feriados, publicaciones, CER, precios)
├── config.py            # configuración central (lee el .env)
├── graph/               # orquestación con LangGraph
│   ├── builder.py       # grafo principal: router + agentes + responder
│   ├── router.py        # decide qué agente responde
│   ├── agente.py        # fábrica de agentes (loop modelo ↔ herramientas)
│   ├── delegacion.py    # consultar_agente_macro: renta fija le pide datos o supuestos al macro
│   ├── responder.py     # respuesta final: directa o síntesis
│   ├── nodes.py         # modelos con respaldo y nodo "modelo"
│   ├── state.py         # estados del grafo
│   └── errores.py       # errores temporales y reintentos
├── tools/               # lo que ven los agentes
│   ├── datos_macro.py   # buscar_indicador, consultar_bcra, consultar_serie, inflacion_acumulada,
│   │                    # inflacion_anualizada,
│   │                    # consultar_fred, buscar_serie_fred
│   ├── noticias.py      # buscar_noticias, titulares_recientes
│   ├── precios.py       # consultar_precio (PPI)
│   ├── bonos.py         # calcular_bono (calculadora propia)
│   ├── breakevens.py    # calcular_breakevens (entre curvas y contra el REM)
│   ├── proyeccion_cer.py   # proyectar_cer (CER con REM, breakeven o escenarios)
│   ├── proyecciones.py  # proyectar_tamar y proyectar_dolar (oficial, MEP, CCL) con escenarios
│   ├── caminos.py       # tabla del camino usado contra el breakeven y el REM (mes a mes y por año)
│   ├── base_propia.py   # consultar_base: datos guardados (CER, TAMAR, A3500, inflación, REM), sin API
│   ├── curvas.py        # curva_tasa_fija: curva teórica de Lecap/Boncap
│   ├── lector_fichas.py # leer_documento_bonos: borradores de fichas desde un documento
│   ├── guardia.py       # límites de seguridad del código que escribe el agente
│   ├── calendario.py    # consultar_feriados, calcular_dia_habil, consultar_publicaciones
│   └── python_exec.py   # ejecutar_python, con acceso a los datos
├── renta_fija/          # el motor de bonos y letras: solo cálculos (los datos los pide a fuentes_datos; no sabe del agente ni del panel)
│   ├── fichas/          # fichas técnicas (cer.toml, cer_cupon.toml, tasa_fija.toml, tamar.toml, hard_dollar.toml, dolar_linked.toml) y prospectos/
│   ├── calculadoras/    # cuentas puras: motor.py (TIR, duration...) y una por familia (cer.py, cer_cupon.py, tasa_fija.py, tamar.py, hard_dollar.py, dolar_linked.py), curva.py, breakeven.py, forwards.py y exit_yield.py
│   ├── leer_fichas.py   # lee y valida las fichas (en memoria mientras los archivos no cambien)
│   ├── metricas.py      # precio → TEA, TNA, duration y flujo de fondos de un bono, y tasa → precio (con las reglas de pago conocido); lo usan el agente, el panel, las curvas y las carteras
│   ├── pagos.py         # cupones y amortizaciones de un bono en la moneda de pago (libro de operaciones, variaciones y backtest)
│   └── curvas_mercado.py  # curvas de mercado (tasa fija, CER, TAMAR, dollar linked, Bonares) a precio de mercado
├── carteras/            # carteras de clientes: excel.py (Excel de datos/carteras/), valuar.py (valuación), operaciones.py (libro de operaciones, costo y resultados), evolucion.py (patrimonio, TWR y TIR), historia.py (variaciones y backtest) y proyeccion.py
├── macro/               # cálculos de macro, sin acceso externo
│   └── series.py        # variaciones de series (mensual, interanual, anualizada, acumulada)
├── fuentes_datos/       # toda la información que entra de afuera
│   ├── conexiones/      # acceso a fuentes externas, sin IA
│   │   ├── http.py          # timeouts, reintentos y caché comunes
│   │   ├── bcra.py          # API del BCRA (Principales Variables v4)
│   │   ├── series_tiempo.py # API de Series de Tiempo de datos.gob.ar
│   │   ├── fred.py          # API de FRED (series y calendario de publicaciones de EE. UU.)
│   │   ├── ppi.py           # API de PPI: precios de mercado, solo lectura
│   │   └── noticias.py      # Google News RSS y feeds de medios
│   ├── carga/           # procesos que traen datos y los guardan en las bases
│   │   ├── feriados.py             # librería holidays + ajustes manuales
│   │   ├── publicaciones_indec.py  # lector de los PDF del INDEC
│   │   ├── publicaciones_fred.py   # fechas de EE. UU. desde FRED
│   │   ├── publicaciones_regla.py  # fechas por regla de días hábiles (ISM, recaudación)
│   │   ├── catalogo.py             # lectura del catálogo de publicaciones
│   │   ├── precios.py              # precios diarios desde PPI, solo los días que faltan
│   │   ├── series.py               # CER, TAMAR y A3500 desde el BCRA, toda la historia y después los días nuevos
│   │   ├── rem.py                  # Excel del REM a la base
│   │   ├── fichas_documentos.py    # lector de fichas: borradores desde llamados a licitación y prospectos, y aprobación
│   │   ├── avisos_tesoro.py        # revisión periódica: lee los llamados y resultados nuevos del Tesoro
│   │   └── novedades.py            # aviso de lo que dejó cada aviso nuevo (notificación y panel)
│   ├── bases/           # lectura y escritura de las bases SQLite de datos/ (db.py, feriados, publicaciones, precios, series, rem)
│   ├── mercado.py       # datos de mercado de los bonos: precios (PPI), CER, A3500, TAMAR y feriados (base propia y fuentes)
│   └── manuales/        # lo que se carga o corrige a mano (se sube a git)
│       ├── calendarios/ # feriados_ajustes.toml, publicaciones.toml (catálogo, con importancia) e indec/ (PDF semestrales)
│       ├── rem/         # Excel del REM del BCRA
│       └── escenarios/  # escenarios propios: inflacion.toml, tamar.toml, dolar_oficial.toml, dolar_mep.toml, dolar_ccl.toml
├── datos/               # las bases y las carteras (no se suben a git)
│   ├── feriados.db
│   ├── publicaciones.db
│   ├── precios.db       # precios diarios de los activos consultados (respaldar)
│   ├── series.db        # CER, TAMAR y A3500 del BCRA (regenerable)
│   ├── rem.db           # expectativas del REM, por relevamiento (regenerable desde fuentes_datos/manuales/rem/)
│   └── carteras/        # Excel de cada cartera (respaldar)
├── prompts/             # instrucciones de cada agente
├── web/                  # panel web (Streamlit): app.py y salidas.py (de texto de herramientas a tablas)
├── tests/               # pruebas automáticas (python -m tests.test_renta_fija_cer, ..._cer_cupon, ..._tasa_fija, ..._tamar, ..._hard_dollar, ..._dolar_linked, tests.test_breakevens, tests.test_proyeccion_cer, tests.test_proyecciones, tests.test_caminos, tests.test_curva, tests.test_fichas_documentos, tests.test_avisos_tesoro, tests.test_web, tests.test_metricas, tests.test_carteras, tests.test_carteras_historia, tests.test_carteras_operaciones, tests.test_forwards, tests.test_duales, tests.test_grafo, tests.test_series)
└── docs/
    ├── arquitectura-multiagente.md   # arquitectura completa y plan por fases
    └── convenciones-renta-fija.md    # cómo se calcula cada variable de cada bono
```

Las capas están separadas a propósito: todo lo que entra de afuera pasa por `fuentes_datos/` (que no sabe nada de IA), `renta_fija/`, `carteras/` y `macro/` solo calculan, `tools/` no depende de LangGraph y `graph/` solo orquesta. Cambiar el modelo, el framework o una fuente de datos afecta a una sola capa.

## Instalación

Requiere Python 3.11 o superior.

```bash
git clone https://github.com/agustinmacri/Finianz.git
cd Finianz
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
cp .env.example .env
```

Completá el `.env` con tu clave de Gemini, que se obtiene gratis en [Google AI Studio](https://aistudio.google.com/apikey), con la de FRED, también gratuita, en [FRED](https://fredaccount.stlouisfed.org/apikeys), y con las de PPI si tenés cuenta (Gestiones → Gestión de servicio API).

> Ubicá el proyecto fuera de carpetas sincronizadas (OneDrive, Dropbox): la sincronización puede dañar archivos del entorno virtual.

## Configuración (`.env`)

| Variable | Qué hace | Por defecto |
|---|---|---|
| `GEMINI_API_KEY` | Clave de la API de Gemini | (obligatoria) |
| `PPI_API_KEY` / `PPI_API_SECRET` | Claves pública y privada de la API de PPI, para precios de mercado | (sin ellas, no hay precios) |
| `PPI_PLAZO` | Plazo de liquidación de los precios | `A-24HS` |
| `FRED_API_KEY` | Clave de la API de FRED, para los datos y las fechas de publicación de EE. UU. | (sin ella, no hay datos de EE. UU.) |
| `GEMINI_MODEL` | Modelo principal | `gemini-3.1-flash-lite` |
| `GEMINI_MODELOS_RESPALDO` | Modelos a usar si el principal está saturado, separados por coma | (ninguno) |
| `MAX_ITERACIONES` | Tope de vueltas modelo ↔ herramientas por pregunta | `15` |
| `CONFIRMAR_CODIGO` | Pedir confirmación antes de ejecutar el código Python que escribe el agente | `true` |
| `CACHE_MINUTOS` | Cuánto tiempo se reutiliza una respuesta de las APIs de datos | `60` |
| `CACHE_NOTICIAS_MINUTOS` | Ídem para noticias | `15` |

El `.env` contiene tus claves: nunca lo subas al repositorio (ya está en el `.gitignore`).

## Uso

```bash
python main.py                                   # modo conversación
python main.py "¿Cuál fue la última inflación?"  # una sola pregunta
```

En la terminal se ve qué agente responde y qué herramientas usa:

```
Vos: ¿cómo viene la inflación y qué dicen las noticias del BCRA?
  🧭 📊 macro + 📰 noticias
  🔧 [macro] buscar_indicador(texto='inflacion mensual')
  🔧 [noticias] buscar_noticias(tema='BCRA')
```

Comandos durante la conversación:

| Comando | Qué hace |
|---|---|
| `nuevo` | Empieza una conversación desde cero |
| `reintentar` | Si hubo un error temporal del modelo, continúa desde el paso donde se cortó, sin repetir lo que ya se hizo |
| `salir` | Termina |

## Bases de datos locales: feriados, publicaciones, series y precios

```bash
python actualizar.py
```

Crea o actualiza `datos/feriados.db` con los feriados de 2016 al año próximo. Los agentes la cargan solos la primera vez, pero conviene correrlo después de actualizar la librería `holidays` o de editar los ajustes. La base no se sube a git: se regenera en cualquier momento.

Los feriados salen de la librería [`holidays`](https://github.com/vacanza/holidays). Para corregir un caso puntual (un feriado decretado que la librería todavía no tiene, o un día que el mercado operó), editá `fuentes_datos/manuales/calendarios/feriados_ajustes.toml` y volvé a correr `python actualizar.py`. Los ajustes tienen prioridad sobre la librería.

> El calendario de BYMA de la librería empieza en 2026. Para años anteriores se usa el calendario nacional como aproximación, y las respuestas lo indican.

Las fechas de publicación del INDEC salen de sus calendarios semestrales en PDF, guardados en `fuentes_datos/manuales/calendarios/indec/`. Cuando el INDEC publica el de un semestre nuevo (`indec.gob.ar/ftp/cuadros/publicaciones/calendario_<1|2>sem<año>.pdf`), copialo a esa carpeta y corré `python actualizar.py`. Si el INDEC actualiza un semestre, reemplazá el PDF viejo.

Las fechas de EE. UU. salen de la API de FRED, que ya tiene programadas las publicaciones de los próximos meses. Conviene correr `python actualizar.py` una vez por semana para traer las nuevas. Las horas se informan en hora del este de EE. UU. (ET).

Las publicaciones con fecha fija por regla (por ejemplo, el ISM manufacturero sale el primer día hábil del mes) se calculan con la base de feriados. La regla de cada una está en el catálogo.

Qué publicaciones se siguen y con qué importancia se define en `fuentes_datos/manuales/calendarios/publicaciones.toml`. Las del INDEC que no están en el catálogo también se guardan, con importancia baja.

**Series (CER, TAMAR y A3500).** `datos/series.db` guarda el CER diario del BCRA desde 2002, la TAMAR de bancos privados (variable 44, % TNA, días hábiles) y el tipo de cambio A3500 (variable 5). La primera vez se baja toda la historia (tarda unos segundos) y después solo los días nuevos; como el BCRA publica el CER por adelantado, se piden también los próximos 60 días. Las calculadoras de bonos toman de acá el CER corriente y el CER inicial de cada bono (el del 10.º día hábil anterior a su emisión), así las fichas solo tienen condiciones de emisión. Se regenera en cualquier momento. Para comparar las bases con las de tus Excel: `python -m tests.verificar_cer_inicial`.

**Fichas de bonos nuevos.** `python -m fuentes_datos.carga.fichas_documentos leer <URL o archivo>` lee un llamado a licitación del Tesoro (o su resultado, una resolución o un prospecto) y deja borradores de fichas de los bonos nuevos en `renta_fija/fichas/borradores/borradores.toml`, con lo que falta anotado como pendiente. Esa carpeta está en `.gitignore`: lo que no aprobaste no se sube. Después de revisarlos: `... pendientes`, `... aprobar <TICKER>` (pasa la ficha al archivo de su familia) o `... descartar <TICKER>`. Con el resultado de una licitación informa lo licitado y el valor de corte (precio, TEM o margen, y la TIREA): un precio de corte no cambia ninguna ficha; la TEM o el margen de un bono nuevo completan su borrador (`... completar <clave> ticker=<TICKER>` si el ticker no vino); y si un dato no coincide con una ficha ya aprobada queda como cambio propuesto en `borradores/cambios.toml`, que se aplica solo con `... aplicar <TICKER>` (o `... rechazar <TICKER>`; `... cambios` los lista). Una reapertura de un bono que no teníamos queda sin fecha de emisión (la del aviso no es la original) hasta que se lee el documento de la primera emisión: si tenés el link, `... leer <URL> --solo <clave>` toma de ese aviso únicamente los datos de ese bono (la búsqueda automática, `... emision <clave>`, está en pausa: el modelo no llega a buscar y escribe links de memoria). Si un borrador coincide en familia, vencimiento y condiciones con un bono ya cargado, no se aprueba solo: `... vincular <clave> <TICKER>` si es el mismo o `... aprobar <TICKER> --nuevo` si es otro. Los borradores sin ticker se buscan en PPI por la convención de nombres del Tesoro (`... tickers`, y también al leer y al listar pendientes). Los bonos ya vencidos no se cargan (y un borrador que vence esperando aprobación se saca solo). El agente de renta fija hace lo mismo si le pasás el documento, y también muestra, aprueba o descarta borradores, pero solo cuando se lo pedís nombrando el bono.

**Panel web (prueba).** Por ahora se muestra sin el nombre del producto (`MOSTRAR_NOMBRE = False` en `web/app.py`). `streamlit run web/app.py` abre el panel de renta fija en el navegador (http://localhost:8501): las curvas de tasa fija, CER, TAMAR, dollar linked y Bonares (una a la vez) con su curva ajustada y una tabla editable (ticker, precio, TEA, TNA y duration: escribís un precio o una tasa y se recalcula el bono y su punto en la curva); la calculadora de un bono (precio ↔ TEA/TNA, duration y otras métricas, y el flujo de fondos con fecha, cupón y amortización); los breakevens; las proyecciones con el camino usado contra el breakeven y el REM (en gráfico y tabla); y las fichas y borradores. Los precios de hoy se actualizan solos cada 1, 2 o 5 minutos, o se puede elegir el cierre de una fecha. El panel no calcula nada propio: llama a las mismas herramientas que el agente (tools/) y convierte sus tablas de texto en tablas (web/salidas.py). La apariencia tiene dos modos, Blanco (por defecto: vista asesor y presentación a clientes) y Obsidiana (fondo oscuro para análisis intensivo), que se cambian con el interruptor "Modo obsidiana" de la barra lateral; las paletas están en `.streamlit/config.toml` y lo que el tema no cubre, en `web/app.py` (PALETAS) y el logo en `web/imagenes/`; hay que correrlo desde la carpeta del proyecto para que tome esa configuración. Corre en tu compu: la "Network URL" que muestra Streamlit solo sirve dentro de tu mismo wifi.

**Compartir el panel por internet (túnel).** 1) Poné `PANEL_CLAVE=una-contraseña-larga` en el `.env`: con eso el panel pide contraseña (sin ella abre directo y avisa en la barra lateral). Después de entrar, ese navegador queda habilitado 12 horas (cookie), así el cambio de modo no la vuelve a pedir. 2) Instalá cloudflared una vez: `winget install --id Cloudflare.cloudflared`. 3) Doble clic en `compartir_panel.bat` (o, en dos terminales: `streamlit run web/app.py` y `cloudflared tunnel --url http://localhost:8501`). Aparece un link `https://....trycloudflare.com`: ese se comparte, junto con la contraseña. El link funciona mientras tu compu y las dos ventanas estén abiertas, y cambia cada vez que lo levantás. Quien entra usa tus consultas a PPI; revisá sus términos antes de mostrar precios a terceros.

**Bonos con el pago final ya conocido.** Cuando ya está publicado el CER que ajusta el último pago (el del 10.º día hábil anterior), la TAMAR de toda la ventana (hasta 10 días hábiles antes del vencimiento) o el A3500 de pago de un dollar linked (3.er día hábil anterior al vencimiento; otro rezago con `rezago_tipo_cambio` en la ficha), el pago queda fijo en pesos y el bono pasa a ser de tasa fija desde ese día. Para una fecha de análisis pasada cuenta lo que se sabía ese día: si todavía no se conocía, sigue siendo indexado y va en su curva aunque hoy el dato ya esté en la base (el CER de una fecha se conoce cuando el INDEC publica el IPC que lo arma, según el calendario de publicaciones; el A3500 y la TAMAR, el día de su fecha). Pasa a tasa fija en: TIR nominal y curva de tasa fija en el panel, los forwards, los breakevens y las carteras (`mercado.cer_final_conocido`, `mercado.a3500_pago_conocido`, `metricas.calculadora`). Por ejemplo, con la inflación de octubre publicada el 14/11, el X30N6 y el TZXD6.

**Sección Curvas (panel).** Pedidos de Agustin (27/11/2026):
- Variación contra el cierre del día hábil anterior al lado del precio (en pesos y %), de la TEA (o el spread) y de la TNA (en pb): en verde con ▲ si sube y en rojo con ▼ si baja.
- TAMAR: el gráfico y la tabla muestran el spread sobre la TAMAR de referencia (TNA 30 d − promedio de los últimos 5 días publicados), editable; la TNA sigue a la vista.
- Hard dollar: Bonares (ley AR) y Globales (ley NY) en el mismo gráfico, cada uno con su curva, en dólares MEP o cable (selector "Dólar").
- Duales: cada pata en la curva de su familia, como una serie aparte por tipo de dual (Duales CER/TAMAR en CER y en TAMAR, Duales tasa fija/TAMAR en tasa fija y en TAMAR, Duales TAMAR/dollar linked en TAMAR y en dollar linked); con 3 o más se les ajusta su propia curva, con menos quedan los puntos. Cuando la pata que va a pagar ya está definida (su pago mínimo, con lo que falta publicar en cero —TAMAR, inflación o A3500—, ya supera el máximo posible de la otra; `renta_fija/duales.py`), el dual figura solo en la curva de esa pata, como un bono más de la curva principal (ej.: TTD26 en TAMAR).
- Cada curva del gráfico va en otro color. Debajo, en este orden: las tablas de rendimientos (primero la curva principal y después los duales, o Bonares y después Globales, cada una aparte), las matrices de forwards de cada una y la exit yield, con la fecha de salida ahí mismo y una tabla por curva.
- Las celdas sin dato quedan en blanco.
- Proyecciones: la TAMAR tiene también la fuente `breakeven` (la que descuenta el mercado: bonos TAMAR contra la tasa fija, encadenada por tramos entre los fines de ventana). Los supuestos se tildan (ninguno, uno o todos, más un camino propio) y cada uno es una línea del gráfico; el detalle de cada uno, contra el breakeven y el REM, queda en un desplegable.
- Exit yield casilla por casilla: cada bono arranca con la TIR de hoy; se escribe otra tasa o un precio de salida (y sale la tasa a esa fecha).
- Bono nuevo entre el resultado de la licitación y su liquidación: entra a las curvas y a la calculadora al precio de corte (el del resultado, por 100 VN, o a la par si se licitó por tasa o margen), con la liquidación en la fecha de emisión. El lector guarda ese precio en `datos/licitaciones.json` al leer el resultado; a mano: `python -m fuentes_datos.carga.fichas_documentos corte <TICKER> <precio | par> <emisión AAAA-MM-DD>`.

**Forwards (panel, sección Curvas).** En todas las curvas (tasa fija, CER, TAMAR, dollar linked y hard dollar), la columna *Forwards (%)* de cada bono es la tasa entre el vencimiento del bono anterior de la curva y el suyo: a la que habría que renovar el anterior para rendir lo mismo que comprar este hoy (el más corto queda vacío; en CER es real, en dollar linked y bonares en dólares). Debajo, la matriz de forwards entre todos los pares, con el bono corto en las columnas y el largo en las filas. f = [(1 + TIR largo)^t largo / (1 + TIR corto)^t corto]^(1 / (t largo − t corto)) − 1, con t en años desde la liquidación hasta cada vencimiento (`renta_fija/calculadoras/forwards.py`). Se recalcula con los precios o tasas que cargues en la tabla.

**Duales.** `calcular_bono` muestra cada pata y cierra con qué pata paga: TAMAR/tasa fija (TAMAR de indiferencia), CER/TAMAR y TAMAR/dollar linked (TMVE8: A3500 de indiferencia, la devaluación que implica y qué pata paga con el REM y con el breakeven del mercado). En el TMVE8 el VN está en dólares y la pata TAMAR capitaliza el VN al tipo de cambio inicial: su ficha TAMAR lleva `fecha_tipo_cambio_inicial` (o `tipo_cambio_inicial`).

**Exit yield.** Retorno de un bono si se vende en una fecha a una TIR de salida (`renta_fija/calculadoras/exit_yield.py`): precio de salida (valor presente de los flujos posteriores a la exit yield, en la unidad del bono), cupones y amortizaciones cobrados hasta la salida reinvertidos a la exit yield, retorno del período y anualizado; con exit yield igual a la TIR de hoy, el retorno anualizado es la TIR de hoy. En la calculadora del panel (sección Bono), con su sensibilidad de −200 a +200 pb; y en Curvas, una tabla con todos los bonos de la curva para una fecha de salida, con la exit yield (o el precio de salida) editable bono por bono.

**Carteras de clientes.** Cada cartera es un Excel en `datos/carteras/` (fuera del repo: los datos de los clientes no se suben). `python -m carteras plantilla` copia la plantilla a `datos/carteras/nueva_cartera.xlsx`: se renombra con el nombre de la cartera y se completa la hoja *Cartera* (Ticker y Nominales; Tipo Activo y Descripcion son opcionales y, si se completan, se respetan) y, si hace falta, la hoja *Supuestos* (fuente de la proyección por variable: inflación, TAMAR, dólar oficial, MEP y CCL; por defecto "rem"; también "mensual:2%", "escenario:<nombre>" o "camino:..."). `python -m carteras listar` las muestra y `python -m carteras ver <nombre> [--moneda pesos|mep|ccl] [--excel]` la valúa: Tipo Activo, Descripcion, Ticker, Tir Spread/Nominal (tasa fija: TIR; CER: CER + tasa real; TAMAR: spread sobre la TAMAR; dollar linked y hard dollar: TIR en dólares), Tir Nominal en base a proyeccion (TIR en pesos con los supuestos; duales: la pata que más rinde), Nominales, Precio, Total, % Cartera y Duration Activo, con los totales de renta fija ponderados por monto. La renta variable va sin tasas ni duration. Valuación en pesos, con los hard dollar ley argentina al MEP y los ley Nueva York al CCL (implícitos del AL30); en `mep` o `ccl` todo se divide por ese tipo de cambio. Con `--excel` guarda la valuación en `datos/carteras/salidas/`. La hoja opcional *Liquidez* suma liquidez, pasivos y créditos (Tipo: Liquidez, Money market, Caución colocadora, Plazo fijo, Crédito, Caución tomadora o Pasivo; Moneda: pesos, mep o ccl; Monto positivo; Tasa TNA y Vencimiento opcionales): los pasivos restan del patrimonio y todo pondera en la TIR y la duration (la liquidez sin colocar rinde 0 con duration 0). Cada activo se clasifica por categoría (Renta Fija, Renta Variable, Liquidez, Créditos, Pasivos…), subclase (Tasa fija, CER, TAMAR, Dollar linked, Hard dollar, Duales, Acciones, CEDEARs…), moneda (Pesos, Pesos ajustables al dólar oficial —dollar linked—, Pesos ajustables al MEP —CEDEARs—, Dólar MEP, Dólar CCL) y emisor (campo `emisor` de la ficha; si falta, Tesoro Nacional). La valuación suma los cuadros por clase, por moneda, clase × moneda y por emisor, y los cobros de cupón, amortizaciones y vencimientos de los próximos 30 días. El agente de renta fija hace lo mismo (`ver_cartera`, `listar_carteras`). **Operaciones (etapa 3).** Una cartera puede llevar la hoja *Operaciones* (Fecha de concertación, Contraparte, Tipo, Ticker, Nominales, Precio, Moneda, Monto, Tasa, Vencimiento, Gastos, Nota; ver `carteras/operaciones.py`): de ahí salen las posiciones, la liquidez por moneda (pesos, MEP, cable), el money market (Suscripción, Rescate y Valuación, en plata, a la última TNA), las cauciones, créditos y pasivos (se cancelan solos al vencer), los cupones y amortizaciones (calculados con las fichas y cobrados enteros a la liquidez; una fila Cobro con el monto del aviso de pago manda), el costo promedio ponderado en pesos, MEP y cable (cada operación al tipo de cambio de su día) y el resultado realizado (ventas, cupones, amortizaciones contra el costo de la parte amortizada, dividendos e intereses) y no realizado. La cartera muestra siempre arriba la liquidez (una fila por moneda), el money market y la caución, y abajo de todo crédito y pasivo, aunque estén en cero. En el panel, Editar abre el editor de operaciones, la vista Resultados muestra lo realizado, lo no realizado y los cobros, y la vista Evolución el patrimonio de cada día desde la primera operación (pesos, MEP o cable), los aportes netos, la ganancia, el rendimiento sin el efecto de aportes y retiros (TWR) y la TIR de la cartera (`carteras/evolucion.py`). `python -m carteras convertir <nombre> --fecha AAAA-MM-DD` pasa una cartera cargada como foto a operaciones (ingresos al cierre de esa fecha; la versión anterior queda en `datos/carteras/anteriores/`). Debajo de la tabla, el panel tiene cuatro análisis: **Composición y cobros**; **Variaciones** (día, semana, mes, en el año y 12 meses; variación de precio o retorno total con cupones y amortizaciones, en la moneda de la vista; `carteras/historia.py`); **Proyección** (fecha y uno o varios escenarios —los supuestos de la cartera, el REM, los breakevens y los escenarios con nombre de `fuentes_datos/manuales/escenarios/`—, con TIR constante, cupones reinvertidos, lo que vence repartido entre los demás activos y las acciones a valor constante en dólares; `carteras/proyeccion.py`) y **Backtest** (el patrimonio de hoy invertido con la composición de hoy desde una fecha, en pesos, MEP y CCL; cupones reinvertidos en el mismo activo, lo que se cobra entero repartido entre los demás y lo que todavía no cotizaba como liquidez a TAMAR). En el panel web, la sección **Carteras** muestra la cartera con su nombre arriba, el patrimonio, la TIR nominal proyectada y la duration, la tabla, los gráficos y el Excel descargable; "Editar" vuelve editable esa misma tabla (más supuestos y nombre), "Guardar" escribe el mismo Excel y "Archivar" la mueve a `datos/carteras/anteriores/` sin borrarla. El chat con la IA sobre la cartera está hecho pero oculto (`MOSTRAR_CHAT` en `web/carteras_panel.py`). Si el panel tiene `PANEL_CLAVE` (para compartirlo), la sección pide además `CARTERAS_CLAVE` y sin ella queda cerrada: los amigos con el link no ven las carteras ni usan tu cuota de Gemini.

**Avisos del Tesoro (actualización periódica).** `python -m fuentes_datos.carga.avisos_tesoro` lee la portada de la Secretaría de Finanzas (donde los avisos del día aparecen primero) y las primeras páginas de su listado de noticias (https://www.argentina.gob.ar/economia/finanzas/noticias), toma los avisos cuyo título empieza con "Llamado", "Resultado", "Anuncio complementario" o "Conversión" y lee con el lector de fichas los que todavía no leyó, del más viejo al más nuevo: borradores de los bonos nuevos, valores de corte y cambios propuestos (nada se aprueba solo). No depende del título ni de los números de las direcciones. Guarda en `datos/avisos_tesoro.json` qué avisos ya leyó (`... estado`, `... listado` muestra el listado y qué falta, `... marcar <URL>` da uno por leído y `... olvidar <URL>` lo vuelve a leer). También corre dentro de `python actualizar.py`. El lector solo deja como borrador lo que no tenemos: si el ticker ya está en la base, no entra (los datos distintos quedan como cambios propuestos; la excepción es la pata de un dual que falta), y si el aviso no trae ticker pero las condiciones coinciden con un bono cargado (familia, vencimiento y, si están, cupón o margen), tampoco. Si un borrador trae un ticker que no tenemos pero las mismas condiciones que otro, queda marcado como posible duplicado y decidís vos (`vincular` o `aprobar --nuevo`).

Para que corra solo en Windows: Programador de tareas → Crear tarea básica → "Finianz avisos del Tesoro" → Diariamente → acción "Iniciar un programa" → `revisar_avisos.bat` de la carpeta del proyecto. Conviene dos horarios por día hábil, por ejemplo 10:00 y 19:30 (los resultados salen a la tarde del día de la licitación). O desde una consola de Windows: `schtasks /Create /TN "Finianz avisos del Tesoro" /SC WEEKLY /D LUN,MAR,MIE,JUE,VIE /ST 19:30 /TR "C:\ruta\a\finianz\revisar_avisos.bat"`. Lo que hizo queda en `datos/avisos_tesoro.log`. Cuando un aviso nuevo deja algo para revisar (borradores nuevos o completados, valores de corte, cambios propuestos), llega una notificación de Windows y el panel lo marca en la barra lateral y en la sección Fichas hasta que tocás "Marcar como vistas" (`fuentes_datos/carga/novedades.py`, registro en `datos/novedades_fichas.json`; `python -m fuentes_datos.carga.novedades` las lista, `... vistas` las marca y `... probar` manda una notificación de prueba). En Mac o Linux, con cron: `30 19 * * 1-5 cd /ruta/a/finianz && .venv/bin/python -m fuentes_datos.carga.avisos_tesoro >> datos/avisos_tesoro.log 2>&1`.

**REM.** El BCRA publica cada mes un Excel con las expectativas del Relevamiento de Expectativas de Mercado (inflación, TAMAR, tipo de cambio, PIB...) mes a mes y por año. La API solo trae la inflación a 12 meses, así que se baja el Excel del sitio del BCRA a `fuentes_datos/manuales/rem/` y `python actualizar.py` lo carga en `datos/rem.db`. La proyección del CER lo usa con la fuente `rem`.

**Precios.** Cada activo que consultás queda "seguido": la primera vez se baja todo su histórico de PPI a `datos/precios.db`, y después solo se piden los días que faltan. `python actualizar.py` suma los cierres nuevos de todos los seguidos (el cierre del día se guarda recién después de las 18 h). El precio del momento se consulta en vivo y no se guarda. A diferencia de las otras bases, esta no se puede regenerar del todo: hacele respaldos.

## Seguridad

La herramienta `ejecutar_python` corre en tu computadora el código que escribe el agente. Con `CONFIRMAR_CODIGO=true`, te muestra el código y pide confirmación antes de ejecutarlo. Desactivalo solo cuando conozcas el tipo de código que genera. Además, ese código:

- corre sin las claves de PPI ni de Gemini;
- corre vigilado por `tools/guardia.py`, que bloquea leer el `.env` y las bases de datos, escribir o borrar archivos, lanzar otros programas y conectarse a sitios que no sean las APIs de datos (BCRA, datos.gob.ar, FRED). No es un aislamiento total (Python lo aclara): protege contra errores del modelo y contra instrucciones maliciosas que pudieran llegar en los datos. Si tu red usa un proxy, esas conexiones también quedan bloqueadas.

La conexión con PPI es de solo lectura a propósito: `fuentes_datos/conexiones/ppi.py` implementa únicamente consultas de precios. No usa la librería oficial, que incluye órdenes y transferencias, así que nada en el proyecto puede operar con tu cuenta.

Para probar la conexión: `python -m fuentes_datos.conexiones.ppi AL30` muestra las respuestas de la API, sin claves.

## Hoja de ruta

El sistema se construye por fases. El detalle está en [`docs/arquitectura-multiagente.md`](docs/arquitectura-multiagente.md).

- [ ] **Fase A** (en curso): router + agentes macro y noticias ✓; calendario de publicaciones del INDEC ✓, de EE. UU. (FRED) ✓ y por regla (ISM, recaudación) ✓; faltan las manuales (BCRA, Tesoro, FOMC).
- [ ] **Fase B** (en curso): bases de datos locales (✓ feriados, ✓ publicaciones), precios de mercado (✓ consulta en vivo vía PPI; falta la base de precios), cartera y registro de pronósticos.
- [ ] **Fase C** (en curso): calculadoras de bonos (✓ motor, ✓ CER cupón cero, ✓ CER con cupón: TX28 y TX31, ✓ tasa fija: Lecap/Boncap y TY30P, ✓ TAMAR: Bonos TAMAR y duales TTD26 y TXM, ✓ hard dollar: Bonares y Globales del canje 2020, ✓ dollar linked del Tesoro, ✓ breakevens entre curvas, ✓ proyección del CER y rendimiento nominal, ✓ REM, ✓ escenarios de TAMAR y dólar, ✓ curva teórica, ✓ letras a descuento, ✓ dollar linked con cupón; faltan cargar ONs) y ✓ agente de renta fija.
- [ ] **Fase D:** agente de escenarios y estratega (retornos esperados, estrés, límites regulatorios).
- [ ] **Fase E:** redactor de informes y revisión humana.
- [ ] **Fase F:** agente de equity (balances, DCF, comparables).

## Aviso

Finianz es una herramienta de análisis y no constituye asesoramiento financiero. Los datos provienen de fuentes públicas que pueden tener demoras o errores; verificá siempre las cifras antes de tomar decisiones.
