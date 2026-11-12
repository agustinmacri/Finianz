# Finianz – Arquitectura multiagente

Acordada el 11/11/2026. Última actualización: 11/11/2026 (feriados y base local).

## Principio

No todo es un agente:

- **Agentes** donde hace falta criterio.
- **Código** para cálculos que tienen una forma correcta de hacerse.
- **Procesos programados** (sin IA) para traer datos que se repiten.

## Agentes

| Agente | Tareas | Herramientas / insumos |
|---|---|---|
| Router | Clasifica el pedido (una llamada, modelo barato, salida estructurada) | — |
| Macro | Buscar y analizar indicadores; comparar con el consenso (REM) | `datos_macro` (BCRA, datos.gob.ar), `ejecutar_python` |
| Noticias | Noticias de medios y regulación (BCRA, CNV); calendario de eventos | Google News RSS, feeds de medios, calendario |
| Escenarios | Econometría + plantear escenarios; diferencias con el consenso (REM) | Herramientas econométricas en código |
| Renta fija | Valuación de bonos por escenario | Calculadoras: TIR, duration, proyección CER, precio por escenario |
| Equity | DCF y comparables (sector local y de otro país) | Balances extraídos a la base; DCF y múltiplos en código |
| Estratega | Retornos esperados ponderados, cartera, estrés, límites | Cálculo en código + posiciones propias + políticas |
| Redactor | Informe final | Salidas estructuradas de los demás agentes |

## Unificaciones

- Buscar + analizar indicadores → **agente macro**.
- Econometría + escenarios → **agente escenarios**.
- Buscar empresas + leer balances → **proceso de carga** (no es un agente): cada balance se extrae una sola vez a datos estructurados.
- Calculadoras de bonos + rendimientos esperados de bonos → **agente renta fija**.

## Orquestación

1. **Router a la entrada.** Las consultas puntuales van a un solo agente; solo el informe completo activa todo el flujo.
2. **Flujo fijo** (aristas del grafo) donde el orden se conoce de antemano. No se usa un supervisor LLM que decida cada paso.
3. **Paralelismo:** macro ∥ noticias; renta fija ∥ equity; `Send` para valuar varios activos a la vez.
4. **Escenarios como contrato:** un objeto estructurado (nombre, probabilidad, trayectorias de inflación, tipo de cambio, tasas, actividad, supuestos) que consumen todos los agentes.
5. **Modelo según la tarea:** Flash-Lite para router, macro y noticias; un modelo más capaz para escenarios, equity y estratega.
6. **Revisión humana** (`interrupt`): aprobar los escenarios antes de valuar, y el borrador antes de la versión final.

Flujo del informe completo:

```
pedido → router → (macro ∥ noticias) → escenarios → (renta fija ∥ equity) → estratega → redactor → revisión
```

## Agregados incorporados al plan

| Agregado | Qué es | Dónde vive | Fase |
|---|---|---|---|
| Comparación con el consenso | Expectativas del REM (BCRA) y research externo frente a los datos y escenarios propios | Macro (dato) → Escenarios (diferencias) | A y D |
| Calendario de eventos | INDEC, licitaciones del Tesoro, BCRA; después, vencimientos y cupones de la cartera | Noticias (eventos públicos); renta fija (cartera) | A y C |
| Seguimiento de cartera | Posiciones, exposición por moneda e instrumento, duration, concentración | Base de datos + herramientas; lo usa el estratega | B |
| Registro de pronósticos | Guardar cada escenario con fecha y compararlo con los datos reales | Tabla en la base + herramienta de evaluación | B (tabla), D (uso) |
| Estrés y riesgo | Impacto de cada escenario (en especial el de estrés) sobre la cartera | Código; lo usa el estratega | D |
| Límites regulatorios | Límites de la CNV y del reglamento del FCI, chequeados antes de recomendar | Carpeta `politicas/` en código | D |

## Dependencias de datos

- **Precios de bonos y acciones:** API de PPI (cuenta propia), conexión propia de solo lectura. Alternativa gratuita anotada: Data912 (no oficial). La API oficial de BYMA es paga.
- **Balances locales:** CNV (Autopista de Información Financiera), generalmente en PDF → extracción.
- **Comparables de otro país:** según el país elegido.
- **EE. UU.:** API de FRED (clave gratuita): series y calendario de publicaciones.
- **Noticias:** Google News RSS (no oficial) + feeds de medios (Ámbito Economía y Finanzas).
- **Calendario:** feriados con la librería `holidays` + ajustes manuales; INDEC desde sus PDF semestrales; EE. UU. desde la API de FRED (clave gratuita, `FRED_API_KEY`). ISM y recaudación por regla de días hábiles. Pendientes: BCRA (REM, informe monetario), Secretaría de Finanzas (licitaciones), Ministerio de Economía (resultado fiscal, vencimientos), Fed (FOMC y minutas).
- **REM:** la API del BCRA (v4) solo publica la inflación esperada a 12 meses (variable 29, mediana). Tipo de cambio, tasas y PBI esperados: Excel mensual de tablas del REM (pendiente, fase D).

## Catálogo del BCRA (API v4)

