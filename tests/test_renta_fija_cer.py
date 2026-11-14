"""Pruebas de la calculadora CER contra el Excel de Agustin (ejemplo_Cer.xlsx, 12/11/2026).

Cada caso es una fila del Excel: si un cambio en el código deja de reproducir estos números,
la prueba falla. Correr con:
    python -m tests.test_renta_fija_cer
(o con pytest, si está instalado: pytest tests/)
"""
from datetime import date

from renta_fija.calculadoras import cer
from renta_fija.calculadoras.motor import Flujo, tir

LIQUIDACION = date(2026, 11, 13)          # operación del 12/11/2026, T+1
CER_CORRIENTE = 862.27597                 # CER que usó el Excel (BCRA, 30/10/2026)
INFLACION = 0.0183814985                  # inflación del carry del Excel (estaba mal: es el CER de 30 días; sirve para verificar la fórmula)

# ticker, vencimiento, fecha CER final, base, ratio, precio, duration, plazo, TNA real, TEA real, carry mensual
CASOS = [
    ("X30N6", "2026-11-30", "2026-11-13", 659.1790598022395, 130.8105828570012, 129.6599999999998, 0.04657534246575343, 17, 0.19052669098615962, 0.20887032366105718, 0.03425872275414277),
    ("TZXD6", "2026-12-15", "2026-11-27", 271.047555509126, 318.1271893704932, 315.1500000000004, 0.08767123287671233, 32, 0.10775366097789643, 0.11321015731403028, 0.027360970253454173),
    ("X29E7", "2027-01-29", "2027-01-15", 815.43451086916, 105.74435576433015, 104.57999999999912, 0.21095890410958903, 77, 0.052776331545207764, 0.05388643529724213, 0.02277952613406345),
    ("TZXM7", "2027-03-31", "2027-03-12", 361.3176034572122, 238.6476501416079, 234.4500000000028, 0.3780821917808219, 138, 0.047355429503087285, 0.04805544604886247, 0.022327784297220075),
    ("TZXA7", "2027-04-30", "2027-04-16", 651.8980624429383, 132.27159580246283, 129.44999999999777, 0.4602739726027397, 168, 0.04735614356985409, 0.047962095164041596, 0.022327843802783975),
    ("TZXY7", "2027-05-31", "2027-05-14", 659.1790598022395, 130.8105828570012, 127.55000000000038, 0.5452054794520548, 199, 0.046887228884733234, 0.047386440612073644, 0.022288767579023903),
    ("TZX27", "2027-06-30", "2027-06-15", 200.38801458911763, 430.3031655693829, 417.54999999999313, 0.6273972602739726, 229, 0.048681829625062, 0.04912154286849102, 0.022438317640717968),
    ("TZXS7", "2027-09-30", "2027-09-16", 723.0599806219161, 119.25372628933934, 112.89999999998108, 0.8794520547945206, 321, 0.06399151499041572, 0.06423443776631688, 0.023714124754497443),
    ("TZXO7", "2027-10-29", "2027-10-15", 791.48970450621, 108.94342216827214, 101.99999999989575, 0.958904109589041, 350, 0.07099017062913093, 0.07109154714207455, 0.024297346057723712),
    ("TZXD7", "2027-12-15", "2027-11-30", 271.047555509126, 318.1271893704932, 290.94999999999425, 1.0876712328767124, 397, 0.0858793080794766, 0.08556638697445362, 0.025538107511919185),
    ("TZXM8", "2028-03-31", "2028-03-16", 723.0599806219161, 119.25372628933934, 104.50000000000861, 1.3808219178082193, 504, 0.10224633735105328, 0.10036644596194577, 0.026902026617883906),
    ("TZX28", "2028-06-30", "2028-06-15", 200.38801458911763, 430.3031655693829, 360.79999999997926, 1.63013698630137, 595, 0.11817182839643832, 0.11412388898464054, 0.028229150871665994),
    ("TXMJ8", "2028-06-30", "2028-06-15", 758.118, 113.7390182265307, 102.20000000000043, 1.63013698630137, 595, 0.06926181408481526, 0.06782430275526785, 0.024153316345697406),
    ("TZXS8", "2028-09-29", "2028-09-15", 723.0599806219161, 119.25372628933934, 97.20000000000553, 1.8794520547945206, 686, 0.12072145580040522, 0.11493832098894208, 0.02844161982199657),
    ("TXMD8", "2028-12-15", "2028-11-30", 779.88639312623, 110.56430498064154, 95.04999999997334, 2.0904109589041098, 763, 0.07808156868455772, 0.07500736657733809, 0.024888295895675944),
    ("TZXM9", "2029-03-28", "2029-03-14", 723.0599806219161, 119.25372628933934, 92.60000000000807, 2.372602739726027, 866, 0.12131707180808296, 0.11251016842196715, 0.02849125448930305),
    ("TXMJ9", "2029-06-29", "2029-06-15", 746.3809, 115.52760396181225, 92.95000000000336, 2.627397260273973, 959, 0.09244910559468551, 0.0862828828887432, 0.026085590638186593),
    ("TXMD9", "2029-12-14", "2029-11-30", 779.88639312623, 110.56430498064154, 85.90000000001382, 3.0876712328767124, 1127, 0.09299180262565344, 0.08518319519859396, 0.026130815390767254),
    ("TXMJ0", "2030-06-28", "2030-06-14", 779.88639312623, 110.56430498064154, 82.79999999999794, 3.6246575342465754, 1323, 0.09251017229484271, 0.0830469951878412, 0.02609067952986636),
]

