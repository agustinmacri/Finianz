"""Delegación entre agentes: el agente de renta fija le puede pedir al agente macro datos que no están
guardados en el sistema o supuestos macro (trayectorias de inflación, dólar o TAMAR) para sus cálculos.

Se arma como una herramienta más del agente de renta fija. El agente macro corre como siempre, con sus
herramientas, y su respuesta vuelve como resultado de la herramienta. El macro no puede delegar a su vez.
"""
from langchain_core.messages import HumanMessage
from langchain_core.tools import StructuredTool

import config

DEFINICION = {
    "name": "consultar_agente_macro",
    "description": (
        "Le pide al agente macro un dato que no está en la base del sistema (por ejemplo, reservas, tasas de política, "
        "inflación núcleo o datos de EE. UU.) o un supuesto macro fundamentado (trayectoria de inflación mensual, "
        "devaluación o TAMAR) para usar en las proyecciones. Escribí la pregunta completa y pedí los supuestos en un "
        "formato utilizable (ej.: 'inflación mensual de cada mes hasta junio 2027 y anual de 2028')."
    ),
    "parameters": {"type": "object", "properties": {
        "pregunta": {"type": "string", "description": "Qué necesitás del agente macro, con todo el contexto"},
    }, "required": ["pregunta"]},
}


def crear_herramienta_macro(agente_macro) -> StructuredTool:
    def consultar(pregunta: str) -> str:
        try:
            pedido = ("Consulta del agente de renta fija, que va a usar tu respuesta para calcular bonos. "
                      "Respondé solo lo pedido, con datos, fechas y fuentes, y los supuestos en el formato que se indica.\n\n"
                      + pregunta)
            resultado = agente_macro.invoke({"messages": [HumanMessage(pedido)]},
                                            {"recursion_limit": config.MAX_ITERACIONES * 2 + 1})
            print("  ↪ [renta_fija → macro] respuesta recibida")
            return resultado["messages"][-1].text.strip() or "(el agente macro no respondió)"
        except Exception as e:
            return f"Error al consultar al agente macro: {e}"

    return StructuredTool(name=DEFINICION["name"], description=DEFINICION["description"],
                          args_schema=DEFINICION["parameters"], func=consultar)