- Unas 1000 variables; la mayoría son depósitos y préstamos por provincia y municipio.
- Hay nombres repetidos que difieren en unidad o frecuencia: BADLAR (7, 35, 138-140), TAMAR (44, 45, 135-137), base monetaria (15, 64, 71), tasa de política monetaria (160, 161). La búsqueda muestra unidad y frecuencia para distinguirlas.
- Variables clave:

| Id | Variable |
|---|---|
| 1 | Reservas internacionales |
| 4 | Tipo de cambio minorista |
| 5 | Tipo de cambio mayorista (A3500) |
| 27 | Inflación mensual |
| 28 | Inflación interanual |
| 29 | REM: inflación esperada a 12 meses (mediana) |
| 30 | CER |
| 31 | UVA |
| 40 | ICL |

## Orden de construcción

- **Fase A (en curso):** router + agente macro + agente noticias. Incluye la comparación con el REM (macro) y el calendario de eventos públicos: feriados ✓, publicaciones del INDEC ✓ de EE. UU. vía FRED ✓ y por regla (ISM, recaudación) ✓; faltan las manuales (BCRA, Tesoro, FOMC).
- **Fase B (en curso):** base de datos y carga de datos ✓ + fuente de precios (✓ PPI en vivo; falta la base de precios) + tablas de cartera (varias carteras, carga manual) y de pronósticos.
- **Fase C:** calculadoras de bonos (validables contra Excel propio) + agente renta fija + vencimientos y cupones de la cartera.
- **Fase D:** agente escenarios (contrato + REM + registro de pronósticos) → estratega con retornos esperados, estrés y límites regulatorios.
- **Fase E:** redactor + revisión humana.
- **Fase F:** equity (carga de balances, DCF, comparables).

## Pendientes técnicos (no urgentes)

- Mover `MAX_PUNTOS`, `PUNTOS_RESUMEN` y `ANIOS_VIGENCIA` de `tools/datos_macro.py` a `config.py`. Son parámetros ajustables que hoy no llevan guion bajo aunque se usan solo dentro de ese archivo. Se decidió posponerlo (11/11/2026); el momento natural es la fase B.

## Historial

- **11/11/2026:** arquitectura acordada; se decide arrancar por macro y noticias.
- **11/11/2026:** capa de datos de noticias lista (`conexiones/noticias.py`, `tools/noticias.py`: `buscar_noticias`, `titulares_recientes`).
- **11/11/2026:** agregados incorporados al plan por fases.
- **11/11/2026:** REM de inflación encontrado en la API (variable 29); búsqueda del BCRA con sinónimos (REM/expectativas, inflación/precios); resultados con unidad y frecuencia.
- **11/11/2026:** fase A, etapa 2: router + agentes macro y noticias en LangGraph. Cada agente es un subgrafo con su prompt y sus herramientas; la ruta "ambos" corre los dos en paralelo y un paso de síntesis los integra. Pendiente en fase A: calendario de eventos.

