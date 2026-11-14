"""Router: decide qué agente(s) responden cada pregunta.

Es una sola llamada a un modelo barato con salida estructurada: no usa herramientas
ni escribe texto, solo elige los agentes. Así las preguntas simples no recorren todo el sistema.
"""
from typing import Literal

from pydantic import BaseModel, Field

from graph.nodes import cargar_prompt, crear_modelos, invocar_con_respaldo, mensaje_sistema
from graph.state import Estado

# El router solo necesita lo último de la conversación para entender preguntas como "¿y el mes anterior?"
HISTORIAL_ROUTER = 6
AGENTES = ("macro", "renta_fija", "noticias")      # en este orden se muestran y se integran


class Ruta(BaseModel):
    agentes: list[Literal["macro", "renta_fija", "noticias"]] = Field(
        description="Los agentes que tienen que responder: macro (indicadores económicos), renta_fija (bonos, letras, "
                    "curvas, rendimientos, breakevens, proyecciones) y/o noticias (hechos y novedades). Lista vacía para "
                    "saludos o preguntas sobre la conversación."
    )


def crear_router():
    prompt = cargar_prompt("router.md")
    modelos = crear_modelos(preparar=lambda llm: llm.with_structured_output(Ruta))

    def router(estado: Estado) -> dict:
        ruta = invocar_con_respaldo(modelos, [mensaje_sistema(prompt)] + estado["messages"][-HISTORIAL_ROUTER:])
        elegidos = [a for a in AGENTES if a in ruta.agentes]
        # Se limpian los informes del turno anterior para que no se mezclen con los nuevos
        return {"ruta": "+".join(elegidos) or "general",
                **{f"informe_{a}": None for a in AGENTES}}

    return router


def elegir_destino(estado: Estado) -> list[str]:
    """Qué nodo(s) siguen. Varios agentes corren en paralelo; sin agentes, directo a responder."""
    ruta = estado.get("ruta") or "general"
    if ruta == "general":
        return ["responder"]
    return [f"agente_{a}" for a in ruta.split("+") if a in AGENTES] or ["responder"]
