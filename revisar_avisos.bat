@echo off
rem Revisa los llamados y resultados de licitacion nuevos del Tesoro y los deja como borradores de fichas.
rem Para el Programador de tareas de Windows (ver README, "Avisos del Tesoro"). Deja lo que hizo en datos\avisos_tesoro.log
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo ==== %date% %time% ==== >> datos\avisos_tesoro.log
".venv\Scripts\python.exe" -m fuentes_datos.carga.avisos_tesoro >> datos\avisos_tesoro.log 2>&1
