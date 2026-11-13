# Convenciones de renta fija

Definiciones de Agustin para calcular las variables de cada bono. **El código las respeta tal cual**: cualquier cambio se discute y se decide antes de programarlo, y queda registrado acá.

Validación: `python -m tests.test_renta_fija_cer` reproduce los 19 bonos del Excel de Agustin (`ejemplo_Cer.xlsx`, 12/11/2026) `python -m tests.test_renta_fija_cer_cupon` el TX28 (`ejemplo_tx28.xlsx`, 13/11/2026) y `python -m tests.test_renta_fija_tasa_fija` las Lecap/Boncap y el TY30P (`tasa_fija.xlsx`, 13/11/2026).

## Generales

- Los precios y los cálculos siempre se realizan en **T+1**, salvo que se indique lo contrario.
- Precio por cada 100 de valor nominal original, para todos los bonos (uniformidad). Se usa el precio como cotiza: nominal y con cupón corrido (dirty).
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
| Precio dirty real | Precio de mercado / ratio |
| Precio clean | Dirty real − interés corrido (real); × ratio en pesos |
| Paridad | Dirty real / valor técnico |
| TIR real | Tasa efectiva anual (base 365) que iguala los flujos futuros reales, en las fechas corridas, al dirty real (como el XIRR de Excel) |
| TNA semestral | ((1 + TIR)^(1/2) − 1) × 2 (capitalización semestral exacta; para todos los bonos) |
| TNA 30 d | ((1 + TIR)^(30/365) − 1) × 365/30 |
| TEM | (1 + TIR)^(30/365) − 1 |
| Duration | Macaulay, en años |
| Duration modificada | Duration / (1 + TIR) |
| Convexidad | Σ flujo × t(t+1) / (1 + TIR)^(t+2) / dirty real |
| PV01 / DD | Dirty real × (−MD × Δ + CVX × Δ² / 2), con Δ = 1 pb y 100 pb |
| Current yield | Cupón actual (tasa × residual) / precio clean real |
| Cash yield | (Cupones + amortizaciones de los próximos 12 meses) / precio clean real |

Correcciones al Excel del TX28 acordadas el 13/11/2026: la fila del último cupón usaba la emisión en lugar de la liquidación; la TIR nominal dejaba afuera el último flujo; algunas sumas tenían rangos desplazados; la duration y la convexidad usaban fechas sin correr mientras la TIR usaba fechas corridas (ahora todo con fechas corridas); el current yield mezclaba unidades.

## Tasa fija

Código: `renta_fija/calculadoras/tasa_fija.py`. Fichas: `renta_fija/fichas/tasa_fija.toml`.

**Capitalizables (Lecap "S", Boncap "T"):**

| Variable | Definición |
|---|---|
| Pago final | 100 × (1 + TEM de emisión) ^ (días 30/360 entre emisión y vencimiento / 30) |
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
| Valor técnico, paridad, precio clean | Como los bonos con cupón |
| TIR | Nominal anual con capitalización semestral, base 30/360: precio = Σ flujo / (1 + TIR/2) ^ (días 30/360 / 180) (convención de mercado; solo para esta familia) |
| TEA | (1 + TIR/2)² − 1 |
| Duration / modificada / convexidad | Macaulay en años con esa TIR; modificada = duration / (1 + TIR/2) |
| Current yield, cash yield | Cupón vigente × residual / clean; flujos de 12 meses / clean |
| Spread contra Treasuries | TIR − rendimiento del Treasury constant maturity (FRED, también semestral) interpolado linealmente a la duration del bono, en pb |
| Spread ley NY − ley AR | TIR del Global − TIR del Bonar del mismo vencimiento, con el mismo tipo de precio (MEP con MEP, cable con cable) |
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

## Puntos abiertos (para decidir con Agustin)

1. **Para más adelante (decisión de Agustin, 13/11/2026):** duration modificada, convexidad, valor técnico y paridad de los CER cero cupón. Por ahora no hacen falta.
2. **Para más adelante:** proyección del CER (función y base de datos) para la TIR y la duration nominales de los CER con cupón.
3. **Para más adelante:** curva teórica de tasa fija (regresión de la TEA contra el logaritmo de la duration, con cada letra por encima o por debajo de la curva).
4. **Para más adelante:** calculadora de letras a descuento (hoy todas las letras vigentes son capitalizables).
5. **Para más adelante:** la pata tasa fija del dual TTD26 (hoy se calcula solo como TAMAR).
6. **Para más adelante:** breakeven (devaluación o inflación implícita) entre curvas, para todas las curvas (decisión de Agustin, 13/11/2026).
7. **Para más adelante:** dollar linked corporativos con cupones y amortizaciones, con el tipo de cambio de pago de cada prospecto.
8. **Objetivo:** que las condiciones de emisión de cada bono salgan del análisis de los prospectos, sin carga manual.

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
