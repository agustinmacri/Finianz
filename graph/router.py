"""Router: decide qué agente(s) responden cada pregunta.

Es una sola llamada a un modelo barato con salida estructurada: no usa herramientas
ni escribe texto, solo elige un destino. Así las preguntas simples no recorren todo el sistema.
"""
from typing import Literal

from pydantic import BaseModel, Field

from graph.nodes import cargar_prompt, crear_modelos, invocar_con_respaldo, mensaje_sistema
from graph.state import Estado

# El router solo necesita lo último de la conversación para entender preguntas como "¿y el mes anterior?"
HISTORIAL_ROUTER = 6


class Ruta(BaseModel):
    destino: Literal["macro", "noticias", "ambos", "general"] = Field(
        description="macro: datos e indicadores; noticias: hechos y novedades; "
                    "ambos: necesita datos y noticias; general: saludos o preguntas sobre la conversación"
    )


def crear_router():
    prompt = cargar_prompt("router.md")
    modelos = crear_modelos(preparar=lambda llm: llm.with_structured_output(Ruta))

    def router(estado: Estado) -> dict:
        ruta = invocar_con_respaldo(modelos, [mensaje_sistema(prompt)] + estado["messages"][-HISTORIAL_ROUTER:])
        # Se limpian los informes del turno anterior para que no se mezclen con los nuevos
        return {"ruta": ruta.destino, "informe_macro": None, "informe_noticias": None}

    return router


# Qué nodo(s) siguen según la ruta. Una lista con dos nodos los ejecuta en paralelo.
DESTINOS = {
    "macro": ["agente_macro"],
    "noticias": ["agente_noticias"],
    "ambos": ["agente_macro", "agente_noticias"],
    "general": ["responder"],
}


def elegir_destino(estado: Estado) -> list[str]:
    return DESTINOS.get(estado["ruta"], ["agente_macro"])
