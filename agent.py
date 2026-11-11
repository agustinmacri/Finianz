"""El agente: un loop que llama al modelo, ejecuta herramientas y repite hasta tener la respuesta.

Esta clase está pensada para ser la base del sistema multiagente más adelante:
cada agente futuro va a ser una instancia (o subclase) con otro prompt y otras herramientas.
"""
from datetime import date

from google import genai
from google.genai import types

import config
import tools


class Agente:
    def __init__(self, nombre: str, prompt_file: str, modelo: str = config.GEMINI_MODEL):
        self.nombre = nombre
        self.modelo = modelo
        self.cliente = genai.Client(api_key=config.GEMINI_API_KEY)
        prompt = (config.PROMPTS_DIR / prompt_file).read_text(encoding="utf-8")
        self.config = types.GenerateContentConfig(
            # El modelo no sabe qué día es: se lo decimos para que pueda juzgar si un dato es reciente
            system_instruction=f"{prompt}\n\nFecha de hoy: {date.today().isoformat()}",
            tools=tools.definiciones(),
        )
        self.historial: list[types.Content] = []  # memoria de la conversación actual

    def preguntar(self, pregunta: str) -> str:
        self.historial.append(types.Content(role="user", parts=[types.Part(text=pregunta)]))

        for _ in range(config.MAX_ITERACIONES):
            respuesta = self.cliente.models.generate_content(
                model=self.modelo, contents=self.historial, config=self.config
            )
            candidato = respuesta.candidates[0]
            # Se guarda el contenido tal cual: trae las firmas que Gemini exige en el turno siguiente
            self.historial.append(candidato.content)

            llamadas = [p.function_call for p in (candidato.content.parts or []) if p.function_call]
            if not llamadas:
                return self._texto_final(candidato)

            # El modelo pidió herramientas: las ejecutamos y le devolvemos los resultados
            resultados = []
            for llamada in llamadas:
                argumentos = dict(llamada.args or {})
                print(f"  🔧 {llamada.name}({', '.join(f'{k}={v!r}' for k, v in argumentos.items())})")
                salida = tools.ejecutar(llamada.name, argumentos)
                resultados.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=llamada.id, name=llamada.name, response={"resultado": salida}
                        )
                    )
                )
            self.historial.append(types.Content(role="user", parts=resultados))

        return "Se alcanzó el máximo de iteraciones sin una respuesta final."

    def reiniciar(self):
        self.historial = []

    def _texto_final(self, candidato) -> str:
        partes = candidato.content.parts or []
        salida = "".join(p.text for p in partes if p.text and not p.thought).strip()
        return salida or "(el modelo no devolvió texto)"