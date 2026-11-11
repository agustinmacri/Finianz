"""Actualiza las bases de datos locales de la carpeta datos/.

Uso:
    python actualizar.py

Hoy carga los feriados (datos/feriados.db) y el calendario del INDEC (datos/publicaciones.db).
Más adelante va a sumar las demás ingestas (publicaciones de EE. UU., precios).
Conviene correrlo después de actualizar la librería holidays o de editar
calendarios/feriados_ajustes.toml, o de agregar un PDF del INDEC en calendarios/indec/.
"""
import sys

from carga_datos import catalogo, feriados, publicaciones_indec
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

    try:
        indec = publicaciones_indec.cargar()
    except catalogo.ErrorCatalogo as e:
        sys.exit(f"\nNo se actualizaron las publicaciones. Corregí el catálogo:\n  {e}")
    print(f"\nCalendario del INDEC ({', '.join(indec['archivos']) or 'sin PDF en calendarios/indec/'}):")
    print(f"  {indec['total']} publicaciones del {indec['desde']} al {indec['hasta']}, "
          f"{indec['seguidas']} de las que seguís")
    if indec["sin_encontrar"]:
        print(f"  No se encontraron en los PDF: {', '.join(indec['sin_encontrar'])} (revisá su 'patron' en el catálogo)")
    for aviso in indec["avisos"]:
        print(f"  Aviso: {aviso}")


if __name__ == "__main__":
    main()
