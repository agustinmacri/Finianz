# Convenciones de renta fija

Definiciones de Agustin para calcular las variables de cada bono. **El código las respeta tal cual**: cualquier cambio se discute y se decide antes de programarlo, y queda registrado acá.

Validación: `python -m tests.test_renta_fija_cer` reproduce los 19 bonos del Excel de Agustin (`ejemplo_Cer.xlsx`, 12/11/2026).

## Generales

- Los precios y los cálculos siempre se realizan en **T+1**, salvo que se indique lo contrario.
- Precio por cada 100 de valor nominal.
- Días hábiles: calendario nacional oficial, con los feriados decretados (decisión de Agustin, 12/11/2026). Ej.: el 9/11/2026 (visita del Papa) es inhábil.

## Bonos CER que no pagan intereses ni amortizaciones

Boncer cero cupón (TZX), LeCER (X) y la parte CER de los duales CER/TAMAR (TXM).
Código: `renta_fija/calculadoras/cer.py`. Fichas: `renta_fija/fichas/cer.toml`.

| Variable | Definición (Agustin) |
|---|---|
| Plazo residual | Días corridos entre la liquidación y el vencimiento |
| Duration | Plazo residual / 365 |
| CER final | CER correspondiente al décimo día hábil anterior a la fecha de vencimiento |
| CER inicial (base) | CER correspondiente al décimo día hábil anterior a la liquidación inicial del bono |
| CER corriente | CER del décimo día hábil anterior a la liquidación de la operación (operación del 12/11/26 → liquidación 13/11/26 → CER del 29/10/26) |
| Ratio actual | CER corriente / CER inicial |
| TNA real | (ratio actual / precio − 1) × 365 / plazo residual |
| TIR (TEA real) | Capitalización de la TNA por el plazo remanente, base 365: (1 + TNA × plazo / 365) ^ (365 / plazo) − 1 |
| Carry mensual | Inflación corriente (último dato de inflación mensual publicado, INDEC vía BCRA) + TNA del bono mensualizada (TNA / 12). Suma simple |

Notas de implementación:
- La TEA real coincide con la TIR del motor común (`renta_fija/calculadoras/motor.py`) para un flujo único: lo verifica una prueba.
- La fecha del CER final es informativa (no entra en los cálculos). En TXMJ9 y TXMJ0 difiere un día del Excel por feriados de 2029 y 2030 aún no decretados.

## Puntos abiertos (para decidir con Agustin)

1. **Variables no definidas todavía:** duration modificada, convexidad, valor técnico y paridad.

## Historial de cambios de definición

- **12/11/2026:** el CER corriente pasa de "CER del día de liquidación" a "CER del décimo día hábil anterior a la liquidación" (error de definición, detectado con el TZXO7 a 103,35: el Excel usaba el CER del 30/10). Días hábiles con el calendario nacional oficial: el Excel de ese día tomaba el 9/11 como hábil (CER del 30/10); con el calendario oficial es el del 29/10.
- **13/11/2026:** carry mensual confirmado como inflación corriente (último dato mensual publicado) + TNA / 12, suma simple. La inflación del Excel del 12/11 (1,83815%) estaba mal: era el crecimiento del CER en 30 días, no el dato publicado (1,9% de septiembre). Las pruebas usan ese valor solo para verificar la fórmula con los números del Excel.
