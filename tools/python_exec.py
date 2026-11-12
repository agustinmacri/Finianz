"""Herramienta local: ejecuta código Python para hacer cálculos.

El código tiene acceso directo a las conexiones de datos (bcra, series_tiempo, fred):
el modelo trae los datos desde el propio código en vez de copiarlos a mano.

Corre en un proceso aparte con tiempo límite. Ojo: se ejecuta en TU máquina,
por eso por defecto pide confirmación (ver CONFIRMAR_CODIGO en config.py).
"""
import os
import subprocess
import sys
import tempfile

import config

# Se agrega al principio de todo código que escriba el modelo
PREAMBULO = """\
import math
from datetime import date
from conexiones import bcra, fred, series_tiempo
"""

DEFINICION = {
    "name": "ejecutar_python",
    "description": (
        "Ejecuta código Python y devuelve lo que imprime con print(). Usalo solo para calcular: "
        "nunca para escribir mensajes, razonar o avisar que falta un dato. "
        "Ya están importados math, date y estas funciones de datos, que devuelven listas "
        "[{'fecha': 'AAAA-MM-DD', 'valor': ...}] ordenadas de la más vieja a la más nueva:\n"
        "- bcra.buscar_variables(texto): variables del BCRA, con 'id', 'descripcion', 'ultima_fecha', 'ultimo_valor'.\n"
        "- bcra.obtener_serie(id_variable, desde=None, hasta=None): serie del BCRA. "
        "Las variables en % vienen como porcentaje (2.1 = 2,1%).\n"
        "- series_tiempo.obtener_serie(id_serie, desde=None, hasta=None, modo='valor'): serie de datos.gob.ar. "
        "modo: 'valor', 'variacion', 'variacion_interanual' o 'variacion_acumulada_anio'; "
        "las variaciones vienen como fracción (0.021 = 2,1%).\n"
        "- fred.obtener_serie(id_serie, desde=None, hasta=None, modo='valor'): serie de EE. UU. desde FRED "
        "(ej.: 'CPIAUCSL'). modo: 'valor', 'variacion', 'variacion_interanual' o 'variacion_anualizada'; "
        "las variaciones vienen en porcentaje (0.3 = 0,3%).\n"
        "Fechas en formato 'AAAA-MM-DD'; sin fechas traen el último año. "
        "Traé siempre los datos con estas funciones: nunca escribas números copiados a mano. "
        "Imprimí los datos usados (fecha y valor) además del resultado. "
        "También están disponibles pandas y numpy si están instalados."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "codigo": {"type": "string", "description": "Código Python a ejecutar"},
        },
        "required": ["codigo"],
    },
}

TIMEOUT_SEGUNDOS = 60  # más margen que antes: ahora el código puede consultar APIs


def ejecutar(codigo: str) -> str:
    if config.CONFIRMAR_CODIGO:
        print("\n--- El agente quiere ejecutar este código ---")
        print(codigo)
        print("---------------------------------------------")
        if input("¿Ejecutar? [s/N]: ").strip().lower() != "s":
            return "El usuario no autorizó la ejecución. Seguí sin este cálculo o explicá cómo hacerlo."

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(PREAMBULO + codigo)
        ruta = f.name

    # El proceso corre desde la carpeta del proyecto, para poder importar conexiones y config
    entorno = {**os.environ, "PYTHONPATH": str(config.BASE_DIR), "PYTHONIOENCODING": "utf-8"}
    try:
        res = subprocess.run(
            [sys.executable, ruta],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=TIMEOUT_SEGUNDOS,
            cwd=config.BASE_DIR,
            env=entorno,
        )
    except subprocess.TimeoutExpired:
        return f"Error: el código tardó más de {TIMEOUT_SEGUNDOS} segundos."
    finally:
        os.remove(ruta)

    salida = res.stdout
    if res.returncode != 0:
        salida += f"\nError:\n{res.stderr[-3000:]}"
    return salida.strip()[:10_000] or "(el código no imprimió nada)"