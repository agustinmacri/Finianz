"""Actualiza las bases de datos locales de la carpeta datos/.

Uso:
    python actualizar.py

Hoy carga los feriados (datos/feriados.db). Más adelante va a sumar las demás ingestas
(calendario del INDEC, publicaciones de EE. UU., precios).
Conviene correrlo después de actualizar la librería holidays o de editar
calendarios/feriados_ajustes.toml.
"""
import sys

from carga_datos import feriados
from admin_datos.feriados import NOMBRES_CALENDARIO


def main():
    try:
        resumen = feriados.cargar()
    except feriados.ErrorAjustes as e:
        sys.exit(f"No se actualizó nada. Corregí el archivo de ajustes:\n  {e}")

    print(f"Feriados cargados de {resumen['desde']} a {resumen['hasta']}:")
    for calendario, cantidad in resumen["por_calendario"].items():
        print(f"  {NOMBRES_CALENDARIO[calendario]:<14} {cantidad:>4}")
    if "byma_aproximado_hasta" in resumen:
        print(f"  (BYMA hasta {resumen['byma_aproximado_hasta']}: aproximado con el calendario nacional)")
    print(f"Ajustes manuales aplicados: {resumen['ajustes']}")


if __name__ == "__main__":
    main()
