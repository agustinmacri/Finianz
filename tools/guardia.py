"""Guardia de seguridad para el código que escribe el agente (herramienta ejecutar_python).

No se importa: python_exec.py copia este archivo al principio del código que ejecuta,
después de importar las conexiones de datos y antes del código del modelo. A partir de
ese momento, Python consulta a la guardia antes de cada acción sensible (audit hooks,
https://docs.python.org/3/library/audit_events.html) y la guardia no se puede desactivar.

Qué bloquea:
- Leer archivos del proyecto que no sean código: el .env, las bases de datos/, los calendarios.
- Leer archivos fuera del proyecto, salvo los de la instalación de Python y la carpeta temporal.
- Escribir, borrar o renombrar archivos, salvo en la caché de las APIs y la carpeta temporal.
- Lanzar otros programas (subprocess, os.system...) y usar ctypes.
- Conectarse a sitios que no sean las APIs de datos del proyecto. Si tu red usa un proxy, las
  conexiones a través de él quedan bloqueadas (habría que agregarlo a mano).

Límite conocido (lo aclara la documentación de Python): no es un aislamiento total y
alguien decidido podría saltearla. Protege contra errores del modelo y contra
instrucciones maliciosas que pudieran llegar en los datos. La protección fuerte es
CONFIRMAR_CODIGO=true (ver el código antes de ejecutarlo) o un contenedor aislado.
"""


def activar(proyecto: str, cache: str, sitios: list[str]):
    import os
    import site
    import socket
    import sys
    import tempfile

    def normalizar(ruta) -> str:
        if isinstance(ruta, bytes):
            ruta = ruta.decode(errors="ignore")
        return os.path.normcase(os.path.realpath(os.path.abspath(ruta)))

    def dentro(ruta: str, carpeta: str) -> bool:
        return ruta == carpeta or ruta.startswith(carpeta.rstrip(os.sep) + os.sep)

    proyecto, cache, temporal = normalizar(proyecto), normalizar(cache), normalizar(tempfile.gettempdir())
    python = {normalizar(p) for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, *site.getsitepackages(),
                                      site.getusersitepackages()) if p}
    sitios_ok = {s.lower() for s in sitios if s}
    ips_ok: set[str] = set()
    PROCESOS = ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.startfile",
                "os.fork", "os.forkpty", "pty.spawn", "_winapi.CreateProcess")
    MODIFICAR = ("os.remove", "os.rename", "os.rmdir", "os.truncate", "os.chmod", "os.chown", "os.link",
                 "os.symlink", "shutil.rmtree", "shutil.move", "os.mkdir")

    # El orden importa: el proyecto se revisa antes que la carpeta temporal por si una está dentro de la otra
    def puede_leer(ruta: str) -> bool:
        if dentro(ruta, cache) or any(dentro(ruta, p) for p in python):    # el entorno virtual puede estar en el proyecto
            return True
        if dentro(ruta, proyecto):
            return ruta.endswith((".py", ".pyc")) and not os.path.basename(ruta).startswith(".env")
        return dentro(ruta, temporal)

    def puede_escribir(ruta: str) -> bool:
        if dentro(ruta, cache):
            return True
        return not dentro(ruta, proyecto) and dentro(ruta, temporal)

    def bloquear(motivo: str):
        # PermissionError: Python ignora en silencio, por ejemplo, no poder guardar un .pyc
        raise PermissionError(f"Bloqueado por seguridad: {motivo}")

    def guardia(evento: str, args):
        if evento == "open":
            ruta, modo = args[0], args[1] if len(args) > 1 else "r"
            if isinstance(ruta, int):
                return
            ruta = normalizar(ruta)
            escribe = isinstance(modo, str) and any(c in modo for c in "wax+")
            if escribe and not puede_escribir(ruta):
                bloquear(f"no se permite escribir {ruta}")
            if not escribe and not puede_leer(ruta):
                bloquear(f"no se permite leer {ruta}")
        elif evento in MODIFICAR:
            if not all(puede_escribir(normalizar(a)) for a in args[:2] if isinstance(a, (str, bytes, os.PathLike))):
                bloquear(f"no se permite modificar archivos ({evento})")
        elif evento.startswith(PROCESOS):
            bloquear("no se permite lanzar otros programas")
        elif evento.startswith("ctypes."):
            bloquear("no se permite usar ctypes")
        elif evento == "sqlite3.connect":
            bloquear("no se permite abrir bases de datos")
        elif evento == "socket.getaddrinfo":
            if str(args[0]).lower() not in sitios_ok:
                bloquear(f"no se permite conectarse a {args[0]}")
        elif evento == "socket.connect":
            direccion = args[1]
            if not (isinstance(direccion, tuple) and direccion[0] in ips_ok):
                bloquear(f"no se permite conectarse a {direccion}")

    # Las conexiones solo pueden ir a direcciones obtenidas al resolver un sitio permitido
    resolver = socket.getaddrinfo

    def getaddrinfo(*args, **kwargs):
        resultado = resolver(*args, **kwargs)
        ips_ok.update(r[4][0] for r in resultado)
        return resultado

    socket.getaddrinfo = getaddrinfo
    sys.addaudithook(guardia)
