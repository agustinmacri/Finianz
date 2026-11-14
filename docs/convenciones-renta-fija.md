# Convenciones de renta fija

Definiciones de Agustin para calcular las variables de cada bono. **El código las respeta tal cual**: cualquier cambio se discute y se decide antes de programarlo, y queda registrado acá.

Validación: `python -m tests.test_renta_fija_cer` reproduce los 19 bonos del Excel de Agustin (`ejemplo_Cer.xlsx`, 12/11/2026) `python -m tests.test_renta_fija_cer_cupon` el TX28 (`ejemplo_tx28.xlsx`, 13/11/2026) y `python -m tests.test_renta_fija_tasa_fija` las Lecap/Boncap y el TY30P (`tasa_fija.xlsx`, 13/11/2026).

## Generales

- Los precios y los cálculos siempre se realizan en **T+1**, salvo que se indique lo contrario.
- Precio por cada 100 de valor nominal original, para todos los bonos (uniformidad). Se usa el precio como cotiza en pantalla. En los bonos en pesos no se distingue precio clean y dirty (decisión de Agustin, 14/11/2026): el precio sin el interés corrido solo se usa por dentro para el current yield y el cash yield, y no se muestra. La distinción clean/dirty es solo de los hard dollar, que en el exterior cotizan clean.
- Días hábiles: calendario de BYMA (decisión de Agustin, 13/11/2026), para la liquidación, el rezago del CER y las fechas de pago. Ej.: el 9/11/2026 y el 10/11/2026 fueron inhábiles.
- Fichas: solo condiciones de emisión (fechas, tasas, cronograma). Los valores de índices (CER) salen de la base propia de series, cargada desde la fuente oficial (decisión de Agustin, 13/11/2026).
- Fechas de pago: si caen en un día inhábil, se corren al día hábil siguiente, y esa fecha se usa en todos los cálculos (TIR, duration, convexidad).

## Bonos CER que no pagan intereses ni amortizaciones

Boncer cero cupón (TZX), LeCER (X) y la parte CER de los duales CER/TAMAR (TXM).
Código: `renta_fija/calculadoras/cer.py`. Fichas: `renta_fija/fichas/cer.toml`.

| Variable | Definición (Agustin) |
|---|---|
| Plazo residual | Días corridos entre la liquidación y el vencimiento |
| Duration | Plazo residual / 365 |
| CER final | CER correspondiente al décimo día hábil anterior a la fecha de vencimiento |
| CER inicial (base) | CER correspondiente al décimo día hábil anterior a la liquidación inicial (emisión) del bono. Se toma de la base propia de series (`datos/series.db`, CER del BCRA): las fichas no traen valores de CER |
| CER corriente | CER del décimo día hábil anterior a la liquidación de la operación (operación del 12/11/26 → liquidación 13/11/26 → CER del 28/10/26) |
| Ratio actual | CER corriente / CER inicial |
| TNA real | (ratio actual / precio − 1) × 365 / plazo residual |
| TIR (TEA real) | Capitalización de la TNA por el plazo remanente, base 365: (1 + TNA × plazo / 365) ^ (365 / plazo) − 1 |
| Carry mensual | Inflación corriente (último dato de inflación mensual publicado, INDEC vía BCRA) + TNA del bono mensualizada (TNA / 12). Suma simple |
| Valor técnico | 100 × CER corriente / CER inicial (el ratio, en pesos por 100 VN) |
| Paridad | Precio / valor técnico |
| Duration modificada | Duration / (1 + TIR) |
| Convexidad | Duration × (duration + 1) / (1 + TIR)² |

Notas de implementación:
- La TEA real coincide con la TIR del motor común (`renta_fija/calculadoras/motor.py`) para un flujo único: lo verifica una prueba.
- La fecha del CER final es informativa (no entra en los cálculos). En TXMJ9 y TXMJ0 difiere un día del Excel por feriados de 2029 y 2030 aún no decretados.

## Bonos CER con cupón y amortización

TX28 y TX31. Código: `renta_fija/calculadoras/cer_cupon.py`. Fichas: `renta_fija/fichas/cer_cupon.toml` (con el cronograma de pagos).
Todo por 100 VN original y en términos reales (sin el ajuste CER), salvo los precios nominales.

