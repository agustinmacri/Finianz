# Agente básico: búsqueda y análisis

Un agente que busca información puntual en la web y la analiza, haciendo los cálculos con Python.

## Estructura

```
agente_basico/
├── main.py            # chat por terminal
├── agent.py           # clase Agente: el loop modelo → herramientas → modelo
├── config.py          # parámetros (modelo, límites, confirmación de código)
├── prompts/
│   └── system.md      # instrucciones del agente (editalo para cambiar su comportamiento)
├── tools/
│   ├── __init__.py    # registro de herramientas + búsqueda web
│   └── python_exec.py # ejecuta código Python para cálculos
├── requirements.txt
└── .env.example
```

## Instalación

```bash
python -m venv venv
source venv/bin/activate          # en Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # en Windows: copy .env.example .env
```

Poné tu API key en `.env` (la sacás de https://console.anthropic.com).
La búsqueda web tiene que estar habilitada para tu organización en la consola.

## Uso

```bash
python main.py
python main.py "¿Cuál fue la última inflación mensual del INDEC y cuánto da anualizada?"
```

En modo conversación el agente recuerda las preguntas anteriores. `nuevo` reinicia, `salir` termina.

## Cómo extenderlo

- **Cambiar el comportamiento**: editá `prompts/system.md`.
- **Agregar una herramienta**: creá un archivo en `tools/` con una `DEFINICION` y una función, y sumalo a `LOCALES` en `tools/__init__.py`.
- **Pasar a multiagente**: creá otro prompt en `prompts/` e instanciá otro `Agente` con él.
