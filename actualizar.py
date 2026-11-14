"""Actualiza las bases de datos locales de la carpeta datos/.

Uso:
    python actualizar.py

Hoy carga los feriados (datos/feriados.db) y el calendario de publicaciones
(datos/publicaciones.db): las del INDEC desde sus PDF, las que siguen una regla de días
hábiles (ISM, recaudación) y las de EE. UU. desde FRED. También suma los cierres nuevos
de los activos seguidos a la base de precios (datos/precios.db) y los valores nuevos del CER
la TAMAR y el A3500 a la base de series (datos/series.db), y las expectativas del REM
(Excel en fuentes/rem/) a datos/rem.db.
Conviene correrlo después de actualizar la librería holidays, de editar
calendarios/feriados_ajustes.toml o calendarios/publicaciones.toml, de agregar un PDF
del INDEC en calendarios/indec/, y una vez por semana para traer las fechas nuevas de FRED.
"""
import sys

import config
from carga_datos import catalogo, feriados, precios, publicaciones_fred, publicaciones_indec, publicaciones_regla, rem, series
from admin_datos.feriados import NOMBRES_CALENDARIO
from conexiones.http import ErrorAPI


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

    reglas = publicaciones_regla.cargar()
    print(f"\nPublicaciones por regla de días hábiles ({reglas['desde']} a {reglas['hasta']}):")
    for codigo, proxima in reglas["proximas"].items():
        print(f"  {codigo:<18} próxima: {proxima or '(sin fecha)'}")

    _publicaciones_fred()
    _series()
    _rem()
    _precios()


def _publicaciones_fred():
    print("\nPublicaciones de EE. UU. (FRED):")
    if not config.FRED_API_KEY:
        print("  Se omitió: falta FRED_API_KEY en el .env (clave gratuita en https://fredaccount.stlouisfed.org/apikeys).")
        return
    try:
        eeuu = publicaciones_fred.cargar()
    except ErrorAPI as e:
        print(f"  No se actualizaron (quedan las fechas de la carga anterior): {e}")
        return
    print(f"  {eeuu['total']} fechas del {eeuu['desde']} al {eeuu['hasta']}")
    for codigo, datos in eeuu["por_codigo"].items():
        print(f"  {codigo:<18} próxima: {datos['proxima'] or '(sin fecha)'}")
    for aviso in eeuu["avisos"]:
        print(f"  Aviso: {aviso}")


def _rem():
    print("\nREM del BCRA (Excel en fuentes/rem/):")
    try:
        resumen = rem.cargar()
    except (ValueError, OSError) as e:
        print(f"  error: {e}")
        return
    if not resumen:
        print("  no hay Excel cargados: bajá las tablas del REM del sitio del BCRA a fuentes/rem/")
    for relevamiento, filas in resumen.items():
        print(f"  relevamiento {relevamiento}: {filas} valores")


def _series():
    print("\nSeries diarias (BCRA):")
    for variable, nuevos in series.actualizar_todas().items():
        if isinstance(nuevos, str):
            print(f"  {variable:<10} {nuevos}")
            continue
        primera, ultima, cantidad = series.db.rango(variable) or ("-", "-", 0)
        print(f"  {variable:<10} {nuevos} valores nuevos ({cantidad} en la base, del {primera} al {ultima})")


def _precios():
    print("\nPrecios de los activos seguidos (PPI):")
    if not (config.PPI_API_KEY and config.PPI_API_SECRET):
        print("  Se omitió: faltan PPI_API_KEY y PPI_API_SECRET en el .env.")
        return
    resultado = precios.actualizar_todos()
    if not resultado:
        print("  Todavía no hay activos seguidos: se agregan solos la primera vez que consultás uno.")
    for ticker, nuevos in resultado.items():
        print(f"  {ticker:<10} {nuevos if isinstance(nuevos, str) else f'{nuevos} cierres nuevos'}")


if __name__ == "__main__":
    main()