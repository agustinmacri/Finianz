"""Carteras de clientes para el agente de renta fija: listarlas y valuarlas (los Excel están en datos/carteras/)."""
from carteras import excel, valuar


def listar_carteras() -> str:
    nombres = excel.listar()
    if not nombres:
        return (f"No hay carteras cargadas. Se cargan como Excel en {excel.carpeta()} "
                "(plantilla: python -m carteras plantilla).")
    return "Carteras cargadas: " + ", ".join(nombres)


def ver_cartera(nombre: str, moneda: str = "pesos", guardar_excel: bool = False) -> str:
    try:
        v = valuar.valuar(excel.leer(nombre), moneda or "pesos")
    except ValueError as e:
        return f"No se pudo valuar la cartera: {e}"
    salida = valuar.texto(v)
    if guardar_excel:
        salida += f"\nGuardada en {excel.guardar_valuacion(v)}"
    return salida


LISTAR_CARTERAS = {
    "name": "listar_carteras",
    "description": "Lista las carteras de clientes cargadas en el sistema (Excel en datos/carteras/).",
    "parameters": {"type": "object", "properties": {}},
}
VER_CARTERA = {
    "name": "ver_cartera",
    "description": ("Valúa una cartera de cliente con la calculadora de Finianz: por activo, tipo, descripción, ticker, "
                    "TIR propia (tasa fija: TIR; CER: CER + real; TAMAR: spread; dollar linked y hard dollar: TIR en "
                    "USD), TIR nominal en base a la proyección (supuestos de la cartera, por defecto el REM), nominales, "
                    "precio, total, % de la cartera y duration. Renta variable sin tasas ni duration. Hard dollar ley "
                    "AR al MEP y ley NY al CCL. moneda: 'pesos' (por defecto), 'mep' o 'ccl' (dólares)."),
    "parameters": {"type": "object", "properties": {
        "nombre": {"type": "string", "description": "Nombre de la cartera (el del archivo, sin .xlsx)."},
        "moneda": {"type": "string", "enum": ["pesos", "mep", "ccl"], "description": "Moneda de la vista."},
        "guardar_excel": {"type": "boolean", "description": "Si el usuario pide el Excel de la valuación."},
    }, "required": ["nombre"]},
}

HERRAMIENTAS = [(LISTAR_CARTERAS, listar_carteras), (VER_CARTERA, ver_cartera)]
