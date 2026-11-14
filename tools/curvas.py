"""curva_tasa_fija: curva teórica de las Lecap/Boncap (y letras a descuento) a precios de mercado."""
from datetime import date

from conexiones.http import ErrorAPI
from renta_fija.calculadoras import curva
from tools import bonos, breakevens


def curva_tasa_fija(fecha: str | None = None, incluir_bonte: bool = False) -> str:
    try:
        operacion = date.fromisoformat(fecha) if fecha else date.today()
        bonos._asegurar_feriados(operacion)
        liquidacion = bonos.feriados.sumar_dias_habiles(operacion, bonos.PLAZO_LIQUIDACION, "BYMA")
        familias = {"tasa_fija_capitalizable", "tasa_fija_descuento"} | ({"tasa_fija_cupon"} if incluir_bonte else set())
        curvas, _, errores = breakevens._curvas(operacion, liquidacion, operacion if fecha else None, familias)
        puntos = [dict(p, duration=p["x"] / 365) for p in curvas["tasa_fija"]]
        ajuste = curva.ajustar_log([(p["duration"], p["tea"]) for p in puntos])
    except (ErrorAPI, ValueError) as e:
        return f"Error: {e}"
    filas = curva.desvios(puntos, ajuste)
    texto = [f"Curva teórica de tasa fija – calculadora de Finianz (liquidación {liquidacion})",
             f"TEA = {ajuste['a'] * 100:.2f}% {'+' if ajuste['b'] >= 0 else '−'} {abs(ajuste['b']) * 100:.2f}% × ln(duration en años) | "
             f"R² = {ajuste['r2']:.3f} | {len(filas)} bonos{' (incluye Bonte)' if incluir_bonte else ''}",
             "Bono | vence | duration | TEA | TEA de la curva | desvío | contra sus vecinos de plazo"]
    for f in filas:
        vecinos = "; ".join(f"{t} ({dias:+.0f} d): {dif:+.0f} pb" for t, dif, dias in f["vecinos"])
        texto.append(f"{f['ticker']} | {f['vencimiento']} | {f['duration']:.3f} | {bonos._pct(f['tea'])} | "
                     f"{bonos._pct(f['tea_curva'])} | {f['desvio_pb']:+.0f} pb | {vecinos}")
    texto.append("Lectura: el desvío contra la curva no indica por sí solo si un bono está barato o caro. Sirve para comparar "
                 "bonos de plazos parecidos: un desvío mayor que el de su vecino cercano indica que rinde más que él en "
                 "relación a la curva. Entre plazos muy distintos la comparación pierde sentido.")
    if errores:
        texto.append("Sin precio: " + " | ".join(errores))
    return "\n".join(texto)


CURVA_TASA_FIJA = {
    "name": "curva_tasa_fija",
    "description": (
        "Curva teórica de tasa fija (Lecap, Boncap y letras a descuento): ajuste TEA = a + b × ln(duration), con el desvío "
        "de cada bono en pb y la comparación con sus vecinos de plazo. Sirve para comparar bonos de plazos parecidos, "
        "no como señal absoluta de barato o caro."
    ),
    "parameters": {"type": "object", "properties": {
        "fecha": {"type": "string", "description": "Fecha de operación AAAA-MM-DD para usar los cierres (opcional)"},
        "incluir_bonte": {"type": "boolean", "description": "Sumar el Bonte con cupón (TY30P) a la curva (por defecto, no)"},
    }},
}

HERRAMIENTAS = [(CURVA_TASA_FIJA, curva_tasa_fija)]
