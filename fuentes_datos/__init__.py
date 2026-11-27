"""Toda la información que entra de afuera.

- fuentes_datos/conexiones/: acceso a las fuentes externas (BCRA, FRED, PPI, datos.gob.ar, noticias), sin IA.
- carga/: procesos que traen datos de esas fuentes y los guardan en las bases de datos/ (feriados, publicaciones,
  series, precios, REM) y el lector de fichas de documentos con los avisos del Tesoro y sus novedades.
- bases/: lectura y escritura de las bases SQLite de datos/.
- mercado.py: los datos de mercado de los bonos (precios, CER, A3500, TAMAR, feriados) que usan las calculadoras.
- manuales/: lo que se carga o corrige a mano y se sube a git: calendarios (ajustes de feriados, catálogo de
  publicaciones, PDF del INDEC), Excel del REM y escenarios propios.

Las bases y las carteras de clientes viven en datos/ (fuera de git).
"""
