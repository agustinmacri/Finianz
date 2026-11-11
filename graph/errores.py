"""Clasificación de errores del proveedor del modelo y política de reintentos.

Está en su propio archivo porque lo usan nodes.py (para cambiar al modelo de respaldo),
los constructores de grafos (para los reintentos) y main.py (para el mensaje al usuario).
"""
from langgraph.types import RetryPolicy

# Errores pasajeros: saturación, cuota por minuto, fallas del servidor
ERRORES_TEMPORALES = ("503", "500", "502", "504", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "DEADLINE_EXCEEDED")


def es_temporal(error: Exception) -> bool:
    return any(codigo in str(error) for codigo in ERRORES_TEMPORALES)


# Si todos los modelos fallan por saturación, espera 5s, 10s y 20s antes de rendirse
REINTENTOS_MODELO = RetryPolicy(max_attempts=4, initial_interval=5, backoff_factor=2, max_interval=30,
                                retry_on=es_temporal)
