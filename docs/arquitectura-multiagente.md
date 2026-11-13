# Finianz – Arquitectura multiagente

Acordada el 11/11/2026. Última actualización: 11/11/2026 (feriados y base local).

## Principio

No todo es un agente:

- **Agentes** donde hace falta criterio.
- **Código** para cálculos que tienen una forma correcta de hacerse.
- **Procesos programados** (sin IA) para traer datos que se repiten.
- **De afuera, solo datos:** las fuentes externas aportan datos (precios, series, fechas); todos los cálculos los hace el proyecto, salvo excepción explícita de Agustin.

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
- **Fase B (en curso):** base de datos y carga de datos ✓ + fuente de precios (✓ PPI) + base propia de precios ✓ + tablas de cartera (varias carteras, carga manual) y de pronósticos.
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
- **12/11/2026:** herramienta `inflacion_anualizada` ((1 + mensual)^12 − 1 del último mes y del promedio geométrico de 3 y 6 meses). Motivo: ante "inflación anualizada", el agente usaba `ejecutar_python` (y con `CONFIRMAR_CODIGO=true` pedía autorización) o preguntaba qué fórmula usar. Las recetas del REM y de "cómo viene la inflación" ahora la usan. Además, `inflacion_acumulada` devuelve la acumulada anualizada ((1 + acumulada)^(12/n) − 1) cuando el período tiene menos de 12 meses: el agente copiaba la acumulada a mano en `ejecutar_python` para anualizarla. El prompt ahora prohíbe escribir en el código números devueltos por otra herramienta.
- **12/11/2026:** principio de diseño (decisión de Agustin): de las fuentes externas se traen solo datos; todos los cálculos los hace el proyecto, salvo excepción explícita. Se quitó la calculadora de bonos de PPI (`calcular_bono`, endpoint Bonds/Estimate); de PPI se usan solo precios actuales e históricos. La calculadora propia va en la fase C (validable contra el Excel de Agustin). Pendiente por el mismo principio: calcular en código las variaciones que hoy calculan FRED (`units`) y datos.gob.ar (`representation_mode`).
- **12/11/2026:** base propia de precios (`datos/precios.db`, no regenerable del todo: respaldar). Tablas `instrumentos` (activos seguidos: ticker, tipo, moneda, ISIN, mercado, fuente, desde cuándo) y `precios` (ticker, plazo, fecha, OHLC, volumen, fuente). Cada activo consultado se registra y se baja todo su histórico; después solo los días faltantes (`carga_datos/precios.py`). Solo cierres de días terminados (el del día, después de las 18 h). `consultar_precio` lee el histórico de la base y el precio del momento en vivo; si PPI falla, usa lo guardado. `actualizar.py` suma los cierres de todos los seguidos.
- **12/11/2026:** diseño acordado para las calculadoras (fase C): (1) ficha técnica de cada bono como datos (cronograma, cupones, base de cálculo, ajuste CER/TAMAR/DL, rezago, capitalización); (2) pocos generadores de flujos por familia (tasa fija, CER, variable, dólar linked, cupón cero/capitalizable); (3) un único motor financiero (TIR, duration, MD, convexidad, valor técnico, interés corrido, paridad). Validación por capa contra el Excel de Agustin. Con la base de precios permite TIR histórica.
- **12/11/2026:** nueva capa `calculos/` (funciones puras, sin acceso externo). `calculos/series.py` calcula las variaciones (período anterior, interanual, anualizada y acumulada en el año) sobre los niveles; detecta la frecuencia por la distancia entre fechas. FRED y datos.gob.ar ahora solo entregan niveles (se quitaron `units` y `representation_mode`): aplica el principio "de afuera, solo datos". `ejecutar_python` tiene `transformar(serie, modo)`. El motor de bonos de la fase C va en esta capa. Ajuste tras la primera prueba real: el CPI de octubre de 2025 no existe (cierre del gobierno de EE. UU.; el BLS no publica la interanual de octubre de 2026). Las variaciones contra el período anterior exigen períodos consecutivos (antes, noviembre de 2025 se comparaba contra septiembre) y las herramientas avisan qué fechas no tienen variación calculable. `inflacion_anualizada` acepta `pais='US'` (CPI desestacionalizado, variaciones propias, promedio geométrico; si falta un mes en la ventana, no la calcula). Motivo: ante "¿y anualizado?" después de hablar de EE. UU., el agente usaba la de Argentina, y para EE. UU. copiaba números en `ejecutar_python` y promediaba tasas anualizadas. El prompt suma una sección "Seguí el hilo de la conversación" y la regla de explicar los AVISO de las herramientas. El AVISO nombra el dato que falta (ej.: el CPI de 2025-10-01) y aclara que no es una demora: el agente había interpretado que la interanual de octubre saldría en el informe siguiente.
- **12/11/2026:** fase C, paso 1 (decisiones de Agustin: empezar por CER; TIR efectiva anual base 365 desde la liquidación; fichas armadas por Claude y revisadas por Agustin; validación contra su Excel). Motor `renta_fija/calculadoras/motor.py` (TIR por Newton con respaldo de bisección, duration, MD, convexidad, residual, valor técnico, paridad), probado contra resultados analíticos. Calculadora de familia `renta_fija/calculadoras/cer.py`: coeficiente = CER(liquidación − 10 hábiles) / CER inicial; flujos reales; precio real = precio / coeficiente → TIR real. Regla confirmada en la norma (Res. Conj. 32/2026): CER entre los 10 días hábiles anteriores a la emisión y los 10 anteriores a cada pago. Fichas en `renta_fija/fichas/cer.toml`: 15 cupón cero (Boncer TZX y LeCER X) con su CER inicial (fuente: calculador de BONCER de sinelefantesblancos.com.ar), `revisado = false` hasta validarlas. Herramienta `calcular_bono` (liquidación T+1 BYMA, precio en vivo o cierre de una fecha). Abierto: con qué calendario se cuentan los 10 hábiles (hoy bancario: el 6/11, Día del Bancario, cuenta como inhábil). Próximos: TX28 y TX31 (con cupón), duales CER/TAMAR (TXMJ8, TXMD8, TXMD9, TXMJ0), DICP/PARP/CUAP.
- **12/11/2026:** organización por tema (decisión de Agustin): todo lo de bonos en `renta_fija/` (`fichas/` con los TOML y `prospectos/` para los PDF, `calculadoras/` con `motor.py` y una por familia, `leer_fichas.py`). Quedan afuera, por ser compartidos: `tools/bonos.py` (todas las herramientas del agente viven en `tools/`), `conexiones/` y `calculos/series.py` (macro). En la fase F, `renta_variable/` con la misma forma.
- **12/11/2026:** requisito de Agustin: `renta_fija/calculadoras/motor.py` es el único motor para todas las familias (CER, tasa fija, TAMAR y duales, hard dollar); cada familia solo aporta su calculadora de flujos. Para cuando se sumen: agregar al motor el interés corrido por base de cálculo (30/360, real/365, real/real; la base la indica la ficha) y las tasas equivalentes (TIR efectiva ↔ TNA, TEM, TEA).
- **12/11/2026:** calculadora CER cero cupón reescrita con las definiciones de Agustin (`docs/convenciones-renta-fija.md`): plazo residual, duration = plazo/365, ratio = CER corriente (del día de liquidación) / CER inicial, TNA real, TEA real y carry mensual = inflación + TNA/12. Fichas de `cer.toml` con los datos de su Excel (19 bonos, incluidos los duales TXM solo por su parte CER); TZXD8 sin validar. Pruebas automáticas en `tests/test_renta_fija_cer.py` (reproducen el Excel). Días hábiles: calendario bancario (validado). Feriados cargados hasta 20 años adelante (`FERIADOS_ANIOS_ADELANTE`) para cubrir vencimientos; las publicaciones por regla siguen hasta el año próximo. La serie del CER en el BCRA es la id 30 ("coeficiente de estabilización de referencia"); `buscar_variables` reconoce "CER" como sinónimo.
- **12/11/2026:** corrección de definición (Agustin): el CER corriente es el del décimo día hábil anterior a la liquidación, no el del día de liquidación (detectado con el TZXO7 a 103,35: el Excel usaba el CER del BCRA del 30/10). Días hábiles del rezago con el calendario nacional oficial (decisión de Agustin): el 9/11/2026 es feriado, así que para la liquidación del 13/11 corresponde el CER del 29/10. Pruebas nuevas para la fecha del CER corriente y el caso del TZXO7.
- **13/11/2026:** calculadora de CER con cupón (`renta_fija/calculadoras/cer_cupon.py`, ficha del TX28 en `fichas/cer_cupon.toml` con el cronograma de pagos), a partir del Excel de Agustin con correcciones acordadas (errores de arrastre en la última fila y en la TIR nominal; una sola convención de fechas: corridas al día hábil siguiente). Al motor se le sumaron el conteo 30/360 (DAYS360 de Excel), el interés corrido, las tasas equivalentes (TNA n días, TEM) y la sensibilidad (PV01, DD). Días hábiles del CER y de los pagos con el calendario de BYMA (decisión de Agustin). Current yield sobre el cupón actual y cash yield a 12 meses, sobre el precio clean. Pendiente: proyección del CER para la parte nominal.
- **13/11/2026:** TX31 cargado desde sus condiciones de emisión (imagen en `renta_fija/fichas/prospectos/`). El CER inicial pasa a ser opcional en las fichas con cupón: si falta, la herramienta lo toma del BCRA para el 10.º día hábil anterior a la emisión y lo aclara en la respuesta.
- **13/11/2026:** 7/12/2026 feriado en BYMA (ajuste). Calculadoras de tasa fija (`renta_fija/calculadoras/tasa_fija.py`, fichas en `tasa_fija.toml`): Lecap/Boncap capitalizables (pago final con la TEM de emisión) y Bonte con cupón TY30P (reusa la calculadora con cupón con ratio 1). Correcciones a la planilla de Agustin: vencimientos de T15E7 y T31Y7; en el TY30P, duration/convexidad con la TIR de mercado y base 365. Decisiones: TNA semestral exacta para todos los bonos, TEM de 30 días corridos, cupón 30/360 por período. Para más adelante: curva teórica de tasa fija, letras a descuento, proyección del CER y extracción de las condiciones de emisión desde los prospectos.
- **13/11/2026:** nueva base `datos/series.db` (tabla `series`: variable, fecha, valor, fuente), con `admin_datos/series.py` y `carga_datos/series.py`. Guarda el CER diario del BCRA desde 2002 (carga completa de a un año por consulta, después incremental hasta 60 días adelante) y la actualiza `actualizar.py`. La calculadora de bonos lee de ahí el CER corriente y el inicial (10.º día hábil anterior a la emisión); las fichas ya no traen `cer_inicial` (leer_fichas lo rechaza). Pensada para sumar TAMAR, A3500 y UVA. T15E7, T31Y7 y TX31 pasan a revisados.
- **13/11/2026:** TAMAR de bancos privados en la base de series (BCRA id 44, % TNA; la 45 es la TEA, elegida la TNA por Agustin). Base para las calculadoras TAMAR.
- **13/11/2026:** calculadora TAMAR (`renta_fija/calculadoras/tamar.py`, fichas en `tamar.toml`): ventana de 10 días hábiles, proyección con el promedio de los últimos 5 publicados, TEM base 32 días, pago final 30/360 y luego como Lecap; spread = TNA 30 d − TAMAR de referencia. `leer_fichas` admite varias fichas por ticker si son de familias distintas (duales): `fichas_de()`, `todas()`, `ficha(ticker, familia)`. `calcular_bono` muestra una sección por ficha. `admin_datos/feriados.dias_habiles_entre()`.
- **13/11/2026:** error 400 del BCRA: la carga de series pide solo fechas entre la primera y la última publicadas (listado oficial). El prompt macro pide informar los errores de `calcular_bono` sin rellenar.
- **13/11/2026:** hard dollar (`renta_fija/calculadoras/hard_dollar.py`, fichas en `hard_dollar.toml` con `tramos` step-up): AL30 y GD30. Motor: funciones `*_30_360` (TIR nominal periódica 30/360, duration, modificada, convexidad). La herramienta toma precios D, C y en pesos de PPI y la curva de Treasuries constant maturity de FRED (en vivo, con caché).
- **13/11/2026:** hard dollar completo: AL29/GD29, AL35/GD35, AE38/GD38, AL41/GD41 y GD46 (sin par; `par` pasa a ser opcional). AL30/GD30 validados.
- **13/11/2026:** dollar linked del Tesoro (`renta_fija/calculadoras/dolar_linked.py`, fichas en `dolar_linked.toml`, familia `dolar_linked_bullet`): precio en dólares con el A3500 del día de concertación (`_a3500` en tools/bonos.py estima con el día hábil anterior si no se publicó), luego como una Lecap con pago final 100. A3500 (BCRA id 5) en la base de series. Pendientes: breakeven entre curvas y DL corporativos con cupones.
- **13/11/2026:** breakevens: `renta_fija/calculadoras/breakeven.py` (puro: interpolar sin extrapolar, cruzar curvas, forwards, TAMAR implícita despejando la cuenta del bono) y herramienta `calcular_breakevens` en `tools/breakevens.py` (arma las curvas a precio de mercado con las calculadoras; excluye duales). Pendiente: comparación con el REM.
- **13/11/2026:** proyección del CER: `renta_fija/calculadoras/proyeccion_cer.py` (regla del BCRA del 16 al 15 en días corridos, camino mensual + anual, inflación desde niveles de CER interpolando en meses de CER, rendimiento nominal) y herramienta `proyectar_cer` (fuentes breakeven, escenario y mensual). Escenarios en `renta_fija/escenarios/inflacion.toml`. `breakevens._curvas` acepta un filtro de familias. Pendiente: REM.

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
tools/          HERRAMIENTAS_MACRO (datos + precios + calendario + python), HERRAMIENTAS_NOTICIAS (noticias + calendario); guardia.py
calculos/       series.py (variaciones propias)
renta_fija/     fichas/ (cer.toml + prospectos/), calculadoras/ (motor.py, cer.py), leer_fichas.py
conexiones/     http.py, bcra.py, series_tiempo.py, fred.py, ppi.py (solo lectura), noticias.py
admin_datos/        db.py (una base SQLite por tema en datos/), feriados.py (consultas y días hábiles), publicaciones.py, precios.py
carga_datos/        feriados.py (holidays + ajustes), publicaciones_indec.py (PDF del INDEC), publicaciones_fred.py (API de FRED), publicaciones_regla.py (días hábiles), precios.py (PPI, incremental), catalogo.py
datos/          feriados.db, publicaciones.db, precios.db, cartera.db (no se suben a git)
calendarios/    feriados_ajustes.toml, publicaciones.toml (catálogo), indec/ (PDF semestrales)
actualizar.py   recarga la base
```
