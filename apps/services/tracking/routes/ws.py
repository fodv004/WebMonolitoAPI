"""
routes/ws.py
WebSocket /ws (Flask-Sock). Todos los mensajes son JSON.

  /ws?role=gps                     simulador. Header X-Internal-Key obligatorio.
      recibe  {"vehicle_id": "<codigo>", "latitude", "longitude", "speed", "heading"[, "final": true]}
      manda   {"type":"ack","codigo","estado","progreso"[,"detail"]}
              {"type":"error","error":"<CODIGO>","detail":"<texto>"}

  /ws?role=cliente&codigo=<codigo> app del cliente. JWT en "Authorization: Bearer <token>"
      (respaldo: ?token=<token>). Dueño del envio o admin.
      manda   {"type":"snapshot", ...envio completo con ruta y recorrido}
              {"type":"update","codigo","estado","progreso","latitude","longitude","speed","heading","received_at"}

  /ws?role=map                     mapa de admin (JWT de admin): snapshot de los envios en curso y
                                   el update de TODOS los codigos.

Si la autenticacion o el permiso fallan se manda {"type":"error","error":"<CODIGO>","message":"<texto>"}
y se cierra la conexion.
"""
import hmac
import json
import logging
import queue

from flask import request
from flask_sock import ConnectionClosed, Sock

from common.auth import INTERNAL_KEY_HEADER, verificar_token
from common.config import settings
from common.errors import ApiError
from services import difusion, envios_service
from services.envios_service import Actor

log = logging.getLogger(__name__)

sock = Sock()
ESPERA_EVENTOS_S = 1.0


def _enviar(conexion, datos):
    conexion.send(json.dumps(datos, ensure_ascii=False))


def _error(conexion, codigo, mensaje):
    _enviar(conexion, {"type": "error", "error": codigo, "message": mensaje})


def _clave_interna_valida():
    recibida = request.headers.get(INTERNAL_KEY_HEADER, "")
    esperada = settings.INTERNAL_API_KEY
    return bool(esperada and recibida and hmac.compare_digest(recibida.encode(), esperada.encode()))


def _token():
    partes = request.headers.get("Authorization", "").split()
    if len(partes) == 2 and partes[0].lower() == "bearer":
        return partes[1]
    return (request.args.get("token") or "").strip() or None


def _autenticar(conexion):
    """Payload del JWT del handshake, o None (ya se mando el error)."""
    token = _token()
    if token is None:
        _error(conexion, "TOKEN_AUSENTE", "Envia 'Authorization: Bearer <token>' (o ?token=) en el handshake.")
        return None
    try:
        return verificar_token(token)
    except ApiError as e:
        _error(conexion, e.code, e.message)
        return None


@sock.route("/ws")
def ws(conexion):
    rol = request.args.get("role")
    cliente = f"{request.remote_addr}:{request.environ.get('REMOTE_PORT', '?')}"
    try:
        if rol == "gps":
            _atender_gps(conexion, cliente)
        elif rol == "cliente":
            _atender_cliente(conexion, cliente)
        elif rol == "map":
            _atender_mapa(conexion, cliente)
        else:
            _error(conexion, "ROL_INVALIDO", "role debe ser 'gps', 'cliente' o 'map'.")
    except ConnectionClosed:
        pass
    except Exception as e:                       # una conexion rota nunca debe tumbar el servidor
        log.warning("[%s] %s: error en la conexion (%s: %s)", rol, cliente, type(e).__name__, e)


# ------------------------------------------------------------------ simulador
def _atender_gps(conexion, cliente):
    if not _clave_interna_valida():
        log.warning("[gps] %s rechazado: X-Internal-Key invalida o ausente", cliente)
        _enviar(conexion, {"type": "error", "error": "CLAVE_INTERNA_INVALIDA",
                           "detail": "Envia el header X-Internal-Key en el handshake."})
        return
    log.info("[gps] Conectado %s", cliente)
    try:
        while True:
            crudo = conexion.receive()
            try:
                datos = json.loads(crudo)
            except (TypeError, ValueError):
                _enviar(conexion, {"type": "error", "error": "VALIDACION", "detail": "JSON invalido."})
                continue
            try:
                ack = envios_service.registrar_posicion(envios_service.validar_posicion(datos))
            except ApiError as e:
                _enviar(conexion, {"type": "error", "error": e.code, "detail": e.message})
                continue
            except Exception as e:
                log.warning("[gps] %s: no se pudo guardar la posicion (%s: %s)", cliente, type(e).__name__, e)
                _enviar(conexion, {"type": "error", "error": "ERROR_INTERNO",
                                   "detail": "No se pudo guardar la posicion. Reintenta."})
                continue
            _enviar(conexion, ack)
    finally:
        log.info("[gps] Desconectado %s", cliente)


# ------------------------------------------------------------------ cliente y mapa
def _reenviar_eventos(conexion, cola):
    """Manda los eventos de la cola hasta que el cliente cierre la conexion."""
    while True:
        try:
            evento = cola.get(timeout=ESPERA_EVENTOS_S)
        except queue.Empty:
            evento = None
        if evento is not None:
            _enviar(conexion, evento)
        # receive(timeout=0): descarta lo que mande el cliente y lanza ConnectionClosed si ya cerro.
        conexion.receive(timeout=0)


def _atender_cliente(conexion, cliente):
    payload = _autenticar(conexion)
    if payload is None:
        return
    codigo = envios_service.normalizar_codigo(request.args.get("codigo"))
    if not codigo:
        _error(conexion, "VALIDACION", "Falta ?codigo=<codigo de rastreo>.")
        return
    cola = difusion.suscribir(codigo)            # antes del snapshot: no se pierde ningun update
    try:
        try:
            snapshot = envios_service.para_suscriptor(Actor(payload), codigo)
        except ApiError as e:
            _error(conexion, e.code, e.message)
            return
        log.info("[cliente] %s sigue %s (user %s)", cliente, codigo, payload["user_id"])
        _enviar(conexion, {"type": "snapshot", **snapshot})
        _reenviar_eventos(conexion, cola)
    finally:
        difusion.cancelar(codigo, cola)
        log.info("[cliente] %s dejo de seguir %s", cliente, codigo)


def _atender_mapa(conexion, cliente):
    payload = _autenticar(conexion)
    if payload is None:
        return
    if not Actor(payload).es_admin:
        _error(conexion, "ROL_INSUFICIENTE", "El mapa de la flota es solo para administradores.")
        return
    cola = difusion.suscribir(difusion.TODOS)
    try:
        _enviar(conexion, {"type": "snapshot", "envios": envios_service.en_curso()})
        log.info("[map] Conectado %s (admin %s)", cliente, payload["user_id"])
        _reenviar_eventos(conexion, cola)
    finally:
        difusion.cancelar(difusion.TODOS, cola)
        log.info("[map] Desconectado %s", cliente)
