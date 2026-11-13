# Convenciones de renta fija

Definiciones de Agustin para calcular las variables de cada bono. **El código las respeta tal cual**: cualquier cambio se discute y se decide antes de programarlo, y queda registrado acá.

Validación: `python -m tests.test_renta_fija_cer` reproduce los 19 bonos del Excel de Agustin (`ejemplo_Cer.xlsx`, 12/11/2026) y `python -m tests.test_renta_fija_cer_cupon` el TX28 (`ejemplo_tx28.xlsx`, 13/11/2026).

## Generales

- Los precios y los cálculos siempre se realizan en **T+1**, salvo que se indique lo contrario.
- Precio por cada 100 de valor nominal original, para todos los bonos (uniformidad). Se usa el precio como cotiza: nominal y con cupón corrido (dirty).
- Días hábiles: calendario de BYMA (decisión de Agustin, 13/11/2026), para la liquidación, el rezago del CER y las fechas de pago. Ej.: el 9/11/2026 y el 10/11/2026 fueron inhábiles.
- Fechas de pago: si caen en un día inhábil, se corren al día hábil siguiente, y esa fecha se usa en todos los cálculos (TIR, duration, convexidad).

## Bonos CER que no pagan intereses ni amortizaciones

Boncer cero cupón (TZX), LeCER (X) y la parte CER de los duales CER/TAMAR (TXM).
Código: `renta_fija/calculadoras/cer.py`. Fichas: `renta_fija/fichas/cer.toml`.

| Variable | Definición (Agustin) |
|---|---|
| Plazo residual | Días corridos entre la liquidación y el vencimiento |
| Duration | Plazo residual / 365 |
| CER final | CER correspondiente al décimo día hábil anterior a la fecha de vencimiento |
| CER inicial (base) | CER correspondiente al décimo día hábil anterior a la liquidación inicial del bono |
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
| Ratio | CER corriente / CER inicial (igual que en los cero cupón). Si la ficha no trae el CER inicial, se toma el del BCRA del 10.º día hábil anterior a la emisión |
| Residual | 100 − amortizaciones pagadas hasta la liquidación |
| Cupón de cada pago | Residual anterior × tasa anual / frecuencia (2,25% semestral → × 180/360) |
| Interés corrido | Residual × tasa × días 30/360 (DAYS360 de Excel, método US) desde el último cupón / 360 |
| Valor técnico | Residual + interés corrido |
| Precio dirty real | Precio de mercado / ratio |
| Precio clean | Dirty real − interés corrido (real); × ratio en pesos |
| Paridad | Dirty real / valor técnico |
| TIR real | Tasa efectiva anual (base 365) que iguala los flujos futuros reales, en las fechas corridas, al dirty real (como el XIRR de Excel) |
| TNA 180 d / TNA 30 d | ((1 + TIR)^(n/365) − 1) × 365/n |
| TEM | (1 + TIR)^(30/365) − 1 |
| Duration | Macaulay, en años |
| Duration modificada | Duration / (1 + TIR) |
| Convexidad | Σ flujo × t(t+1) / (1 + TIR)^(t+2) / dirty real |
| PV01 / DD | Dirty real × (−MD × Δ + CVX × Δ² / 2), con Δ = 1 pb y 100 pb |
| Current yield | Cupón actual (tasa × residual) / precio clean real |
| Cash yield | (Cupones + amortizaciones de los próximos 12 meses) / precio clean real |

Correcciones al Excel del TX28 acordadas el 13/11/2026: la fila del último cupón usaba la emisión en lugar de la liquidación; la TIR nominal dejaba afuera el último flujo; algunas sumas tenían rangos desplazados; la duration y la convexidad usaban fechas sin correr mientras la TIR usaba fechas corridas (ahora todo con fechas corridas); el current yield mezclaba unidades.

## Puntos abiertos (para decidir con Agustin)

1. **Para más adelante (decisión de Agustin, 13/11/2026):** duration modificada, convexidad, valor técnico y paridad de los CER cero cupón. Por ahora no hacen falta.
2. **Para más adelante:** proyección del CER (función y base de datos) para la TIR y la duration nominales de los CER con cupón.
3. **7/12/2026 (feriado turístico):** el Excel lo toma como inhábil; el calendario de BYMA de la librería, como hábil. Afecta solo la fecha informativa del CER final del TZXD6. Se resuelve con un ajuste en `calendarios/feriados_ajustes.toml` cuando se confirme si opera el mercado.

## Historial de cambios de definición

- **12/11/2026:** el CER corriente pasa de "CER del día de liquidación" a "CER del décimo día hábil anterior a la liquidación" (error de definición, detectado con el TZXO7 a 103,35: el Excel usaba el CER del 30/10). Días hábiles con el calendario nacional oficial: el Excel de ese día tomaba el 9/11 como hábil (CER del 30/10); con el calendario oficial es el del 29/10.
- **13/11/2026:** carry mensual confirmado como inflación corriente (último dato mensual publicado) + TNA / 12, suma simple. La inflación del Excel del 12/11 (1,83815%) estaba mal: era el crecimiento del CER en 30 días, no el dato publicado (1,9% de septiembre). Las pruebas usan ese valor solo para verificar la fórmula con los números del Excel.
- **13/11/2026:** días hábiles con el calendario de BYMA (el 9/11 y el 10/11/2026 fueron feriados): para la liquidación del 13/11 el CER corriente es el del 28/10. Se suma la calculadora de CER con cupón (TX28), con current yield sobre el cupón actual y cash yield a 12 meses, ambos sobre el precio clean.
- **13/11/2026:** se suma el TX31 desde sus condiciones de emisión (cupón 2,5% semestral 30/360, 10 amortizaciones de 10% desde mayo 2027). Su CER inicial se calcula con la serie del BCRA (13/05/2022) hasta validarlo.