# Diferencias de calendario conocidas (la fecha CER final es solo informativa, no entra en ningún cálculo):
# - TXMJ9 y TXMJ0: feriados de 2029 y 2030 que todavía no están decretados.
FECHA_CER_CONOCIDAS = {"TXMJ9", "TXMJ0"}


def test_variables_como_el_excel():
    for t, vto, _, base, ratio, precio, dur, plazo, tna, tea, carry in CASOS:
        r = cer.calcular(precio, base, CER_CORRIENTE, LIQUIDACION, date.fromisoformat(vto), INFLACION)
        assert r["plazo_residual"] == plazo, t
        assert abs(r["duration"] - dur) < 1e-12, t
        # el CER del Excel tiene más decimales que CER_CORRIENTE: tolerancia acorde
        assert abs(r["ratio"] / ratio - 1) < 1e-8, (t, r["ratio"], ratio)
        assert abs(r["tna_real"] - tna) < 1e-7, (t, r["tna_real"], tna)
        assert abs(r["tea_real"] - tea) < 1e-7, (t, r["tea_real"], tea)
        assert abs(r["carry_mensual"] - carry) < 1e-7, (t, r["carry_mensual"], carry)


def test_el_motor_da_la_misma_tir():
    """Para un cupón cero, la TIR del motor común coincide con la TEA real de la definición."""
    for t, vto, _, base, ratio, precio, *_ , tea, _carry in CASOS:
        flujos = [Flujo(date.fromisoformat(vto), amortizacion=cer.ratio(CER_CORRIENTE, base))]
        assert abs(tir(flujos, precio, LIQUIDACION) - tea) < 1e-7, t


def _feriados():
    from admin_datos import feriados
    from carga_datos import feriados as carga
    carga.cargar()          # recarga con los ajustes vigentes (ej.: el 7/12/2026 en BYMA)
    return feriados


def test_fecha_cer_final():
    from tools.bonos import CALENDARIO_HABILES
    feriados = _feriados()
    for t, vto, fecha_cer, *_ in CASOS:
        if t in FECHA_CER_CONOCIDAS:
            continue
        calculada = feriados.sumar_dias_habiles(date.fromisoformat(vto), -cer.REZAGO_HABILES, CALENDARIO_HABILES)
        assert calculada.isoformat() == fecha_cer, (t, calculada, fecha_cer)


def test_fecha_cer_corriente():
    """Liquidación 13/11/2026: 10.º día hábil anterior con el calendario de BYMA (9/11 y 10/11 feriados)."""
    from tools.bonos import CALENDARIO_HABILES
    feriados = _feriados()
    assert feriados.sumar_dias_habiles(LIQUIDACION, -cer.REZAGO_HABILES, CALENDARIO_HABILES) == date(2026, 10, 28)


def test_fecha_base_con_feriados_puente():
    """Emisión del 31/03/2026 (TZXM8, TZXM9, TZXS7, TZXS8): con el 23/03 (puente) y el 24/03 inhábiles,
    el 10.º día hábil anterior es el 13/03/2026, como en el Excel."""
    from tools.bonos import CALENDARIO_HABILES
    feriados = _feriados()
    assert feriados.sumar_dias_habiles(date(2026, 3, 31), -cer.REZAGO_HABILES, CALENDARIO_HABILES) == date(2026, 3, 13)


def test_tzxo7_a_103_35():
    """Caso de Agustin: TZXO7 a 103,35. Con el CER del 30/10 (su Excel) la TIR es 5,65%;
    con el del 28/10 (calendario de BYMA, que es lo que calcula la herramienta) es 5,52%."""
    base, vto = 791.48970450621, date(2027, 10, 29)
    excel = cer.calcular(103.35, base, 862.27597, LIQUIDACION, vto)       # CER BCRA del 30/10/2026
    oficial = cer.calcular(103.35, base, 861.22954, LIQUIDACION, vto)     # CER BCRA del 28/10/2026
    assert round(excel["tea_real"] * 100, 2) == 5.65, excel["tea_real"]
    assert round(oficial["tea_real"] * 100, 2) == 5.52, oficial["tea_real"]


def test_variables_extra():
    """Valor técnico, paridad, duration modificada y convexidad: iguales al motor común con un solo flujo."""
    from renta_fija.calculadoras import motor
    liq, vto = date(2026, 11, 13), date(2027, 10, 29)
    r = cer.calcular(103.35, 791.48970450621, 861.22954, liq, vto)
    assert abs(r["valor_tecnico"] - 100 * 861.22954 / 791.48970450621) < 1e-9
    assert abs(r["paridad"] - 103.35 / r["valor_tecnico"]) < 1e-15
    flujos = [motor.Flujo(vto, 0.0, r["valor_tecnico"])]
    assert abs(r["duration_modificada"] - motor.duration_modificada(flujos, liq, r["tea_real"])) < 1e-12
    assert abs(r["convexidad"] - motor.convexidad(flujos, liq, r["tea_real"])) < 1e-12


if __name__ == "__main__":
    for prueba in (test_variables_como_el_excel, test_el_motor_da_la_misma_tir, test_fecha_cer_final,
                   test_fecha_cer_corriente, test_fecha_base_con_feriados_puente, test_tzxo7_a_103_35,
                   test_variables_extra):
        prueba()
        print(f"OK  {prueba.__name__}")
    print(f"Todas las pruebas pasaron ({len(CASOS)} bonos del Excel).")
