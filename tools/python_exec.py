"""Herramienta local: ejecuta código Python para hacer cálculos.

El código tiene acceso directo a las conexiones de datos (bcra, series_tiempo, fred):
el modelo trae los datos desde el propio código en vez de copiarlos a mano.

Corre en un proceso aparte con tiempo límite. Ojo: se ejecuta en TU máquina, por eso:
- por defecto pide confirmación (ver CONFIRMAR_CODIGO en config.py);
- corre sin las claves del broker ni del modelo;
- corre vigilado por tools/guardia.py: no puede leer el .env ni las bases, escribir archivos,
  lanzar programas ni conectarse a sitios que no sean las APIs de datos.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import config

# Se agrega al principio de todo código que escriba el modelo
PREAMBULO = """\
import math
from datetime import date
from conexiones import bcra, fred, series_tiempo
from calculos.series import transformar
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
        "- series_tiempo.obtener_serie(id_serie, desde=None, hasta=None): niveles de una serie de datos.gob.ar.\n"
        "- fred.obtener_serie(id_serie, desde=None, hasta=None): niveles de una serie de EE. UU. desde FRED "
        "(ej.: 'CPIAUCSL').\n"
        "- transformar(serie, modo): calcula variaciones sobre los niveles, en porcentaje (0.3 = 0,3%). "
        "modo: 'variacion', 'variacion_interanual', 'variacion_anualizada' o 'variacion_acumulada_anio'. "
        "Para variaciones, traé datos desde antes del período (por ejemplo, un año más).\n"
        "Fechas en formato 'AAAA-MM-DD'; sin fechas traen el último año. "
        "Traé siempre los datos con estas funciones: nunca escribas números copiados a mano. "
        "Imprimí los datos usados (fecha y valor) además del resultado. "
        "Por seguridad, el código no puede leer ni escribir archivos, lanzar programas ni conectarse "
        "a otros sitios: trabajá solo con estas funciones de datos. "
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

GUARDIA = (Path(__file__).parent / "guardia.py").read_text(encoding="utf-8")


def _sitios_permitidos() -> list[str]:
    """Las APIs de datos que puede usar el código."""
    urls = [config.BCRA_URL, config.SERIES_TIEMPO_URL, config.SERIES_BUSQUEDA_URL, config.FRED_URL]
    return sorted({urlparse(u).hostname for u in urls if urlparse(u).hostname})


def armar_script(codigo: str) -> str:
    """Preámbulo de datos + guardia activada + código del modelo."""
    activacion = f"activar({str(config.BASE_DIR)!r}, {str(config.CACHE_DIR)!r}, {_sitios_permitidos()!r})\n"
    return PREAMBULO + GUARDIA + "\n" + activacion + "del activar\n" + codigo


# Claves que el código escrito por el agente nunca recibe (ver también config.py)
CLAVES_OCULTAS = {"PPI_API_KEY", "PPI_API_SECRET", "GEMINI_API_KEY", "GOOGLE_API_KEY"}

TIMEOUT_SEGUNDOS = 60  # más margen que antes: ahora el código puede consultar APIs


def ejecutar(codigo: str) -> str:
    if config.CONFIRMAR_CODIGO:
        print("\n--- El agente quiere ejecutar este código ---")
        print(codigo)
        print("---------------------------------------------")
        if input("¿Ejecutar? [s/N]: ").strip().lower() != "s":
            return "El usuario no autorizó la ejecución. Seguí sin este cálculo o explicá cómo hacerlo."

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(armar_script(codigo))
        ruta = f.name

    # El proceso corre desde la carpeta del proyecto, para poder importar conexiones y config
    # Sin las claves del broker ni la del modelo: el código del agente solo necesita las APIs de datos.
    entorno = {k: v for k, v in os.environ.items() if k not in CLAVES_OCULTAS}
    entorno |= {"PYTHONPATH": str(config.BASE_DIR), "PYTHONIOENCODING": "utf-8", "FINIANZ_SUBPROCESO": "1"}
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