| Variable | Definición |
|---|---|
| Ratio | CER corriente / CER inicial (igual que en los cero cupón; ambos de la base de series) |
| Residual | 100 − amortizaciones pagadas hasta la liquidación |
| Cupón de cada pago | Residual anterior × tasa anual × días 30/360 del período / 360 (semestre completo: × 180/360). El primer período empieza en la emisión |
| Interés corrido | Residual × tasa × días 30/360 (DAYS360 de Excel, método US) desde el último cupón / 360 |
| Valor técnico | Residual + interés corrido |
| Precio real | Precio de mercado / ratio |
| Paridad | Precio real / valor técnico |
| TIR real | Tasa efectiva anual (base 365) que iguala los flujos futuros reales, en las fechas corridas, al precio real (como el XIRR de Excel) |
| TNA semestral | ((1 + TIR)^(1/2) − 1) × 2 (capitalización semestral exacta; para todos los bonos) |
| TNA 30 d | ((1 + TIR)^(30/365) − 1) × 365/30 |
| TEM | (1 + TIR)^(30/365) − 1 |
| Duration | Macaulay, en años |
| Duration modificada | Duration / (1 + TIR) |
| Convexidad | Σ flujo × t(t+1) / (1 + TIR)^(t+2) / precio real |
| PV01 / DD | Precio real × (−MD × Δ + CVX × Δ² / 2), con Δ = 1 pb y 100 pb |
| Current yield | Cupón actual (tasa × residual) / (precio real − interés corrido) |
| Cash yield | (Cupones + amortizaciones de los próximos 12 meses) / (precio real − interés corrido) |

Correcciones al Excel del TX28 acordadas el 13/11/2026: la fila del último cupón usaba la emisión en lugar de la liquidación; la TIR nominal dejaba afuera el último flujo; algunas sumas tenían rangos desplazados; la duration y la convexidad usaban fechas sin correr mientras la TIR usaba fechas corridas (ahora todo con fechas corridas); el current yield mezclaba unidades.

## Tasa fija

Código: `renta_fija/calculadoras/tasa_fija.py`. Fichas: `renta_fija/fichas/tasa_fija.toml`.

**Capitalizables (Lecap "S", Boncap "T"):**

| Variable | Definición |
|---|---|
| Pago final | 100 × (1 + cupón de licitación) ^ (días 30/360 entre emisión y vencimiento / 30). El cupón de licitación es la tasa mensual capitalizable de emisión (campo `cupon` de la ficha) |
| Plazo residual | Días corridos entre la liquidación y el vencimiento |
| Duration | Plazo residual / 365 |
| TNA | (pago final / precio − 1) × 365 / plazo residual |
| TEA (TIR) | (1 + TNA × plazo / 365) ^ (365 / plazo) − 1 |
| TEM | (pago final / precio) ^ (30 / plazo) − 1 (30 días corridos, base 365) |

**Con cupón (Bonte, ej. TY30P):** las mismas variables que los CER con cupón, en pesos (sin ratio).

Correcciones a la planilla del 13/11/2026: vencimientos del T15E7 (15/01/2027, no 17/01) y del T31Y7 (31/05/2027, no 30/05), confirmados por Agustin el 13/11/2026. En el TY30P, la duration, la convexidad y el PV01 se calculaban con la tasa fija del "rate mover" (28,5974% TNA) en lugar de la TIR de mercado, y en base 360; ahora con la TIR de mercado y base 365. Emisión del TY30P: 04/06/2025.

## TAMAR

Bonos TAMAR capitalizables del Tesoro (TMF27, TML27, TMG27, TMF28, TMG28) y la pata TAMAR de los duales: TTD26 (contra tasa fija) y TXM (contra CER). Código: `renta_fija/calculadoras/tamar.py`. Fichas: `renta_fija/fichas/tamar.toml`. Los duales CER/TAMAR tienen una ficha en `cer.toml` y otra en `tamar.toml`, y la herramienta los muestra calculados de las dos formas (decisión de Agustin, 13/11/2026).

