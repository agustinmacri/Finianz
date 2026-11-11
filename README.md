# Finianz

Sistema multiagente en Python para asistir a un portfolio manager o asesor financiero en Argentina. Los agentes consultan datos oficiales y noticias, los analizan y responden en lenguaje natural, citando siempre la fuente y la fecha de cada dato.

Construido con [LangGraph](https://langchain-ai.github.io/langgraph/) y modelos Gemini de Google. Todas las fuentes de datos son gratuitas.

## Qué puede hacer hoy

| Agente | Qué hace | Fuentes |
|---|---|---|
| **Macro** | Busca y analiza indicadores: inflación, expectativas del REM, reservas, tipo de cambio, tasas, CER, UVA, actividad. Calcula acumulados, tasas reales y proyecciones. | API del BCRA, Series de Tiempo de datos.gob.ar |
| **Noticias** | Busca noticias sobre un tema y resume los titulares del día, con su implicancia para el mercado. | Google News (RSS), feeds de Ámbito |

Un **router** decide qué agente responde cada pregunta. Si hacen falta los dos, corren en paralelo y sus respuestas se integran en una sola.

Ejemplos de preguntas:

- *¿Cuál fue la última inflación y qué espera el REM?*
- *¿Cuánto da la inflación acumulada en el año?*
- *¿Qué pasó hoy en el mercado?*
- *¿Cómo viene la inflación y qué se dice de la próxima licitación?*

## Cómo funciona

```
                       ┌→ agente_macro ────┐
    pregunta → router ─┤                   ├→ responder → respuesta
                       ├→ agente_noticias ─┤
                       └───────────────────┘   (saludos: directo a responder)
```

- **Router:** una sola llamada al modelo, con salida estructurada. Elige entre `macro`, `noticias`, `ambos` o `general`.
- **Agentes:** cada uno es un subgrafo con su propio prompt y **solo sus herramientas**. Iteran entre el modelo y las herramientas hasta tener la respuesta.
- **Responder:** si respondió un solo agente, devuelve su informe tal cual, sin otra llamada al modelo. Si respondieron los dos, los integra.
- **Memoria:** la conversación guarda solo las preguntas y las respuestas finales. Las consultas internas de cada agente no se acumulan, y así el contexto se mantiene chico.

Principios de diseño:

- **No todo es un agente.** Los cálculos con una forma correcta (como la inflación acumulada) se hacen en código, no los resuelve el modelo.
- **Los datos nunca pasan por el modelo para calcular.** El código Python que escribe el agente trae los datos directamente de las APIs.
- **Siempre con fecha.** Cada respuesta indica la fecha del último dato disponible.

## Estructura del proyecto

```
Finianz/
├── main.py              # chat por terminal
├── config.py            # configuración central (lee el .env)
├── graph/               # orquestación con LangGraph
│   ├── builder.py       # grafo principal: router + agentes + responder
│   ├── router.py        # decide qué agente responde
│   ├── agente.py        # fábrica de agentes (loop modelo ↔ herramientas)
│   ├── responder.py     # respuesta final: directa o síntesis
│   ├── nodes.py         # modelos con respaldo y nodo "modelo"
│   ├── state.py         # estados del grafo
│   └── errores.py       # errores temporales y reintentos
├── tools/               # lo que ven los agentes
│   ├── datos_macro.py   # buscar_indicador, consultar_bcra, consultar_serie, inflacion_acumulada
│   ├── noticias.py      # buscar_noticias, titulares_recientes
│   └── python_exec.py   # ejecutar_python, con acceso a los datos
├── clients/             # acceso a fuentes externas, sin IA
│   ├── http.py          # timeouts, reintentos y caché comunes
│   ├── bcra.py          # API del BCRA (Principales Variables v4)
│   ├── series_tiempo.py # API de Series de Tiempo de datos.gob.ar
│   └── noticias.py      # Google News RSS y feeds de medios
├── prompts/             # instrucciones de cada agente
└── docs/
    └── arquitectura-multiagente.md   # arquitectura completa y plan por fases
```

Las capas están separadas a propósito: `clients/` no sabe nada de IA, `tools/` no depende de LangGraph y `graph/` solo orquesta. Cambiar el modelo, el framework o una fuente de datos afecta a una sola capa.

## Instalación

Requiere Python 3.11 o superior.

```bash
git clone https://github.com/agustinmacri/Finianz.git
cd Finianz
python -m venv .venv
source .venv/Scripts/activate      # Windows (Git Bash)
# source .venv/bin/activate        # macOS / Linux
pip install -r requirements.txt
cp .env.example .env
```

Completá el `.env` con tu clave de Gemini, que se obtiene gratis en [Google AI Studio](https://aistudio.google.com/apikey).

> Ubicá el proyecto fuera de carpetas sincronizadas (OneDrive, Dropbox): la sincronización puede dañar archivos del entorno virtual.

## Configuración (`.env`)

| Variable | Qué hace | Por defecto |
|---|---|---|
| `GEMINI_API_KEY` | Clave de la API de Gemini | (obligatoria) |
| `GEMINI_MODEL` | Modelo principal | `gemini-3.1-flash-lite` |
| `GEMINI_MODELOS_RESPALDO` | Modelos a usar si el principal está saturado, separados por coma | (ninguno) |
| `MAX_ITERACIONES` | Tope de vueltas modelo ↔ herramientas por pregunta | `15` |
| `CONFIRMAR_CODIGO` | Pedir confirmación antes de ejecutar el código Python que escribe el agente | `true` |
| `CACHE_MINUTOS` | Cuánto tiempo se reutiliza una respuesta de las APIs de datos | `60` |
| `CACHE_NOTICIAS_MINUTOS` | Ídem para noticias | `15` |

El `.env` contiene tu clave: nunca lo subas al repositorio (ya está en el `.gitignore`).

## Uso

```bash
python main.py                                   # modo conversación
python main.py "¿Cuál fue la última inflación?"  # una sola pregunta
```

En la terminal se ve qué agente responde y qué herramientas usa:

```
Vos: ¿cómo viene la inflación y qué dicen las noticias del BCRA?
  🧭 📊 macro + 📰 noticias
  🔧 [macro] buscar_indicador(texto='inflacion mensual')
  🔧 [noticias] buscar_noticias(tema='BCRA')
```

Comandos durante la conversación:

| Comando | Qué hace |
|---|---|
| `nuevo` | Empieza una conversación desde cero |
| `reintentar` | Si hubo un error temporal del modelo, continúa desde el paso donde se cortó, sin repetir lo que ya se hizo |
| `salir` | Termina |

## Seguridad

La herramienta `ejecutar_python` corre en tu computadora el código que escribe el agente. Con `CONFIRMAR_CODIGO=true`, te muestra el código y pide confirmación antes de ejecutarlo. Desactivalo solo cuando conozcas el tipo de código que genera.

## Hoja de ruta

El sistema se construye por fases. El detalle está en [`docs/arquitectura-multiagente.md`](docs/arquitectura-multiagente.md).

- [ ] **Fase A** (en curso): router + agentes macro y noticias ✓; falta el calendario de eventos.
- [ ] **Fase B:** base de datos local, ingesta, precios de mercado, cartera y registro de pronósticos.
- [ ] **Fase C:** calculadoras de bonos y agente de renta fija.
- [ ] **Fase D:** agente de escenarios y estratega (retornos esperados, estrés, límites regulatorios).
- [ ] **Fase E:** redactor de informes y revisión humana.
- [ ] **Fase F:** agente de equity (balances, DCF, comparables).

## Aviso

Finianz es una herramienta de análisis y no constituye asesoramiento financiero. Los datos provienen de fuentes públicas que pueden tener demoras o errores; verificá siempre las cifras antes de tomar decisiones.
