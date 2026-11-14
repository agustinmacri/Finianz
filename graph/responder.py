"""Respuesta final del turno.

- Si respondió un solo agente: su informe va tal cual (sin gastar otra llamada al modelo).
- Si respondieron varios: un modelo los integra en una sola respuesta.
- Si el router eligió "general": un modelo responde con la conversación como contexto.

Solo esta respuesta final se agrega a la conversación.
"""
from langchain_core.messages import AIMessage, HumanMessage

from graph.nodes import cargar_prompt, crear_modelos, invocar_con_respaldo, mensaje_sistema
from graph.state import Estado


def crear_responder():
    prompt_sintesis = cargar_prompt("sintesis.md")
    prompt_general = cargar_prompt("general.md")
    modelos = crear_modelos()

    def responder(estado: Estado) -> dict:
        informes = {
            nombre: estado.get(f"informe_{clave}")
            for clave, nombre in (("macro", "MACRO"), ("renta_fija", "DE RENTA FIJA"), ("noticias", "DE NOTICIAS"))
            if estado.get(f"informe_{clave}")
        }

        if len(informes) == 1:
            texto = next(iter(informes.values()))
        elif len(informes) > 1:
            pregunta = estado["messages"][-1].text
            pedido = f"Pregunta del usuario: {pregunta}\n\n" + "\n\n".join(
                f"INFORME DEL AGENTE {nombre}:\n{texto}" for nombre, texto in informes.items())
            texto = invocar_con_respaldo(modelos, [mensaje_sistema(prompt_sintesis), HumanMessage(pedido)]).text
        else:
            texto = invocar_con_respaldo(modelos, [mensaje_sistema(prompt_general)] + estado["messages"][-8:]).text

        return {"messages": [AIMessage(texto.strip() or "(no se obtuvo respuesta)")]}

    return responder
