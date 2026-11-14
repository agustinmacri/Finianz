"""Pruebas de la proyección del CER y del rendimiento nominal de los bonos CER.
Correr con:
    python -m tests.test_proyeccion_cer
"""
from datetime import date, timedelta

from renta_fija.calculadoras import motor
from renta_fija.calculadoras import proyeccion_cer as pc


def _serie(desde: date, hasta: date, inflaciones: dict, inicial: float = 800.0) -> dict:
    """CER armado día a día con la regla, para usar de dato."""
    cer, valor, dia = {desde: inicial}, inicial, desde
    while dia < hasta:
        dia += timedelta(days=1)
        mes = pc.mes_aplicado(dia)
        ini, fin = pc.periodo(mes)
        valor *= (1 + inflaciones[mes]) ** (1 / ((fin - ini).days + 1))
        cer[dia] = valor
    return cer


def test_regla_con_los_datos_del_bcra():
    """Factores diarios publicados: 1,0006073377 (16/10 al 15/11, 31 días) y 1,0007256462 (16/11 al 15/12, 30 días)."""
    assert pc.periodo((2026, 9)) == (date(2026, 10, 16), date(2026, 11, 15))
    assert pc.periodo((2026, 10)) == (date(2026, 11, 16), date(2026, 12, 15))
    assert pc.mes_aplicado(date(2026, 11, 15)) == (2026, 9) and pc.mes_aplicado(date(2026, 11, 16)) == (2026, 10)
    assert pc.mes_aplicado(date(2027, 1, 3)) == (2026, 11)
    assert abs(1.0006073377 ** 31 - 1.019) < 1e-8 and abs(1.0007256462 ** 30 - 1.022) < 1e-8
    serie = _serie(date(2026, 10, 15), date(2026, 12, 15), {(2026, 9): 0.019, (2026, 10): 0.022})
    assert abs(serie[date(2026, 11, 17)] / serie[date(2026, 11, 16)] - 1.0007256462) < 1e-10
    publicadas = pc.inflacion_publicada(serie)
    assert abs(publicadas[(2026, 9)] - 0.019) < 1e-12 and abs(publicadas[(2026, 10)] - 0.022) < 1e-12


def test_proyectar():
    serie = _serie(date(2026, 10, 15), date(2026, 12, 15), {(2026, 9): 0.019, (2026, 10): 0.022})
    proy = pc.proyectar(serie, {(2026, 11): 0.02, (2026, 12): 0.025}, date(2027, 2, 15))
    assert min(proy) == date(2026, 12, 16) and max(proy) == date(2027, 2, 15)
    assert abs(proy[date(2027, 1, 15)] / serie[date(2026, 12, 15)] - 1.02) < 1e-12
    assert abs(proy[date(2027, 2, 15)] / proy[date(2027, 1, 15)] - 1.025) < 1e-12
    try:
        pc.proyectar(serie, {(2026, 11): 0.02}, date(2027, 2, 15))
        raise AssertionError("tenía que pedir la inflación de diciembre")
    except ValueError:
        pass


def test_camino_mensual_y_anual():
    publicadas = {(2026, m): 0.02 for m in range(1, 11)}                  # enero a octubre publicadas
    mensuales = {(2026, 11): 0.021, (2027, 1): 0.019, (2027, 2): 0.018}
    anuales = {2026: 0.27, 2027: 0.20, 2028: 0.15}
    c = pc.camino(publicadas, mensuales, anuales, (2026, 11), (2029, 12))
    assert c[(2026, 11)] == (0.021, "mensual")
    dic = c[(2026, 12)][0]                                               # cierra 2026 en 27%
    assert abs(1.02 ** 10 * 1.021 * (1 + dic) - 1.27) < 1e-12 and c[(2026, 12)][1] == "anual 2026"
    anio = 1.019 * 1.018                                                 # 2027 cierra en 20%
    for m in range(3, 13):
        anio *= 1 + c[(2027, m)][0]
    assert abs(anio - 1.20) < 1e-12
    assert abs(c[(2028, 6)][0] - (1.15 ** (1 / 12) - 1)) < 1e-15
    assert c[(2029, 6)] == (1.15 ** (1 / 12) - 1, "anual 2028 (último año con dato)")


def test_inflacion_desde_cer():
    """Niveles de CER con 2% mensual: se recupera el 2% de cada mes."""
    serie = _serie(date(2026, 12, 15), date(2027, 12, 15), {pc.sumar_meses((2026, 11), k): 0.02 for k in range(13)})
    nodos = [(d, serie[d]) for d in (date(2027, 3, 20), date(2027, 8, 2), date(2027, 12, 15))]
    c = pc.inflacion_desde_cer((date(2026, 12, 15), serie[date(2026, 12, 15)]), nodos, (2026, 11), (2028, 2))
    for mes in [(2026, 11), (2027, 5), (2027, 10)]:
        assert abs(c[mes][0] - 0.02) < 1e-12, (mes, c[mes])
    assert c[(2028, 2)][1] == "breakeven (última, extendida)"


def test_nominal():
    """TIR nominal = (1 + TIR real) × (1 + inflación) − 1 cuando el CER del pago crece a esa inflación."""
    liq, vto = date(2026, 11, 16), date(2027, 11, 16)
    cer_inicial, cer_corriente, real, inflacion = 500.0, 800.0, 0.05, 0.25
    precio = 100 * cer_corriente / cer_inicial / (1 + real)
    r = pc.nominal_cero_cupon(precio, cer_inicial, cer_corriente * (1 + inflacion), liq, vto)
    assert abs(r["tir"] - (1.05 * 1.25 - 1)) < 1e-12
    flujos = [motor.Flujo(vto, 0.0, 100.0)]
    r2 = pc.nominal_con_cupon(precio, cer_inicial, flujos, [cer_corriente * (1 + inflacion)], liq)
    assert abs(r2["tir"] - r["tir"]) < 1e-9 and abs(r2["flujos"][0].total - r["pago_final"]) < 1e-9


def test_tasa_mensual():
    from tools.proyeccion_cer import tasa_mensual
    for texto in ("2%", "2", "0.02", "2,0%"):
        assert abs(tasa_mensual(texto) - 0.02) < 1e-15, texto
    assert abs(tasa_mensual("1.66") - 0.0166) < 1e-15                     # el caso que daba 857% de TNA
    assert abs(tasa_mensual("0.25") - 0.0025) < 1e-15


def test_escenarios_del_archivo():
    from tools import proyeccion_cer
    assert isinstance(proyeccion_cer.escenarios(), dict)                 # el archivo de ejemplo no trae activos


if __name__ == "__main__":
    for prueba in (test_regla_con_los_datos_del_bcra, test_proyectar, test_camino_mensual_y_anual,
                   test_inflacion_desde_cer, test_nominal, test_tasa_mensual, test_escenarios_del_archivo):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas de la proyección del CER pasaron.")