| Variable | Definición |
|---|---|
| TAMAR | TAMAR de bancos privados en % TNA (BCRA, variable 44), de la base de series |
| Ventana | Del 10.º día hábil anterior a la emisión al 10.º día hábil anterior al vencimiento (calendario de BYMA) |
| TAMAR del bono | Promedio simple de la TAMAR de los días hábiles de la ventana. Los días hábiles todavía no publicados se estiman con el promedio simple de los últimos 5 días hábiles publicados |
| TEM del bono | ((1 + (TAMAR del bono + margen) × 32/365) ^ (365/32)) ^ (1/12) − 1 (base 32 días, según las condiciones de emisión) |
| Pago final teórico | 100 × (1 + TEM) ^ (días 30/360 entre emisión y vencimiento / 30) |
| Plazo residual, duration, TNA, TEA (TIR), TEM 30 d | Como las Lecap/Boncap |
| TNA 30 d | ((1 + TIR) ^ (30/365) − 1) × 365/30 |
| Spread sobre TAMAR | TNA 30 d − promedio de la TAMAR de los últimos 5 días hábiles publicados. Se usa la TNA de 30 días y no la del plazo porque la TAMAR es una tasa a 30 días |

Correcciones a la planilla del 13/11/2026: la serie proyectada terminaba el 10/01/2029, así que en TXMJ9, TXMD9 y TXMJ0 el promedio dejaba afuera el resto de la ventana (TXMD9 y TXMJ0 daban la misma TEM); ahora se proyecta hasta el final de la ventana. La proyección usaba valores fijos (24,22% y 24%) y el spread restaba un 24,19% cargado a mano; ahora ambos usan el promedio de los últimos 5 días hábiles publicados. La TNA 30 d pasa de NOMINAL(TEA; 12) a la de 30 días corridos (menos de 3 pb de diferencia).

## Hard dollar

Bonares (ley argentina, AL) y Globales (ley Nueva York, GD). Bonares AL29, AL30, AL35, AE38, AL41 y Globales GD29, GD30, GD35, GD38, GD41, GD46 (el GD46 no tiene par de ley argentina). Cronogramas del Anexo II del Decreto 676/2020; los Bonares con las mismas condiciones que el Global del mismo año. Código: `renta_fija/calculadoras/hard_dollar.py`. Fichas: `renta_fija/fichas/hard_dollar.toml` (cupón step-up en `tramos`, cronograma en `pagos`).

| Variable | Definición |
|---|---|
| Precio | Por 100 VN original, en dólares, con cupón corrido. Se calcula con el MEP (ticker D) y con el cable (ticker C) |
| Cupón de cada pago | Residual × tasa vigente al inicio del período × días 30/360 del período / 360 |
| Interés corrido | Residual × tasa vigente × días 30/360 desde el último cupón / 360 |
| Valor técnico, paridad | Como los bonos con cupón |
| Precio clean | (Precio − interés corrido) / residual × 100: por cada 100 de valor residual (definición de Agustin, 14/11/2026) |
| TNA | Nominal anual con capitalización semestral, base 30/360: precio = Σ flujo / (1 + TNA/2) ^ (días 30/360 / 180) (convención de mercado; solo para esta familia) |
| TIR (TEA) | (1 + TNA/2)² − 1 |
| Duration / modificada / convexidad | Macaulay en años con esa tasa; modificada = duration / (1 + TNA/2) |
| Current yield, cash yield | Cupón vigente × residual / clean; flujos de 12 meses / clean |
| Spread contra Treasuries | TNA semestral − rendimiento del Treasury constant maturity (FRED, también semestral) interpolado linealmente a la duration del bono, en pb |
| Spread ley NY − ley AR | TNA del Global − TNA del Bonar del mismo vencimiento, con el mismo tipo de precio (MEP con MEP, cable con cable) |
| Dólar implícito | Precio en pesos / precio en dólares: MEP con el D, CCL con el C |

Fechas de pago corridas al día hábil siguiente, como en el resto de los bonos (la convención de mercado suele contar el 30/360 hasta la fecha teórica: la diferencia es de uno o dos días por flujo).

## Dollar linked

Valor nominal en dólares; se suscriben, cotizan y pagan en pesos al tipo de cambio. Por ahora los del Tesoro, que son bullet: D30N6, D15E7, D31M7, TZV27, TZV28, TZVD8. Código: `renta_fija/calculadoras/dolar_linked.py`. Fichas: `renta_fija/fichas/dolar_linked.toml`.

