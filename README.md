# Finianz

Sistema multiagente en Python para asistir a un portfolio manager o asesor financiero en Argentina. Los agentes consultan datos oficiales y noticias, los analizan y responden en lenguaje natural, citando siempre la fuente y la fecha de cada dato.

Construido con [LangGraph](https://langchain-ai.github.io/langgraph/) y modelos Gemini de Google. Todas las fuentes de datos son gratuitas.

## Qué puede hacer hoy

| Agente | Qué hace | Fuentes |
|---|---|---|
| **Macro** | Busca y analiza indicadores: inflación, expectativas del REM, reservas, tipo de cambio, tasas, CER, UVA, actividad. De EE. UU.: CPI, PCE, empleo, PBI, tasa de la Fed, bonos del Tesoro. Precios de bonos, letras, ONs, acciones y CEDEARs. Calcula acumulados, tasas reales y proyecciones. | API del BCRA, Series de Tiempo de datos.gob.ar, FRED, API de PPI |
| **Noticias** | Busca noticias sobre un tema y resume los titulares del día, con su implicancia para el mercado. | Google News (RSS), feeds de Ámbito |

Los dos agentes consultan además un **calendario de feriados** de Argentina y EE. UU. (nacionales, bancos, BYMA, NYSE y bonos del Tesoro) desde 2016 hasta el año próximo, y calculan días hábiles por mercado (por ejemplo, la liquidación T+2).

También consultan un **calendario de publicaciones** con las fechas de los datos oficiales que sigue el proyecto (IPC, EMAE, salarios y balanza de pagos del INDEC; recaudación de ARCA; CPI, empleo, PCE, PBI, ISM y otras de EE. UU.), para saber cuándo sale el próximo dato. Las del BCRA, el Tesoro y la Fed se suman en el próximo paso.

Un **router** decide qué agente responde cada pregunta. Si hacen falta los dos, corren en paralelo y sus respuestas se integran en una sola.

Ejemplos de preguntas:

- *¿Cuál fue la última inflación y qué espera el REM?*
- *¿Cuánto da la inflación acumulada en el año?*
- *¿Cuál fue el último dato de inflación en EE. UU. y cuándo sale el próximo?*
- *¿Qué pasó hoy en el mercado?*
- *¿Cómo viene la inflación y qué se dice de la próxima licitación?*

## Cómo funciona

```
                       ┌→ agente_macro ────┐
    pregunta → router ─┤                   ├→ responder → respuesta
                       ├→ agente_noticias ─┤
                       └───────────────────┘   (saludos: directo a responder)
```

- **Router:** una sola llamada al modelo, con salida estructurada. Elige entre `macro`, `noticias`, `ambos` o `general`.
- **Agentes:** cada uno es un subgrafo con su propio prompt y **solo sus herramientas**. Iteran entre el modelo y las herramientas hasta tener la respuesta.
- **Responder:** si respondió un solo agente, devuelve su informe tal cual, sin otra llamada al modelo. Si respondieron los dos, los integra.
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
│   ├── guardia.py       # límites de seguridad del código que escribe el agente
│   ├── calendario.py    # consultar_feriados, calcular_dia_habil, consultar_publicaciones
│   └── python_exec.py   # ejecutar_python, con acceso a los datos
├── calculos/            # cálculos propios, sin acceso externo
│   └── series.py        # variaciones de series (mensual, interanual, anualizada, acumulada)
├── renta_fija/          # todo lo propio de bonos y letras
│   ├── fichas/          # fichas técnicas (cer.toml, cer_cupon.toml, tasa_fija.toml, tamar.toml, hard_dollar.toml) y prospectos/
│   ├── calculadoras/    # cuentas puras: motor.py (TIR, duration...) y una por familia (cer.py, cer_cupon.py, tasa_fija.py, tamar.py, hard_dollar.py)
│   └── leer_fichas.py   # lee y valida las fichas
├── conexiones/             # acceso a fuentes externas, sin IA
│   ├── http.py          # timeouts, reintentos y caché comunes
│   ├── bcra.py          # API del BCRA (Principales Variables v4)
│   ├── series_tiempo.py # API de Series de Tiempo de datos.gob.ar
│   ├── fred.py          # API de FRED (series y calendario de publicaciones de EE. UU.)
│   ├── ppi.py           # API de PPI: precios de mercado, solo lectura
│   └── noticias.py      # Google News RSS y feeds de medios
├── admin_datos/             # bases de datos locales (SQLite, una por tema)
│   ├── db.py            # tablas de cada base y conexión
│   ├── feriados.py      # consultas de feriados y días hábiles
│   ├── publicaciones.py # consultas del calendario de publicaciones
│   ├── precios.py       # consultas de la base de precios
│   └── series.py        # consultas de la base de series (CER)
├── carga_datos/             # carga de datos en la base
│   ├── feriados.py      # librería holidays + ajustes manuales
│   ├── publicaciones_indec.py  # lector de los PDF del INDEC
│   ├── publicaciones_fred.py   # fechas de EE. UU. desde FRED
│   ├── publicaciones_regla.py  # fechas por regla de días hábiles (ISM, recaudación)
│   ├── precios.py              # precios diarios desde PPI, solo los días que faltan
│   ├── series.py               # CER y TAMAR desde el BCRA, toda la historia y después los días nuevos
│   └── catalogo.py      # lectura del catálogo de publicaciones
├── datos/               # las bases (no se suben a git)
│   ├── feriados.db
│   ├── publicaciones.db
│   ├── precios.db       # precios diarios de los activos consultados (respaldar)
│   ├── series.db        # CER y TAMAR del BCRA (regenerable)
│   └── cartera.db       # fase B
├── calendarios/
│   ├── feriados_ajustes.toml   # correcciones manuales a los feriados
│   ├── publicaciones.toml      # catálogo de publicaciones que se siguen, con su importancia
│   └── indec/                  # calendarios semestrales del INDEC en PDF
├── prompts/             # instrucciones de cada agente
├── tests/               # pruebas automáticas (python -m tests.test_renta_fija_cer, ..._cer_cupon, ..._tasa_fija, ..._tamar, ..._hard_dollar, tests.test_series)
└── docs/
    ├── arquitectura-multiagente.md   # arquitectura completa y plan por fases
    └── convenciones-renta-fija.md    # cómo se calcula cada variable de cada bono
```

Las capas están separadas a propósito: `conexiones/` y `carga_datos/` no saben nada de IA, `tools/` no depende de LangGraph y `graph/` solo orquesta. Cambiar el modelo, el framework o una fuente de datos afecta a una sola capa.

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

Los feriados salen de la librería [`holidays`](https://github.com/vacanza/holidays). Para corregir un caso puntual (un feriado decretado que la librería todavía no tiene, o un día que el mercado operó), editá `calendarios/feriados_ajustes.toml` y volvé a correr `python actualizar.py`. Los ajustes tienen prioridad sobre la librería.

> El calendario de BYMA de la librería empieza en 2026. Para años anteriores se usa el calendario nacional como aproximación, y las respuestas lo indican.

Las fechas de publicación del INDEC salen de sus calendarios semestrales en PDF, guardados en `calendarios/indec/`. Cuando el INDEC publica el de un semestre nuevo (`indec.gob.ar/ftp/cuadros/publicaciones/calendario_<1|2>sem<año>.pdf`), copialo a esa carpeta y corré `python actualizar.py`. Si el INDEC actualiza un semestre, reemplazá el PDF viejo.

Las fechas de EE. UU. salen de la API de FRED, que ya tiene programadas las publicaciones de los próximos meses. Conviene correr `python actualizar.py` una vez por semana para traer las nuevas. Las horas se informan en hora del este de EE. UU. (ET).

Las publicaciones con fecha fija por regla (por ejemplo, el ISM manufacturero sale el primer día hábil del mes) se calculan con la base de feriados. La regla de cada una está en el catálogo.

Qué publicaciones se siguen y con qué importancia se define en `calendarios/publicaciones.toml`. Las del INDEC que no están en el catálogo también se guardan, con importancia baja.

**Series (CER y TAMAR).** `datos/series.db` guarda el CER diario del BCRA desde 2002 y la TAMAR de bancos privados (variable 44, % TNA, días hábiles). La primera vez se baja toda la historia (tarda unos segundos) y después solo los días nuevos; como el BCRA publica el CER por adelantado, se piden también los próximos 60 días. Las calculadoras de bonos toman de acá el CER corriente y el CER inicial de cada bono (el del 10.º día hábil anterior a su emisión), así las fichas solo tienen condiciones de emisión. Se regenera en cualquier momento. Para comparar las bases con las de tus Excel: `python -m tests.verificar_cer_inicial`.

**Precios.** Cada activo que consultás queda "seguido": la primera vez se baja todo su histórico de PPI a `datos/precios.db`, y después solo se piden los días que faltan. `python actualizar.py` suma los cierres nuevos de todos los seguidos (el cierre del día se guarda recién después de las 18 h). El precio del momento se consulta en vivo y no se guarda. A diferencia de las otras bases, esta no se puede regenerar del todo: hacele respaldos.

## Seguridad

La herramienta `ejecutar_python` corre en tu computadora el código que escribe el agente. Con `CONFIRMAR_CODIGO=true`, te muestra el código y pide confirmación antes de ejecutarlo. Desactivalo solo cuando conozcas el tipo de código que genera. Además, ese código:

- corre sin las claves de PPI ni de Gemini;
- corre vigilado por `tools/guardia.py`, que bloquea leer el `.env` y las bases de datos, escribir o borrar archivos, lanzar otros programas y conectarse a sitios que no sean las APIs de datos (BCRA, datos.gob.ar, FRED). No es un aislamiento total (Python lo aclara): protege contra errores del modelo y contra instrucciones maliciosas que pudieran llegar en los datos. Si tu red usa un proxy, esas conexiones también quedan bloqueadas.

La conexión con PPI es de solo lectura a propósito: `conexiones/ppi.py` implementa únicamente consultas de precios. No usa la librería oficial, que incluye órdenes y transferencias, así que nada en el proyecto puede operar con tu cuenta.

Para probar la conexión: `python -m conexiones.ppi AL30` muestra las respuestas de la API, sin claves.

## Hoja de ruta

El sistema se construye por fases. El detalle está en [`docs/arquitectura-multiagente.md`](docs/arquitectura-multiagente.md).

- [ ] **Fase A** (en curso): router + agentes macro y noticias ✓; calendario de publicaciones del INDEC ✓, de EE. UU. (FRED) ✓ y por regla (ISM, recaudación) ✓; faltan las manuales (BCRA, Tesoro, FOMC).
- [ ] **Fase B** (en curso): bases de datos locales (✓ feriados, ✓ publicaciones), precios de mercado (✓ consulta en vivo vía PPI; falta la base de precios), cartera y registro de pronósticos.
- [ ] **Fase C** (en curso): calculadoras de bonos (✓ motor, ✓ CER cupón cero, ✓ CER con cupón: TX28 y TX31, ✓ tasa fija: Lecap/Boncap y TY30P, ✓ TAMAR: Bonos TAMAR y duales TTD26 y TXM, ✓ hard dollar: Bonares y Globales del canje 2020) y agente de renta fija.
- [ ] **Fase D:** agente de escenarios y estratega (retornos esperados, estrés, límites regulatorios).
- [ ] **Fase E:** redactor de informes y revisión humana.
- [ ] **Fase F:** agente de equity (balances, DCF, comparables).

## Aviso

Finianz es una herramienta de análisis y no constituye asesoramiento financiero. Los datos provienen de fuentes públicas que pueden tener demoras o errores; verificá siempre las cifras antes de tomar decisiones.
