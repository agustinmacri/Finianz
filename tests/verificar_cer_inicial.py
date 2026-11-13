"""Compara el CER inicial que toma la herramienta (base de series, 10.º día hábil anterior a la
emisión) con las bases de los Excel de Agustin. Necesita conexión al BCRA.
Correr con:
    python -m tests.verificar_cer_inicial

No es una prueba automática: muestra las diferencias para revisarlas. Una diferencia suele
deberse a la fecha de emisión de la ficha o a un feriado (antes de 2026 el calendario de BYMA
se aproxima con el nacional).
"""
from renta_fija import leer_fichas
from tests.test_renta_fija_cer import CASOS
from tests.test_renta_fija_cer_cupon import CER_INICIAL as BASE_TX28
from tools import bonos

EXCEL = {t: base for t, _vto, _fecha, base, *_ in CASOS} | {
    "TX28": BASE_TX28,
    "TZXD8": 791.48970450621,      # emitido el 30/06/2026, como el TZXO7 (Excel de Agustin, 13/11/2026)
}


def main():
    print(f"{'Bono':<7} {'Emisión':<11} {'Fecha base':<11} {'Base propia':>16} {'Excel':>16} {'Dif. %':>9}")
    for f in sorted(leer_fichas.todas(), key=lambda f: f["ticker"]):
        if not f["familia"].startswith("cer"):
            continue
        ticker = f["ticker"].upper()
        bonos._asegurar_feriados(f["emision"])
        fecha = bonos.feriados.sumar_dias_habiles(f["emision"], -bonos.cer.REZAGO_HABILES, bonos.CALENDARIO_HABILES)
        propia = bonos._cer(fecha)
        excel = EXCEL.get(ticker)
        dif = f"{(propia / excel - 1) * 100:9.5f}" if excel else f"{'(sin Excel)':>9}"
        marca = "  <-- revisar" if excel and abs(propia / excel - 1) > 1e-6 else ""
        print(f"{ticker:<7} {f['emision']!s:<11} {fecha!s:<11} {propia:16.6f} {excel or 0:16.6f} {dif}{marca}")


if __name__ == "__main__":
    main()
