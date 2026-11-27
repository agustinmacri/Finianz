"""Novedades de la revisión automática de avisos del Tesoro: qué borradores, valores de corte y cambios propuestos
dejó cada aviso nuevo, para avisarlo (notificación de Windows y marca en la sección Fichas del panel) hasta que los
revises. Registro en datos/novedades_fichas.json (fuera del repo).

Uso:
    python -m fuentes_datos.carga.novedades            # las novedades sin ver
    python -m fuentes_datos.carga.novedades vistas     # marcarlas como vistas
    python -m fuentes_datos.carga.novedades probar     # mandar una notificación de prueba
"""
import json
import os
import subprocess
import sys
from datetime import datetime

import config

REGISTRO = None        # se resuelve en tiempo de ejecución: datos/novedades_fichas.json


def _ruta():
    return REGISTRO or config.DATOS_DIR / "novedades_fichas.json"


def _cargar() -> list[dict]:
    ruta = _ruta()
    try:
        return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else []
    except (json.JSONDecodeError, OSError):
        return []


def _guardar(lista: list[dict]):
    ruta = _ruta()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(lista[-200:], ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def registrar(resumen: dict, direccion: str) -> dict | None:
    """Guarda lo que dejó un aviso leído (si dejó algo para revisar). Devuelve la novedad o None."""
    novedad = {"cuando": datetime.now().isoformat(timespec="minutes"), "url": direccion,
               "documento": resumen.get("documento"), "fecha": resumen.get("fecha"),
               "nuevos": list(resumen.get("nuevos") or []),
               "completados": [c for c, _ in resumen.get("completados") or []],
               "cortes": list(resumen.get("cortes") or []), "cambios": list(resumen.get("cambios") or []),
               "vista": False}
    if not (novedad["nuevos"] or novedad["completados"] or novedad["cortes"] or novedad["cambios"]):
        return None
    lista = _cargar()
    lista.append(novedad)
    _guardar(lista)
    return novedad


def sin_ver() -> list[dict]:
    return [n for n in _cargar() if not n.get("vista")]


def marcar_vistas() -> int:
    lista = _cargar()
    cuantas = sum(1 for n in lista if not n.get("vista"))
    for n in lista:
        n["vista"] = True
    _guardar(lista)
    return cuantas


def resumen_texto(novedades: list[dict]) -> str:
    """Una línea para la notificación: cuántos borradores nuevos, completados, cortes y cambios, con los tickers."""
    nuevos = [c for n in novedades for c in n["nuevos"]]
    completados = [c for n in novedades for c in n["completados"]]
    partes = []
    if nuevos:
        partes.append(f"{len(nuevos)} borrador{'es' if len(nuevos) > 1 else ''} nuevo{'s' if len(nuevos) > 1 else ''}"
                      f" ({', '.join(nuevos[:4])}{'…' if len(nuevos) > 4 else ''})")
    if completados:
        partes.append(f"{len(completados)} completado{'s' if len(completados) > 1 else ''}")
    cortes = sum(len(n["cortes"]) for n in novedades)
    if cortes:
        partes.append(f"{cortes} valor{'es' if cortes > 1 else ''} de corte")
    cambios = sum(len(n["cambios"]) for n in novedades)
    if cambios:
        partes.append(f"{cambios} cambio{'s' if cambios > 1 else ''} propuesto{'s' if cambios > 1 else ''}")
    return ", ".join(partes) + ". Revisalos en Fichas (panel) o con: python -m fuentes_datos.carga.fichas_documentos pendientes"


_SCRIPT_TOAST = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$plantilla = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$textos = $plantilla.GetElementsByTagName("text")
$textos.Item(0).AppendChild($plantilla.CreateTextNode($env:FINIANZ_TITULO)) > $null
$textos.Item(1).AppendChild($plantilla.CreateTextNode($env:FINIANZ_TEXTO)) > $null
$aviso = [Windows.UI.Notifications.ToastNotification]::new($plantilla)
$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show($aviso)
"""


def notificar(titulo: str, texto: str) -> str:
    """Notificación de Windows (sin instalar nada: PowerShell). En otros sistemas no hace nada. Devuelve qué pasó."""
    if os.name != "nt":
        return "sin notificación (solo en Windows)"
    entorno = dict(os.environ, FINIANZ_TITULO=titulo[:120], FINIANZ_TEXTO=texto[:300])
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _SCRIPT_TOAST],
                           env=entorno, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError) as e:
        return f"no se pudo notificar ({e})"
    return "notificación enviada" if r.returncode == 0 else f"no se pudo notificar ({r.stderr.strip()[:200]})"


def avisar(novedades: list[dict]) -> str:
    if not novedades:
        return ""
    return notificar("Finianz: licitación del Tesoro", resumen_texto(novedades))


def main(argv: list[str]):
    if argv and argv[0] == "vistas":
        print(f"{marcar_vistas()} novedades marcadas como vistas.")
        return
    if argv and argv[0] == "probar":
        print(notificar("Finianz: prueba", "Si ves esto, las notificaciones de los avisos del Tesoro funcionan."))
        return
    if argv:
        print(__doc__)
        return
    lista = sin_ver()
    if not lista:
        print("No hay novedades sin ver.")
    for n in lista:
        print(f"{n['cuando']} · {n['documento']} del {n['fecha']} · {n['url']}")
        for clave in ("nuevos", "completados", "cortes", "cambios"):
            if n[clave]:
                print(f"   {clave}: {'; '.join(map(str, n[clave]))}")


if __name__ == "__main__":
    main(sys.argv[1:])