| Variable | Definición (Agustin) |
|---|---|
| Precio en dólares | Precio en pesos por 100 VN / A3500 del día de concertación de la operación (no del de liquidación). Intradiario, hasta que se publica (alrededor de las 15 h), se estima con el A3500 del día hábil anterior |
| Pago | 100 dólares por 100 VN al vencimiento, en pesos al tipo de cambio de pago del prospecto (A3500, BNA vendedor o un promedio de días, según cada bono) |
| TNA | (100 / precio en dólares − 1) × 365 / plazo residual (actual/365, distinto de los hard dollar) |
| TIR | (1 + TNA × plazo / 365) ^ (365 / plazo) − 1 |
| Duration, TEM | Plazo / 365; TEM de 30 días corridos |

## Breakevens entre curvas

Código: `renta_fija/calculadoras/breakeven.py` (cuentas) y `tools/breakevens.py` (herramienta `calcular_breakevens`). Decisiones de Agustin, 13/11/2026.

- **Emparejamiento:** cada bono de la curva indexada se compara con la otra curva interpolada linealmente a su duration en días (en los bonos sin cupón, el plazo residual). Fuera del rango de la otra curva no se extrapola.
- **Tasas:** TEA contra TEA (la TIR de los hard dollar pasada a TEA). Breakeven anual, mensual = (1 + anual)^(1/12) − 1, y acumulado hasta el vencimiento.
- **Rezagos:** plazo tal cual, sin ajustar por el rezago del CER ni por el tipo de cambio de pago de los dollar linked.
- **Forwards:** entre vencimientos consecutivos, (1 + acumulado del más largo) / (1 + acumulado del más corto) − 1.
- **Curvas:** tasa fija = Lecap/Boncap y TY30P; CER = cero cupón y TX28/TX31; dollar linked del Tesoro; Bonos TAMAR (TMF27, TML27, TMG27, TMF28, TMG28); Bonares en MEP. Se excluyen los duales (tienen opcionalidad).

| Breakeven | Fórmula | Nivel implícito |
|---|---|---|
| Inflación (CER vs tasa fija) | (1 + TEA tasa fija) / (1 + TEA real CER) − 1 | Inflación acumulada al vencimiento |
| Devaluación (dollar linked vs tasa fija) | (1 + TEA tasa fija) / (1 + TEA en USD del DL) − 1 | A3500 implícito = A3500 de hoy × (1 + acumulado) |
| Tipo de cambio real (dollar linked vs CER) | (1 + TEA real CER) / (1 + TEA en USD del DL) − 1 (positivo = depreciación real) | Acumulado |
| Brecha (dollar linked vs Bonares en MEP) | (1 + TEA del DL) / (1 + TEA del Bonar en MEP) − 1 | Brecha implícita = brecha de hoy (MEP implícito AL30/AL30D / A3500) × (1 + acumulado). Incluye el riesgo de crédito en dólares del Bonar |
| TAMAR (Bonos TAMAR vs tasa fija) | TAMAR promedio de los días por publicar que hace rendir al bono TAMAR la TEA de la tasa fija a su plazo | Contra la TAMAR actual (últimos 5 días) |

**Comparación con el REM** (último relevamiento cargado, mediana; decisión de Agustin, 14/11/2026):
- Inflación: para cada CER, la inflación anual que espera el REM entre la liquidación y el mismo plazo del breakeven (cada mes calendario pesa por la fracción de días que cae en el período; los meses ya publicados con el dato del INDEC). Breakeven − REM en puntos porcentuales: positivo = el mercado descuenta más inflación que el REM.
- Devaluación: el A3500 implícito de cada dollar linked contra el tipo de cambio del REM a la misma fecha, interpolado en forma geométrica entre el A3500 de hoy y los promedios mensuales del REM (ubicados a mitad de mes; también su dato a 12 meses y el de diciembre de cada año). Solo hasta donde llega el REM.
- TAMAR: la TAMAR implícita de los días por publicar contra el promedio de la TAMAR del REM esos mismos días, y la TEA del bono TAMAR si se cumple el REM. TAMAR del REM (decisión de Agustin, 14/11/2026): la mediana mensual en los meses que trae el relevamiento y, para todos los meses siguientes, su valor "próximos 12 meses" sin modificar. Los valores anuales (diciembre) no se usan.

