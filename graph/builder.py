"""Arma el grafo principal: router + agentes + respuesta final.

                       ┌→ agente_macro ────┐
    INICIO → router ───┤                   ├→ responder → FIN
                       ├→ agente_noticias ─┤
                       └───────────────────┘   (ruta "general": directo a responder)

Con la ruta "ambos", macro y noticias corren en paralelo y responder espera a los dos.
"""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from graph.agente import construir_agente, nodo_agente
from graph.errores import REINTENTOS_MODELO
from graph.responder import crear_responder
from graph.router import DESTINOS, crear_router, elegir_destino
from graph.state import Estado
from tools import HERRAMIENTAS_MACRO, HERRAMIENTAS_NOTICIAS


def construir_grafo(checkpointer=None):
    macro = construir_agente("macro", "macro.md", HERRAMIENTAS_MACRO)
    noticias = construir_agente("noticias", "noticias.md", HERRAMIENTAS_NOTICIAS)

    g = StateGraph(Estado)
    g.add_node("router", crear_router(), retry_policy=REINTENTOS_MODELO)
    g.add_node("agente_macro", nodo_agente(macro, "informe_macro"))
    g.add_node("agente_noticias", nodo_agente(noticias, "informe_noticias"))
    g.add_node("responder", crear_responder(), retry_policy=REINTENTOS_MODELO)

    g.add_edge(START, "router")
    nodos_posibles = sorted({nodo for nodos in DESTINOS.values() for nodo in nodos})
    g.add_conditional_edges("router", elegir_destino, nodos_posibles)
    g.add_edge("agente_macro", "responder")
    g.add_edge("agente_noticias", "responder")
    g.add_edge("responder", END)

    # El checkpointer guarda la conversación de cada hilo (thread_id).
    # InMemorySaver la guarda mientras el programa está abierto.
    return g.compile(checkpointer=checkpointer or InMemorySaver())
