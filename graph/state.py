"""Estados de los grafos: la información que viaja entre los nodos.

Hay dos niveles:
- Estado: el del sistema completo. Guarda la conversación (solo preguntas y respuestas finales)
  y lo que produce cada agente en el turno actual.
- EstadoAgente: el de cada agente por dentro. Ahí quedan sus llamadas a herramientas,
  que NO pasan a la conversación general: así el contexto se mantiene limpio.
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class Estado(TypedDict, total=False):
    # add_messages: cada nodo AGREGA mensajes a la lista, en vez de reemplazarla
    messages: Annotated[list[AnyMessage], add_messages]
    ruta: str                   # decisión del router: macro, noticias, ambos o general
    informe_macro: str | None   # respuesta del agente macro en este turno
    informe_noticias: str | None


class EstadoAgente(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
