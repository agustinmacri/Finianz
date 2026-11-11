"""Piezas comunes para los nodos que llaman al modelo.

- crear_modelos: arma el modelo principal y los de respaldo, ya preparados
  (con herramientas, con salida estructurada, o tal cual).
- invocar_con_respaldo: llama al principal y, si está saturado, a los de respaldo.
- crear_nodo_modelo: el nodo "modelo" del loop de cada agente.
"""
from datetime import date

from langchain_core.messages import SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from graph.errores import es_temporal


def cargar_prompt(archivo: str) -> str:
    return (config.PROMPTS_DIR / archivo).read_text(encoding="utf-8")


def mensaje_sistema(prompt: str) -> SystemMessage:
    # La fecha se calcula en cada llamada: el modelo no sabe qué día es
    return SystemMessage(f"{prompt}\n\nFecha de hoy: {date.today().isoformat()}")


def crear_modelos(modelo: str = config.GEMINI_MODEL, respaldos: list[str] = config.GEMINI_MODELOS_RESPALDO,
                  preparar=lambda llm: llm) -> list[tuple[str, object]]:
    """Lista [(nombre, modelo)] con el principal primero y los de respaldo después.

    preparar: qué hacerle a cada modelo antes de usarlo, por ejemplo bind_tools(...)
    o with_structured_output(...).
    """
    # max_retries bajo: si un modelo está saturado, conviene pasar rápido al de respaldo
    return [
        (nombre, preparar(ChatGoogleGenerativeAI(model=nombre, api_key=config.GEMINI_API_KEY, max_retries=1)))
        for nombre in [modelo, *respaldos]
    ]


def invocar_con_respaldo(modelos: list[tuple[str, object]], mensajes: list):
    for i, (nombre, llm) in enumerate(modelos):
        try:
            return llm.invoke(mensajes)
        except Exception as e:
            hay_otro = i < len(modelos) - 1
            if not (es_temporal(e) and hay_otro):
                raise  # error no temporal, o no quedan modelos: lo manejan los reintentos del grafo
            print(f"  ⚠️  {nombre} no disponible, probando con {modelos[i + 1][0]}")


def crear_nodo_modelo(prompt_file: str, herramientas: list, modelo: str = config.GEMINI_MODEL):
    """Nodo que llama al modelo con un prompt y un conjunto de herramientas propios."""
    prompt = cargar_prompt(prompt_file)
    modelos = crear_modelos(modelo, preparar=lambda llm: llm.bind_tools(herramientas))

    def llamar_modelo(estado) -> dict:
        respuesta = invocar_con_respaldo(modelos, [mensaje_sistema(prompt)] + estado["messages"])
        return {"messages": [respuesta]}

    return llamar_modelo