## Proyección del CER y rendimiento nominal de los CER

Código: `renta_fija/calculadoras/proyeccion_cer.py` y herramienta `proyectar_cer` (`tools/proyeccion_cer.py`). Escenarios: `renta_fija/escenarios/inflacion.toml`.

**Regla del CER** (verificada con la serie del BCRA el 13/11/2026: factor diario 1,0006073377 del 16/10 al 15/11 = 1,9% de septiembre en 31 días; 1,0007256462 del 16/11 al 15/12 = 2,2% de octubre en 30 días):
- La inflación del mes m se aplica del 16 del mes m+1 al 15 del mes m+2, inclusive.
- Factor diario = (1 + inflación) ^ (1 / días corridos del período). El CER crece todos los días, hábiles o no.
- CER del 15 de m+2 = CER del 15 de m+1 × (1 + inflación de m). La inflación publicada de cada mes se lee de la propia serie.

**Camino de inflación** (decisión de Agustin): mes a mes donde la fuente lo trae (el año corriente y parte del próximo); para los años siguientes, inflación anual (diciembre contra diciembre) pasada a mensual. Los meses de un año sin dato mensual se completan con una misma tasa para que el año cierre en la inflación anual. Los años sin dato usan la última inflación anual disponible.

**Fuentes:**
- `breakeven`: CER implícito en la fecha del CER final de cada CER cero cupón = precio × (1 + TEA de la tasa fija a su plazo) ^ (plazo/365) × CER inicial / 100. Entre esos puntos, inflación mensual constante (interpolación del logaritmo del CER en meses de CER). Después del último bono, se repite la última inflación mensual.
- `escenario:<nombre>`: los escenarios del archivo, con inflaciones mensuales y anuales.
- `mensual:<tasa>`: inflación mensual plana, en porcentaje ("2%", "2" o "1.66"); una fracción menor a 0,2 ("0.02") también se acepta.
- `rem`: último relevamiento del REM cargado (Excel del BCRA en `fuentes/rem/`, base `datos/rem.db`), mediana. Los meses que trae mes a mes se usan tal cual; los demás meses de cada año se completan para que el año cierre en la inflación anual del REM (diciembre contra diciembre); después del último año del REM se repite su anual. Los meses ya publicados usan el dato del INDEC, aunque el REM esperara otro. Si no hay Excel cargado, la mediana a 12 meses de la API (BCRA id 29), pasada a mensual y plana, como aproximación.

**Rendimiento nominal:** CER de cada pago = el proyectado (o publicado) 10 días hábiles antes. Cero cupón: pago final = 100 × CER final / CER inicial; TNA = (pago / precio − 1) × 365 / plazo; TIR = (pago / precio) ^ (365 / plazo) − 1. Con cupón: flujos reales × CER del pago / CER inicial y TIR efectiva (base 365) con el motor; TNA semestral exacta. Se contrasta con la TEA de la tasa fija interpolada al plazo.

## Duales: qué pata paga

Al vencimiento, un dual paga la pata de mayor pago final (decisión de Agustin, 14/11/2026). La herramienta muestra siempre las dos:
- **Tasa fija / TAMAR (TTD26):** pago final de la pata fija (cupón de licitación) contra el de la TAMAR proyectada; TAMAR de los días por publicar con la que las dos patas pagan lo mismo.
- **CER / TAMAR (TXM):** pata CER = 100 × CER final proyectado / CER inicial, con la fuente de inflación elegida (por defecto el REM; también breakeven, escenario o mensual); pata TAMAR con la fuente de TAMAR (por defecto la actual: últimos 5 días). Inflación mensual plana, en los meses sin publicar, con la que las dos patas pagan lo mismo.
- Rendimiento de cada pata y del dual: TNA = (pago / precio − 1) × 365 / plazo; TEA = (pago / precio)^(365 / plazo) − 1.

## Escenarios de TAMAR y tipo de cambio

