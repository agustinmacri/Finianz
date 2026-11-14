"""Pruebas del armado del grafo: agentes, rutas y reparto de herramientas (sin llamar al modelo).
Correr con:
    python -m tests.test_grafo
"""


def test_reparto_de_herramientas():
    import tools
    macro = {t.name for t in tools.HERRAMIENTAS_MACRO}
    renta_fija = {t.name for t in tools.HERRAMIENTAS_RENTA_FIJA}
    bonos = {"calcular_bono", "calcular_breakevens", "proyectar_cer", "proyectar_tamar", "proyectar_dolar"}
    assert bonos <= renta_fija and not bonos & macro                 # el macro no ve herramientas de bonos
    assert {"buscar_indicador", "inflacion_acumulada", "consultar_fred"} <= macro


def test_rutas():
    from graph.router import elegir_destino
    assert elegir_destino({"ruta": "renta_fija"}) == ["agente_renta_fija"]
    assert elegir_destino({"ruta": "macro+renta_fija"}) == ["agente_macro", "agente_renta_fija"]
    assert elegir_destino({"ruta": "general"}) == ["responder"]


def test_grafo():
    from graph.builder import construir_grafo
    nodos = set(construir_grafo().get_graph().nodes)
    assert {"router", "agente_macro", "agente_renta_fija", "agente_noticias", "responder"} <= nodos


if __name__ == "__main__":
    for prueba in (test_reparto_de_herramientas, test_rutas, test_grafo):
        prueba()
        print(f"OK  {prueba.__name__}")
    print("Todas las pruebas del grafo pasaron.")
