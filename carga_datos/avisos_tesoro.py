"""Revisa si la Secretaría de Finanzas publicó llamados o resultados de licitación nuevos y los lee con el lector de
fichas (carga_datos/fichas_documentos.py): borradores de los bonos nuevos, valores de corte y cambios propuestos.
Nada se aprueba solo.

Cómo encuentra los avisos nuevos: argentina.gob.ar arma la dirección de cada noticia con su título, y como los
avisos repiten título, les agrega un número que va subiendo (…-en-dolares-16, …-en-dolares-17). Se guarda el último
número leído de cada serie y se prueba el siguiente; si no existe, se prueban un par más por si hubo un salto.
Limitación: un aviso con un título distinto del habitual (por ejemplo, con una conversión en el título) no cae en
ninguna serie; para esos está `leer <URL>` del lector de fichas, o agregar la serie abajo.

Uso:
    python -m carga_datos.avisos_tesoro              # revisa y lee los nuevos
    python -m carga_datos.avisos_tesoro estado       # último número leído de cada serie
    python -m carga_datos.avisos_tesoro desde <serie> <número>   # corrige desde dónde seguir

Para que corra solo, programalo en tu compu (ver README, "Avisos del Tesoro").
"""
import json
import sys
from datetime import date, datetime

import config
from carga_datos import fichas_documentos as fd

BASE = "https://www.argentina.gob.ar/noticias/"
SERIES = {
    "llamado": "llamado-licitacion-de-instrumentos-del-tesoro-nacional-denominados-en-pesos-y-en-dolares",
    "resultado": "resultado-de-la-licitacion-por-efectivo-de-instrumentos-del-tesoro-nacional-denominados",
}
# Últimos ya leídos a mano (Agustin, 15/11/2026): llamado del 05/11/2026 (-16) y resultado del 11/11/2026 (-17)
INICIAL = {"llamado": 16, "resultado": 17}
HUECOS = 2            # números seguidos que pueden faltar antes de dar la serie por al día
REGISTRO = None       # se resuelve en tiempo de ejecución: datos/avisos_tesoro.json


def _ruta():
    return REGISTRO or config.DATOS_DIR / "avisos_tesoro.json"


def cargar_registro() -> dict:
    ruta = _ruta()
    registro = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    registro.setdefault("series", {})
    for serie, numero in INICIAL.items():
        registro["series"].setdefault(serie, numero)
    registro.setdefault("leidos", [])
    return registro


def guardar_registro(registro: dict):
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(registro, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def url(serie: str, numero: int) -> str:
    return f"{BASE}{SERIES[serie]}-{numero}"


def existe(direccion: str) -> bool:
    """True si la página existe (200), False si no (404). Otros errores se informan: no se da por inexistente."""
    import requests
    respuesta = requests.get(direccion, timeout=30, headers=fd.NAVEGADOR)
    if respuesta.status_code == 404:
        return False
    respuesta.raise_for_status()
    return True


def revisar(lector=None, comprobar=existe, hoy: date | None = None) -> list[str]:
    """Lee los avisos nuevos de cada serie. Devuelve el informe en renglones."""
    lector = lector or fd.leer
    registro = cargar_registro()
    informe = []
    for serie in SERIES:
        ultimo = registro["series"][serie]
        numero, faltantes = ultimo + 1, 0
        while faltantes <= HUECOS:
            direccion = url(serie, numero)
            try:
                hay = comprobar(direccion)
            except Exception as e:
                informe.append(f"[{serie}] no se pudo consultar {direccion}: {str(e).splitlines()[0][:150]}. "
                               "Se reintenta la próxima vez.")
                break
            if not hay:
                faltantes += 1
                numero += 1
                continue
            try:
                resumen = lector(direccion, hoy=hoy) if hoy else lector(direccion)
            except Exception as e:
                # No se avanza: la próxima revisión lo vuelve a intentar
                informe.append(f"[{serie}] {direccion}: no se pudo leer ({str(e).splitlines()[0][:150]}). "
                               "Se reintenta la próxima vez.")
                break
            informe.append(f"[{serie} {numero}] {direccion}\n" + fd.describir(resumen))
            registro["series"][serie] = ultimo = numero
            registro["leidos"].append({"serie": serie, "numero": numero, "url": direccion,
                                       "leido": datetime.now().isoformat(timespec="minutes"),
                                       "documento": resumen.get("documento"), "fecha": resumen.get("fecha")})
            guardar_registro(registro)
            numero, faltantes = numero + 1, 0
    guardar_registro(registro)
    if not informe and fd.pendientes():
        # Sin avisos nuevos igual se reintenta el ticker de los borradores que no lo tienen (sale cerca de la liquidación)
        informe += fd.actualizar_borradores()
    if not informe:
        informe.append("No hay avisos nuevos del Tesoro (último llamado leído: "
                       f"{registro['series']['llamado']}, último resultado: {registro['series']['resultado']}).")
    return informe


def main(argv: list[str]):
    if argv and argv[0] == "estado":
        registro = cargar_registro()
        for serie, numero in registro["series"].items():
            print(f"{serie}: último leído {numero} → próximo a probar {url(serie, numero + 1)}")
        for leido in registro["leidos"][-5:]:
            print(f"  leído {leido['leido']}: {leido['url']}")
        return
    if argv and argv[0] == "desde":
        if len(argv) < 3 or argv[1] not in SERIES or not argv[2].isdigit():
            print(f"Uso: desde <{'|'.join(SERIES)}> <número del último ya leído>")
            return
        registro = cargar_registro()
        registro["series"][argv[1]] = int(argv[2])
        guardar_registro(registro)
        print(f"{argv[1]}: la próxima revisión empieza en {url(argv[1], int(argv[2]) + 1)}")
        return
    if argv:
        print(__doc__)
        return
    print("\n\n".join(revisar()))


if __name__ == "__main__":
    main(sys.argv[1:])
