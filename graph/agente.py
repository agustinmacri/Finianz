"""Fábrica de agentes: cada agente es un subgrafo con su loop modelo ↔ herramientas.

    INICIO → modelo ──(¿pidió herramientas?)── no → FIN
               ↑              │ sí
               └── herramientas

Para sumar un agente nuevo alcanza con un prompt y una lista de herramientas.
"""
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

import config
from graph.errores import REINTENTOS_MODELO
from graph.nodes import crear_nodo_modelo
from graph.state import Estado, EstadoAgente

# Cuántos mensajes de la conversación recibe cada agente como contexto (preguntas y respuestas previas)
MAX_HISTORIAL = 8


def construir_agente(nombre: str, prompt_file: str, herramientas: list, modelo: str = config.GEMINI_MODEL):
    g = StateGraph(EstadoAgente)
    g.add_node("modelo", crear_nodo_modelo(prompt_file, herramientas, modelo), retry_policy=REINTENTOS_MODELO)
    g.add_node("herramientas", ToolNode(herramientas))

    g.add_edge(START, "modelo")
    # tools_condition devuelve "tools" o END; el diccionario traduce "tools" a nuestro nodo
    g.add_conditional_edges("modelo", tools_condition, {"tools": "herramientas", END: END})
    g.add_edge("herramientas", "modelo")

    # checkpointer=False: cada consulta al agente arranca limpia. Sus llamadas a herramientas
    # no se acumulan entre preguntas; la memoria de la conversación la lleva el grafo principal.
    return g.compile(name=nombre, checkpointer=False)


def nodo_agente(subgrafo, campo: str):
    """Envuelve un agente para usarlo como nodo del grafo principal.

    Le pasa las últimas preguntas y respuestas de la conversación (no los pasos internos
    de otros agentes) y guarda su respuesta final en `campo` del estado.
    """
    def ejecutar(estado: Estado, config: RunnableConfig) -> dict:
        historial = estado["messages"][-MAX_HISTORIAL:]
        resultado = subgrafo.invoke({"messages": historial}, config)
        return {campo: resultado["messages"][-1].text.strip()}

    return ejecutar
