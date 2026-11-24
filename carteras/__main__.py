"""Carteras desde la terminal.

    python -m carteras listar                         # las carteras de datos/carteras/
    python -m carteras plantilla                      # copia la plantilla a datos/carteras/ para completarla
    python -m carteras ver <nombre> [--moneda pesos|mep|ccl] [--fecha AAAA-MM-DD] [--excel]
"""
import shutil
import sys
from datetime import date

from carteras import excel, valuar


def main(argv: list[str]):
    if not argv or argv[0] not in ("listar", "plantilla", "ver"):
        print(__doc__)
        return
    if argv[0] == "listar":
        nombres = excel.listar()
        print("\n".join(nombres) if nombres else f"No hay carteras en {excel.carpeta()}. Creá una con: python -m carteras plantilla")
        return
    if argv[0] == "plantilla":
        excel.carpeta().mkdir(parents=True, exist_ok=True)
        if not excel.PLANTILLA.exists():
            excel.crear_plantilla()
        destino = excel.carpeta() / "nueva_cartera.xlsx"
        if destino.exists():
            print(f"Ya existe {destino}: renombrala antes de crear otra.")
            return
        shutil.copy(excel.PLANTILLA, destino)
        print(f"Plantilla copiada a {destino}. Renombrala con el nombre de la cartera y completala.")
        return
    if len(argv) < 2:
        print(__doc__)
        return
    opcion = lambda nombre, defecto=None: argv[argv.index(nombre) + 1] if nombre in argv and argv.index(nombre) + 1 < len(argv) else defecto
    try:
        fecha = date.fromisoformat(opcion("--fecha")) if opcion("--fecha") else None
        v = valuar.valuar(excel.leer(argv[1]), opcion("--moneda", "pesos"), fecha)
    except ValueError as e:
        print(f"Error: {e}")
        return
    print(valuar.texto(v))
    if "--excel" in argv:
        print(f"\nGuardada en {excel.guardar_valuacion(v)}")


if __name__ == "__main__":
    main(sys.argv[1:])