Código: `tools/proyecciones.py` (herramientas `proyectar_tamar` y `proyectar_dolar`). Escenarios en `renta_fija/escenarios/` (`tamar.toml`, `dolar_oficial.toml`, `dolar_mep.toml`, `dolar_ccl.toml`).

- **TAMAR** (TNA): `actual` (últimos 5 días, plana), `rem` (mensual del REM y después su valor a 12 meses), `tna:<tasa>` o `escenario:<nombre>` (TNA por mes y `resto`). Bonos TAMAR: TAMAR del bono = publicada + camino en los días por publicar; después, la cuenta de siempre.
- **Dólar oficial (A3500):** `rem` (promedios mensuales a mitad de mes, a 12 meses y diciembre; sin el mes en curso), `breakeven` (A3500 implícito de los dollar linked), `mensual:<variación>` o `escenario:<nombre>`. Dollar linked en pesos: pago = 100 × A3500 proyectado al vencimiento (aproxima el tipo de cambio de pago del prospecto).
- **MEP y CCL:** `mensual:<variación>` o `escenario:<nombre>`, desde el implícito de hoy del AL30 (precio en pesos / precio D o C). Hard dollar en pesos: cada flujo en dólares × dólar proyectado en su fecha, contra el precio en pesos; TIR efectiva (base 365).
- Escenarios de dólar: `nivel` (pesos por dólar de algunos meses, a mitad de mes), `mensual` (variación de algunos meses) y `resto` (variación mensual después). Entre puntos, crecimiento geométrico; después del último, `resto` o la variación del último tramo.

## Puntos abiertos (para decidir con Agustin)

1. **Para más adelante:** curva teórica de tasa fija (regresión de la TEA contra el logaritmo de la duration, con cada letra por encima o por debajo de la curva).
2. **Para más adelante:** calculadora de letras a descuento (hoy todas las letras vigentes son capitalizables).
3. **Para más adelante:** dollar linked corporativos con cupones y amortizaciones, con el tipo de cambio de pago de cada prospecto.
4. **Para más adelante (decisión de Agustin, 14/11/2026):** base propia de la curva de Treasuries (hoy se baja de FRED en cada consulta).
5. **Objetivo:** que las condiciones de emisión de cada bono salgan del análisis de los prospectos, sin carga manual.

## Historial de cambios de definición

