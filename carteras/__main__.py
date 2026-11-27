"""Carteras desde la terminal.

    python -m carteras listar                         # las carteras de datos/carteras/
    python -m carteras plantilla                      # copia la plantilla a datos/carteras/ para completarla
    python -m carteras ver <nombre> [--moneda pesos|mep|ccl] [--fecha AAAA-MM-DD] [--excel]
    python -m carteras convertir <nombre> --fecha AAAA-MM-DD   # pasa una cartera "foto" a operaciones
"""
import shutil
import sys
from datetime import date

from carteras import excel, valuar
from conexiones.http import ErrorAPI


def main(argv: list[str]):
    if not argv or argv[0] not in ("listar", "plantilla", "ver", "convertir"):
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
    if argv[0] == "convertir":
        from carteras import operaciones as ops
        if not opcion("--fecha"):
            print("Indicá la fecha de los ingresos: --fecha AAAA-MM-DD (se usan los cierres de ese día).")
            return
        try:
            cartera = excel.leer(argv[1])
            if cartera.operaciones:
                print(f"{cartera.nombre} ya tiene operaciones.")
                return
            lista = ops.desde_foto(cartera, date.fromisoformat(opcion("--fecha")))
            copia = excel.carpeta() / "anteriores" / f"{excel.ruta(argv[1]).stem}_antes_de_operaciones.xlsx"
            copia.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(excel.ruta(argv[1]), copia)
            excel.guardar(excel.Cartera(cartera.nombre, [], cartera.supuestos, [], lista))
        except (ValueError, ErrorAPI) as e:
            print(f"Error: {str(e).splitlines()[0]}")
            return
        print(f"{cartera.nombre}: {len(lista)} operaciones creadas (la versión anterior quedó en {copia}).")
        return
    try:
        fecha = date.fromisoformat(opcion("--fecha")) if opcion("--fecha") else None
        v = valuar.valuar(excel.leer(argv[1]), opcion("--moneda", "pesos"), fecha)
    except (ValueError, ErrorAPI) as e:
        print(f"Error: {str(e).splitlines()[0]}")
        return
    print(valuar.texto(v))
    if "--excel" in argv:
        print(f"\nGuardada en {excel.guardar_valuacion(v)}")


if __name__ == "__main__":
    main(sys.argv[1:])
