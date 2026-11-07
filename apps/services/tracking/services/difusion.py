"""
services/difusion.py
Reparto en memoria de los eventos de rastreo a los WebSocket abiertos.

Cada conexion se suscribe a un codigo (cliente) o a TODOS (mapa de admin)
y recibe los eventos en su propia cola. Vive en la memoria del proceso:
por eso tracking corre con gunicorn --workers 1 y varios hilos.
"""
import queue
import threading

TODOS = "*"
MAX_PENDIENTES = 200        # una conexion lenta pierde los eventos mas viejos, nunca bloquea al resto

_lock = threading.Lock()
_suscriptores = {}          # codigo | TODOS -> set(Queue)


def suscribir(codigo):
    cola = queue.Queue(maxsize=MAX_PENDIENTES)
    with _lock:
        _suscriptores.setdefault(codigo, set()).add(cola)
    return cola


def cancelar(codigo, cola):
    with _lock:
        colas = _suscriptores.get(codigo)
        if colas is not None:
            colas.discard(cola)
            if not colas:
                del _suscriptores[codigo]


def publicar(codigo, evento):
    """Entrega `evento` a las conexiones de ese codigo y a las de TODOS."""
    with _lock:
        colas = list(_suscriptores.get(codigo, ())) + list(_suscriptores.get(TODOS, ()))
    for cola in colas:
        try:
            cola.put_nowait(evento)
        except queue.Full:
            try:
                cola.get_nowait()
                cola.put_nowait(evento)
            except (queue.Empty, queue.Full):
                pass


def conexiones():
    with _lock:
        return sum(len(c) for c in _suscriptores.values())