- **12/11/2026:** el CER corriente pasa de "CER del día de liquidación" a "CER del décimo día hábil anterior a la liquidación" (error de definición, detectado con el TZXO7 a 103,35: el Excel usaba el CER del 30/10). Días hábiles con el calendario nacional oficial: el Excel de ese día tomaba el 9/11 como hábil (CER del 30/10); con el calendario oficial es el del 29/10.
- **13/11/2026:** carry mensual confirmado como inflación corriente (último dato mensual publicado) + TNA / 12, suma simple. La inflación del Excel del 12/11 (1,83815%) estaba mal: era el crecimiento del CER en 30 días, no el dato publicado (1,9% de septiembre). Las pruebas usan ese valor solo para verificar la fórmula con los números del Excel.
- **13/11/2026:** días hábiles con el calendario de BYMA (el 9/11 y el 10/11/2026 fueron feriados): para la liquidación del 13/11 el CER corriente es el del 28/10. Se suma la calculadora de CER con cupón (TX28), con current yield sobre el cupón actual y cash yield a 12 meses, ambos sobre el precio clean.
- **13/11/2026:** se suma el TX31 desde sus condiciones de emisión (cupón 2,5% semestral 30/360, 10 amortizaciones de 10% desde mayo 2027). Su CER inicial se calcula con la serie del BCRA (13/05/2022); Agustin lo da por bueno sin compararlo (bono ilíquido, hoy no lo usa).
- **13/11/2026:** el 7/12/2026 (feriado turístico) es feriado en BYMA (confirmado por Agustin): cargado en `calendarios/feriados_ajustes.toml`. La fecha del CER final del TZXD6 coincide con el Excel.
- **13/11/2026:** tasa fija: Lecap/Boncap capitalizables (pago final calculado con la TEM de emisión) y Bonte con cupón (TY30P). Para todos los bonos: TNA semestral exacta ((1+TIR)^(1/2) − 1) × 2 en lugar de la de 180 días; el cupón de cada período se devenga en 30/360 desde el pago anterior (o la emisión); la TEM que se muestra es la de 30 días corridos.
- **13/11/2026:** el CER inicial deja de cargarse en las fichas: se toma de la nueva base de series (`datos/series.db`, CER diario del BCRA desde 2002) con la fecha de emisión, igual que el CER corriente. Las bases de los Excel quedan solo en las pruebas, como contraste (`python -m tests.verificar_cer_inicial`). TZXD8: emisión 30/06/2026, validada por Agustin contra su Excel.
- **13/11/2026:** verificación de las bases contra los Excel: coinciden todas salvo las emitidas el 31/03/2026 (TZXM8, TZXM9, TZXS7, TZXS8), por el feriado puente del 23/03/2026, que la librería no tenía en el calendario de BYMA. Se agrega como ajuste (como el 10/07 y el 7/12): la base pasa a ser el CER del 13/03/2026. TXMJ8 y TXMJ9 difieren en el 7.º decimal porque el Excel tenía la base redondeada.
- **13/11/2026:** calculadora TAMAR (Bonos TAMAR capitalizables y pata TAMAR de los duales), con la TAMAR de bancos privados en TNA (BCRA 44) de la base de series. TEM con base 32 días (condiciones de emisión). Spread sobre la TNA de 30 días. Los duales CER/TAMAR se calculan de las dos formas.
- **13/11/2026:** hard dollar: AL30 y GD30, con TIR semestral 30/360 (convención de mercado, solo para esta familia), precio MEP y cable, spread contra Treasuries a la duration, spread entre leyes y dólar implícito. Cronogramas del canje 2020, a validar con la planilla de Agustin.
- **13/11/2026:** AL30 y GD30 validados por Agustin. Se suman AL29/GD29, AL35/GD35, AE38/GD38, AL41/GD41 y GD46 desde el Anexo II del Decreto 676/2020 (Bonares iguales a los Globales), a validar.
- **13/11/2026:** dollar linked del Tesoro (bullet), actual/365, con el A3500 del día de concertación (estimado con el del día hábil anterior hasta que se publica). A3500 (BCRA id 5) en la base de series.
- **13/11/2026:** breakevens entre curvas (inflación, devaluación, tipo de cambio real, brecha y TAMAR implícita), interpolando al plazo (duration en días), TEA contra TEA, sin ajustar rezagos, con forwards y niveles implícitos.
- **13/11/2026:** regla del CER verificada (días corridos, período del 16 al 15). Proyección del CER con breakeven, escenarios o inflación plana, y rendimiento nominal de todos los CER.
- **14/11/2026:** REM cargado desde el Excel del BCRA (relevamiento de octubre de 2026). La fuente `rem` de la proyección del CER usa la mediana mes a mes y completa cada año para cerrar en la anual del REM (decisión de Agustin).
- **14/11/2026:** breakevens de inflación, devaluación y TAMAR comparados con el REM.
- **14/11/2026:** hard dollar: la tasa semestral 30/360 se muestra como TNA y la TEA como TIR, como en las demás familias. Precio clean por 100 de residual. AL29 validado por Agustin en paridad, duration, duration modificada, convexidad y TEA.
- **14/11/2026:** clean y dirty solo en los hard dollar. En los bonos en pesos (TX28, TX31, TY30P) se muestra el precio (y en los CER el precio real = precio / ratio); el precio sin el interés corrido sigue en el current yield y el cash yield, sin nombrarlo.
- **14/11/2026:** hard dollar validados por Agustin (todos los Bonares y Globales). TTD26: pata tasa fija con cupón 2,14% y pago final como las Lecap; al vencimiento paga la pata de mayor pago final. La herramienta muestra las dos patas, cuál paga con la TAMAR estimada y la TAMAR de los días por publicar que iguala las dos.
- **14/11/2026:** en las Lecap/Boncap, la tasa de emisión se llama cupón de licitación (campo `cupon` de la ficha, antes `tem`), para no confundirla con la TEM de mercado que da la calculadora.
- **14/11/2026:** CER cero cupón con valor técnico, paridad, duration modificada y convexidad. Duales CER/TAMAR con las dos patas y cuál paga. Escenarios de TAMAR, dólar oficial, MEP y CCL. Nuevo agente de renta fija.
