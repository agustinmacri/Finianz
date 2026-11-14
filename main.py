"""Punto de entrada: chat por terminal con el sistema de agentes.

Uso:
    python main.py                       # modo conversación
    python main.py "tu pregunta acá"     # una sola pregunta
"""
import sys
import uuid

from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError

import config
from graph.builder import construir_grafo
from graph.errores import es_temporal

ICONOS = {"macro": "📊 macro", "renta_fija": "💵 renta fija", "noticias": "📰 noticias", "general": "💬 general"}


def _icono_ruta(ruta: str | None) -> str:
    return " + ".join(ICONOS.get(parte, parte) for parte in (ruta or "general").split("+"))


def _agente_de(origen: tuple) -> str | None:
    """Qué agente hizo el paso. Si el agente macro corre dentro de una herramienta del de renta fija
    (delegación), el paso aparece anidado bajo renta fija: se muestra como "renta_fija → macro"."""
    if not origen:
        return None
    partes = [p.split(":")[0] for p in origen]
    agente = partes[0].removeprefix("agente_")
    return f"{agente} → macro" if "herramientas" in partes[1:] else agente


def preguntar(grafo, pregunta: str | None, hilo: str) -> str:
    """Envía la pregunta al grafo, muestra qué hace cada agente y devuelve la respuesta final.

    Con pregunta=None, retoma la última pregunta desde el paso donde se cortó
    (LangGraph guarda cada paso en el checkpointer).
    """
    cfg = {
        "configurable": {"thread_id": hilo},
        # límite de pasos por grafo: cada vuelta modelo → herramientas son 2 pasos
        "recursion_limit": config.MAX_ITERACIONES * 2 + 1,
    }
    entrada = {"messages": [HumanMessage(pregunta)]} if pregunta else None
    respuesta = None
    try:
        # subgraphs=True: también recibimos lo que pasa dentro de cada agente
        for origen, paso in grafo.stream(entrada, cfg, stream_mode="updates", subgraphs=True):
            agente = _agente_de(origen)
            for nodo, cambios in paso.items():
                cambios = cambios or {}
                if nodo == "router":
                    print(f"  🧭 {_icono_ruta(cambios.get('ruta'))}")
                elif nodo == "modelo" and agente:
                    for mensaje in cambios.get("messages", []):
                        for llamada in mensaje.tool_calls:
                            args = ", ".join(f"{k}={v!r}" for k, v in llamada["args"].items())
                            print(f"  🔧 [{agente}] {llamada['name']}({args})")
                elif nodo == "responder":
                    respuesta = cambios["messages"][-1].text
    except GraphRecursionError:
        return "Se alcanzó el máximo de iteraciones sin una respuesta final."
    except Exception as e:
        # El programa no se cae: la conversación queda guardada y se puede retomar
        detalle = str(e).splitlines()[0][:200]
        if es_temporal(e):
            return (f"(Error temporal del modelo: {detalle})\n"
                    "La conversación quedó guardada. Escribí 'reintentar' en un rato para continuar desde donde se cortó.")
        return f"(Error: {detalle})\nEste error no es temporal: revisá el mensaje o compartilo para analizarlo."

    return (respuesta or "").strip() or "(no se obtuvo respuesta)"


def main():
    if not config.GEMINI_API_KEY:
        sys.exit("Falta GEMINI_API_KEY. Copiá .env.example a .env y poné tu clave de Google AI Studio.")

    grafo = construir_grafo()
    hilo = str(uuid.uuid4())  # cada hilo es una conversación independiente

    if len(sys.argv) > 1:
        print(preguntar(grafo, " ".join(sys.argv[1:]), hilo))
        return

    print(f"Finianz listo ({config.GEMINI_MODEL}): agentes macro, renta fija y noticias.\n"
          "Comandos: 'nuevo' (reiniciar), 'reintentar' (si hubo un error), 'salir'.\n")
    while True:
        try:
            pregunta = input("Vos: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not pregunta:
            continue
        if pregunta.lower() in ("salir", "exit"):
            break
        if pregunta.lower() == "nuevo":
            hilo = str(uuid.uuid4())  # hilo nuevo = conversación desde cero
            print("(conversación reiniciada)\n")
            continue
        if pregunta.lower() == "reintentar":
            print(f"\nFinianz:\n{preguntar(grafo, None, hilo)}\n")
            continue
        print(f"\nFinianz:\n{preguntar(grafo, pregunta, hilo)}\n")


if __name__ == "__main__":
    main()
