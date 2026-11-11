"""Respuesta final del turno.

- Si respondió un solo agente: su informe va tal cual (sin gastar otra llamada al modelo).
- Si respondieron los dos: un modelo los integra en una sola respuesta.
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
            nombre: texto
            for nombre, texto in (("macro", estado.get("informe_macro")), ("noticias", estado.get("informe_noticias")))
            if texto
        }

        if len(informes) == 1:
            texto = next(iter(informes.values()))
        elif len(informes) == 2:
            pregunta = estado["messages"][-1].text
            pedido = (f"Pregunta del usuario: {pregunta}\n\n"
                      f"INFORME DEL AGENTE MACRO:\n{informes['macro']}\n\n"
                      f"INFORME DEL AGENTE DE NOTICIAS:\n{informes['noticias']}")
            texto = invocar_con_respaldo(modelos, [mensaje_sistema(prompt_sintesis), HumanMessage(pedido)]).text
        else:
            texto = invocar_con_respaldo(modelos, [mensaje_sistema(prompt_general)] + estado["messages"][-8:]).text

        return {"messages": [AIMessage(texto.strip() or "(no se obtuvo respuesta)")]}

    return responder