- **11/11/2026:** bases de datos locales en `datos/`, un archivo por tema: `feriados.db`, `publicaciones.db` y `cartera.db` (reservada para la fase B; no regenerable, requiere respaldo). Primera base: feriados, librería `holidays` (Argentina, bancos, BYMA, EE. UU., NYSE, bonos de EE. UU.) desde 2016 hasta el año próximo, más ajustes manuales en `calendarios/feriados_ajustes.toml`. Se descartó ArgentinaDatos por ahora. Herramientas `consultar_feriados` y `calcular_dia_habil` para macro y noticias. El calendario de BYMA de la librería empieza en 2026; antes se aproxima con el nacional. En 2026, la librería excluye de BYMA los días con fines turísticos (23/3, 10/7, 7/12): pendiente de confirmar.
- **11/11/2026:** carpetas renombradas: `clients` → `conexiones`, `storage` → `admin_datos`, `ingesta` → `carga_datos`.
- **11/11/2026:** catálogo de 24 publicaciones (`calendarios/publicaciones.toml`) con importancia y fuente: indec_pdf (IPC, EMAE, ICA, salarios, balanza de pagos), fred (CPI, empleo, PCE, PBI, ventas minoristas, PPI, JOLTS, Michigan, producción industrial), manual (REM, licitaciones, resultado fiscal, vencimientos de deuda en USD, informe monetario, FOMC, minutas) y regla (ISM manufacturero y de servicios, recaudación). Cargado el calendario del INDEC desde sus PDF semestrales (2.º sem. 2026 y 1.er sem. 2027): 351 publicaciones. Herramienta `consultar_publicaciones` para macro y noticias. El PDF del 1.er semestre 2027 tiene dos días de la semana mal (18/1 y 30/4): se usa la fecha.
- **11/11/2026:** fechas de EE. UU. desde la API de FRED (`conexiones/fred.py`, `carga_datos/publicaciones_fred.py`): 9 publicaciones, identificadas en el catálogo por su nombre exacto en FRED (`fred_release`) y con su hora habitual en ET. Se cargan desde el 1/1 del año pasado, incluidas las futuras programadas (`include_release_dates_with_no_data=true`). Si FRED falla, la base queda como estaba. La herramienta avisa qué códigos del catálogo no tienen fechas cargadas. Pendiente: manuales (REM, licitaciones, FOMC, etc.) y reglas (ISM, recaudación).
- **11/11/2026:** datos de EE. UU. para el agente macro: `consultar_fred` (serie con su último dato; las variaciones las calcula FRED con el parámetro `units`) y `buscar_serie_fred`. La descripción trae los ids más usados (CPI con y sin desestacionalizar, PCE, empleo, desempleo, PBI, tasa de la Fed, Tesoro a 2 y 10 años, etc.) para ahorrar búsquedas. `ejecutar_python` también puede usar `fred.obtener_serie`. Motivo: ante "¿cuál fue la última inflación de EE. UU.?", el agente tenía la fecha del próximo CPI pero no el dato, y usaba `ejecutar_python` para escribir un mensaje; el prompt ahora lo prohíbe.
- **11/11/2026:** publicaciones por regla de días hábiles (`carga_datos/publicaciones_regla.py`): ISM manufacturero (1.er día hábil, NYSE), ISM de servicios (3.er día hábil, NYSE) y recaudación de ARCA (1.er día hábil, AR). El ISM no publica en Viernes Santo ni el 2 de enero (campo `excluir`): con eso, las 24 fechas oficiales de 2026 coinciden. La recaudación se verificó con septiembre (1/10) y octubre (2/11) de 2026. Cubre del año pasado al último año con feriados. Más adelante: bajar las fechas de una fuente oficial. Pendientes: las manuales.
- **12/11/2026:** fase B, paso 1: precios de mercado desde la API de PPI. Se descartó la librería oficial `ppi-client` (sin licencia ni repositorio público, solo sdist, instala pytest/flake8/vcrpy/signalr como obligatorias e incluye órdenes y transferencias) y se escribió `conexiones/ppi.py`, de solo lectura, con los mismos endpoints: LoginApi (token en memoria, se renueva ante un 401), SearchInstrument, Current, Search (histórico) y Bonds/Estimate. Por decisión de Agustin, no se leen posiciones ni movimientos de la cuenta: la cartera se carga a mano. Herramientas `consultar_precio` y `calcular_bono` para el agente macro. `ejecutar_python` corre sin las claves de PPI ni de Gemini (`FINIANZ_SUBPROCESO`). Diagnóstico: `python -m conexiones.ppi AL30`. Pendiente: base de precios con catálogo de instrumentos, cartera y pronósticos.
- **12/11/2026:** seguridad de `ejecutar_python`: quitar las claves del entorno no impedía leer el `.env`. Se agregó `tools/guardia.py`, que se inyecta en el código del agente y registra un *audit hook* (no se puede desactivar): bloquea leer archivos del proyecto que no sean código (`.env`, `datos/`, `calendarios/`) y archivos del usuario fuera de la instalación de Python; escribir, borrar o renombrar fuera de la caché; lanzar procesos; ctypes; sqlite3; y conexiones a sitios que no sean las APIs de datos (solo IPs resueltas desde esos sitios). Probado contra 13 acciones peligrosas (todas bloqueadas) y con uso normal (math, pandas, numpy, caché, consulta HTTP permitida). Límite: no es un sandbox total; la protección fuerte sigue siendo `CONFIRMAR_CODIGO=true` o un contenedor. Pendiente: averiguar si PPI permite claves de solo lectura.
- **12/11/2026:** herramienta `inflacion_anualizada` ((1 + mensual)^12 − 1 del último mes y del promedio geométrico de 3 y 6 meses). Motivo: ante "inflación anualizada", el agente usaba `ejecutar_python` (y con `CONFIRMAR_CODIGO=true` pedía autorización) o preguntaba qué fórmula usar. Las recetas del REM y de "cómo viene la inflación" ahora la usan.

## Estructura del código (fase A)

```
graph/
  state.py      Estado (conversación + informes del turno) y EstadoAgente (loop interno)
  nodes.py      modelos con respaldo, prompts, nodo "modelo"
  errores.py    errores temporales y política de reintentos
  agente.py     fábrica de agentes (subgrafo modelo ↔ herramientas)
  router.py     router con salida estructurada: macro | noticias | ambos | general
  responder.py  respuesta final: informe directo, síntesis o respuesta general
  builder.py    grafo principal
prompts/        macro.md, noticias.md, router.md, sintesis.md, general.md
tools/          HERRAMIENTAS_MACRO (datos + calendario + python), HERRAMIENTAS_NOTICIAS (noticias + calendario)
admin_datos/        db.py (una base SQLite por tema en datos/), feriados.py (consultas y días hábiles), publicaciones.py
carga_datos/        feriados.py (holidays + ajustes), publicaciones_indec.py (PDF del INDEC), publicaciones_fred.py (API de FRED), publicaciones_regla.py (días hábiles), catalogo.py
datos/          feriados.db, publicaciones.db, cartera.db (no se suben a git)
calendarios/    feriados_ajustes.toml, publicaciones.toml (catálogo), indec/ (PDF semestrales)
actualizar.py   recarga la base
```
