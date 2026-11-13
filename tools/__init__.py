"""Registro de herramientas, agrupadas por agente.

Cada archivo de esta carpeta aporta pares (definición, función), independientes
de LangGraph. Acá se convierten al formato de LangChain y se reparten:
cada agente recibe solo las herramientas que necesita.
"""
import functools

from langchain_core.tools import StructuredTool

from . import bonos, calendario, datos_macro, noticias, precios, python_exec


def _segura(nombre: str, funcion):
    """Si la herramienta falla, devuelve el error como texto para que el modelo lo vea y lo corrija."""
    @functools.wraps(funcion)
    def envoltura(**argumentos):
        try:
            return funcion(**argumentos)
        except Exception as e:
            return f"Error al ejecutar {nombre}: {e}"
    return envoltura


def _convertir(pares: list) -> list[StructuredTool]:
    return [
        StructuredTool(
            name=definicion["name"],
            description=definicion["description"],
            args_schema=definicion["parameters"],  # se reutiliza la definición tal cual
            func=_segura(definicion["name"], funcion),
        )
        for definicion, funcion in pares
    ]


HERRAMIENTAS_MACRO = _convertir([*datos_macro.HERRAMIENTAS, *precios.HERRAMIENTAS, *bonos.HERRAMIENTAS, *calendario.HERRAMIENTAS,
                                 (python_exec.DEFINICION, python_exec.ejecutar)])
HERRAMIENTAS_NOTICIAS = _convertir([*noticias.HERRAMIENTAS, *calendario.HERRAMIENTAS])
