"""Arma el grafo principal: router + agentes + respuesta final.

                       ┌→ agente_macro ──────┐
    INICIO → router ───┼→ agente_renta_fija ─┼→ responder → FIN
                       └→ agente_noticias ───┘   (sin agentes, "general": directo a responder)

El router elige uno o varios agentes; si son varios, corren en paralelo y responder espera a todos.
"""
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from graph.agente import construir_agente, nodo_agente
from graph.errores import REINTENTOS_MODELO
from graph.responder import crear_responder
from graph.router import AGENTES, crear_router, elegir_destino
from graph.state import Estado
from tools import HERRAMIENTAS_MACRO, HERRAMIENTAS_NOTICIAS, HERRAMIENTAS_RENTA_FIJA


def construir_grafo(checkpointer=None):
    agentes = {
        "macro": construir_agente("macro", "macro.md", HERRAMIENTAS_MACRO),
        "renta_fija": construir_agente("renta_fija", "renta_fija.md", HERRAMIENTAS_RENTA_FIJA),
        "noticias": construir_agente("noticias", "noticias.md", HERRAMIENTAS_NOTICIAS),
    }

    g = StateGraph(Estado)
    g.add_node("router", crear_router(), retry_policy=REINTENTOS_MODELO)
    for nombre in AGENTES:
        g.add_node(f"agente_{nombre}", nodo_agente(agentes[nombre], f"informe_{nombre}"))
        g.add_edge(f"agente_{nombre}", "responder")
    g.add_node("responder", crear_responder(), retry_policy=REINTENTOS_MODELO)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", elegir_destino, [f"agente_{a}" for a in AGENTES] + ["responder"])
    g.add_edge("responder", END)

    # El checkpointer guarda la conversación de cada hilo (thread_id).
    # InMemorySaver la guarda mientras el programa está abierto.
    return g.compile(checkpointer=checkpointer or InMemorySaver())
