"""
services/envios_service.py
Reglas de negocio de los envios (sin Flask).

Codigo de rastreo: LIB-MTY-<año de creacion>-<pedido_id con 6 digitos>, uno por pedido.

Estados (nunca retroceden):
    CONFIRMADO -> PREPARANDO     por tiempo (SEGUNDOS_CONFIRMADO)
    PREPARANDO -> ENVIADO        por tiempo (SEGUNDOS_PREPARANDO)
    ENVIADO    -> EN_RUTA        primera posicion del simulador
    EN_RUTA    -> ENTREGADO      SOLO con una posicion "final": true que este a menos de
                                 DISTANCIA_ENTREGA_M del ultimo punto de la ruta

Pedidos: al llegar a ENVIADO y a ENTREGADO se avisa por
PATCH /pedidos/internal/<id>/estado (X-Internal-Key). Si pedidos no responde
el envio sigue su curso y la tarea en segundo plano lo reintenta
(columna pedido_estado_sync).
"""
import logging
import math
from datetime import datetime
from math import ceil

from common.auth import ADMIN_ROLE_ID
from common.errors import ApiError
from config import settings as cfg
from db import repository
from db.repository import AHORA
from services import difusion, pedidos_client, rutas

log = logging.getLogger(__name__)

CONFIRMADO, PREPARANDO, ENVIADO, EN_RUTA, ENTREGADO = ESTADOS = (
    "CONFIRMADO", "PREPARANDO", "ENVIADO", "EN_RUTA", "ENTREGADO")
ACTIVOS = (ENVIADO, EN_RUTA)                       # los que reciben posiciones del simulador
CAMPOS_GPS = ("vehicle_id", "latitude", "longitude", "speed", "heading")
PEDIDO_PAGADO = "PAGADO"


class Actor:
    """Quien hace la peticion, segun su JWT."""

    def __init__(self, payload):
        self.user_id = payload["user_id"]
        self.es_admin = payload["role_id"] == ADMIN_ROLE_ID

    def puede_ver(self, envio):
        return self.es_admin or envio["user_id"] == self.user_id


# ------------------------------------------------------------------ salida
def _fecha(valor):
    return valor.isoformat(timespec="seconds") if valor is not None else None


def _fecha_ms(valor):
    return valor.isoformat(timespec="milliseconds") if valor is not None else None


def _posicion(envio):
    if envio["ultima_lat"] is None:
        return None
    return {"latitude": envio["ultima_lat"], "longitude": envio["ultima_lon"], "speed": envio["ultima_velocidad"],
            "heading": envio["ultimo_rumbo"], "received_at": _fecha_ms(envio["ultima_posicion_en"])}


def publico(envio):
    return {
        "codigo": envio["codigo"],
        "pedido_id": envio["pedido_id"],
        "user_id": envio["user_id"],
        "ruta_id": envio["ruta_id"],
        "estado": envio["estado"],
        "progreso": float(envio["progreso"]),
        "posicion": _posicion(envio),
        "pedido_sincronizado": envio["pedido_estado_sync"],
        "created_at": _fecha(envio["created_at"]),
        "updated_at": _fecha(envio["updated_at"]),
        "entregado_en": _fecha(envio["entregado_en"]),
    }


def completo(repo, envio):
    """Envio con su ruta completa y la ruta recorrida (ultimas MAX_POSICIONES posiciones)."""
    datos = publico(envio)
    ruta = rutas.obtener(envio["ruta_id"])
    datos["ruta"] = ruta.a_dict() if ruta else None
    datos["recorrido"] = [{"latitude": p["latitude"], "longitude": p["longitude"], "speed": p["speed"],
                           "heading": p["heading"], "progreso": float(p["progreso"]),
                           "received_at": _fecha_ms(p["received_at"])}
                          for p in repo.posiciones(envio["id"], cfg.MAX_POSICIONES)]
    return datos


def evento_update(envio):
    posicion = _posicion(envio) or {}
    return {"type": "update", "codigo": envio["codigo"], "estado": envio["estado"],
            "progreso": float(envio["progreso"]), "latitude": posicion.get("latitude"),
            "longitude": posicion.get("longitude"), "speed": posicion.get("speed"),
            "heading": posicion.get("heading"), "received_at": posicion.get("received_at")}


# ------------------------------------------------------------------ errores y validacion
def _no_encontrado(codigo):
    return ApiError(404, "ENVIO_NO_ENCONTRADO", f"No existe un envio con codigo {codigo}.")


def _prohibido():
    return ApiError(403, "ROL_INSUFICIENTE", "Solo puedes consultar el rastreo de tus propios pedidos.")


def _invalido(mensaje):
    return ApiError(400, "VALIDACION", mensaje)


def _entero(valor, campo, minimo=1, maximo=None):
    if isinstance(valor, str) and valor.strip().isdigit():
        valor = int(valor.strip())
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo or (maximo and valor > maximo):
        rango = f"entre {minimo} y {maximo}" if maximo else f"mayor o igual a {minimo}"
        raise _invalido(f"'{campo}' debe ser un entero {rango}.")
    return valor


def generar_codigo(pedido_id, anio=None):
    return f"{cfg.CODIGO_PREFIJO}-{anio or datetime.now().year}-{int(pedido_id):06d}"


def normalizar_codigo(codigo):
    return (codigo or "").strip().upper()


def _es_numero(valor):
    return isinstance(valor, (int, float)) and not isinstance(valor, bool) and math.isfinite(valor)


def validar_posicion(datos):
    """Mensaje del simulador: exactamente CAMPOS_GPS y, opcional, "final": true|false."""
    if not isinstance(datos, dict):
        raise _invalido("El mensaje debe ser un objeto JSON.")
    faltan = [c for c in CAMPOS_GPS if c not in datos]
    sobran = sorted(set(datos) - set(CAMPOS_GPS) - {"final"})
    if faltan or sobran:
        raise _invalido(f"Debe traer {list(CAMPOS_GPS)} y opcional 'final' (faltan: {faltan}, sobran: {sobran}).")
    if not isinstance(datos["vehicle_id"], str) or not datos["vehicle_id"].strip():
        raise _invalido("vehicle_id debe ser el codigo de rastreo (texto no vacio).")
    for campo in ("latitude", "longitude", "speed", "heading"):
        if not _es_numero(datos[campo]):
            raise _invalido(f"{campo} debe ser un numero.")
    if not -90 <= datos["latitude"] <= 90:
        raise _invalido("latitude debe estar entre -90 y 90.")
    if not -180 <= datos["longitude"] <= 180:
        raise _invalido("longitude debe estar entre -180 y 180.")
    if datos["speed"] < 0:
        raise _invalido("speed no puede ser negativa.")
    if not 0 <= datos["heading"] <= 360:
        raise _invalido("heading debe estar entre 0 y 360.")
    final = datos.get("final", False)
    if not isinstance(final, bool):
        raise _invalido("final debe ser true o false.")
    return {"codigo": normalizar_codigo(datos["vehicle_id"]), "latitude": float(datos["latitude"]),
            "longitude": float(datos["longitude"]), "speed": float(datos["speed"]),
            "heading": float(datos["heading"]), "final": final}


# ------------------------------------------------------------------ REST
def crear(actor, authorization, datos):
    """POST /envios. Devuelve (envio_completo, creado)."""
    if not isinstance(datos, dict):
        raise _invalido("Envia el cuerpo como un objeto JSON: {\"pedido_id\": 7}.")
    pedido_id = _entero(datos.get("pedido_id"), "pedido_id")

    # pedidos valida que el pedido exista (404) y que sea del usuario o que sea admin (403).
    pedido = pedidos_client.obtener_como_usuario(pedido_id, authorization)

    with repository.unit_of_work() as repo:
        existente = repo.get_by_pedido(pedido_id)
        if existente is not None:
            return completo(repo, existente), False

    if pedido.get("estado") != PEDIDO_PAGADO:
        raise ApiError(409, "PEDIDO_NO_PAGADO",
                       f"El pedido {pedido_id} esta en {pedido.get('estado')}: solo se rastrean pedidos PAGADO.")

    try:
        with repository.unit_of_work() as repo:
            envio = repo.insert(generar_codigo(pedido_id), pedido_id, int(pedido["user_id"]),
                                rutas.para_pedido(pedido_id))
            datos_envio = completo(repo, envio)
    except repository.EnvioDuplicado:
        # Otra peticion lo creo al mismo tiempo: se devuelve ese.
        with repository.unit_of_work() as repo:
            return completo(repo, repo.get_by_pedido(pedido_id)), False
    log.info("Envio %s creado para el pedido %s (ruta %s)", envio["codigo"], pedido_id, envio["ruta_id"])
    difusion.publicar(envio["codigo"], evento_update(envio))
    return datos_envio, True


def listar(actor, args):
    estado = (args.get("estado") or "").strip().upper() or None
    if estado is not None and estado not in ESTADOS:
        raise _invalido(f"'estado' debe ser uno de: {', '.join(ESTADOS)}.")
    page = _entero(args.get("page", 1), "page")
    per_page = _entero(args.get("per_page", 20), "per_page", 1, 100)
    user_id = _entero(args["user_id"], "user_id") if args.get("user_id") else None
    if not actor.es_admin:
        user_id = actor.user_id                                   # un cliente solo ve los suyos
    with repository.unit_of_work() as repo:
        filas, total = repo.list(user_id=user_id, estado=estado, limit=per_page, offset=(page - 1) * per_page)
    return {"items": [publico(fila) for fila in filas], "page": page, "per_page": per_page, "total": total,
            "pages": ceil(total / per_page) if total else 0}


def obtener(actor, codigo):
    codigo = normalizar_codigo(codigo)
    with repository.unit_of_work() as repo:
        envio = repo.get_by_codigo(codigo)
        if envio is None:
            raise _no_encontrado(codigo)
        if not actor.puede_ver(envio):
            raise _prohibido()
        return completo(repo, envio)


def activos():
    """GET /envios/internal/activos: lo que el simulador debe recorrer."""
    with repository.unit_of_work() as repo:
        filas = repo.con_estado(ACTIVOS)
    items = []
    for envio in filas:
        ruta = rutas.obtener(envio["ruta_id"])
        items.append({"codigo": envio["codigo"], "pedido_id": envio["pedido_id"], "ruta_id": envio["ruta_id"],
                      "estado": envio["estado"], "progreso": float(envio["progreso"]), "posicion": _posicion(envio),
                      "ruta": ruta.a_dict() if ruta else None})
    return {"items": items, "total": len(items)}


def en_curso():
    """Envios que no se han entregado (snapshot del mapa de admin)."""
    with repository.unit_of_work() as repo:
        return [publico(envio) for envio in repo.con_estado((CONFIRMADO, PREPARANDO, ENVIADO, EN_RUTA))]


def para_suscriptor(actor, codigo):
    """Snapshot de un envio para el WebSocket de un cliente (mismas reglas que GET /envios/<codigo>)."""
    return obtener(actor, codigo)


# ------------------------------------------------------------------ posiciones (simulador)
def registrar_posicion(posicion):
    """Guarda una posicion validada (validar_posicion). Devuelve el ack para el simulador."""
    codigo = posicion["codigo"]
    with repository.unit_of_work() as repo:
        envio = repo.get_by_codigo(codigo, bloquear=True)
        if envio is None:
            raise _no_encontrado(codigo)
        if envio["estado"] not in ACTIVOS:
            raise ApiError(409, "ENVIO_NO_ACTIVO",
                           f"El envio {codigo} esta en {envio['estado']}: solo recibe posiciones en ENVIADO o EN_RUTA.")
        ruta = rutas.obtener(envio["ruta_id"])
        if ruta is None:
            raise ApiError(500, "RUTA_DESCONOCIDA", f"La ruta {envio['ruta_id']!r} no existe en rutas.json.")

        punto = (posicion["latitude"], posicion["longitude"])
        anterior = float(envio["progreso"])
        recorrido_m = ruta.proyectar(punto, anterior * ruta.distancia_m, cfg.VENTANA_PROYECCION_M)
        progreso = max(anterior, min(0.9999, recorrido_m / ruta.distancia_m))
        cambios = {"estado": EN_RUTA}
        aviso = None
        if posicion["final"]:
            distancia = rutas.distancia_m(punto, ruta.destino)
            if distancia < cfg.DISTANCIA_ENTREGA_M:
                cambios.update(estado=ENTREGADO, entregado_en=AHORA)
                progreso = 1.0
            else:
                aviso = (f"Posicion final a {distancia:.0f} m del destino (maximo {cfg.DISTANCIA_ENTREGA_M} m): "
                         f"el envio sigue {EN_RUTA}.")
        if cambios["estado"] != envio["estado"]:
            cambios["estado_desde"] = AHORA
        progreso = round(progreso, 4)

        guardada = repo.posicion_insert(envio["id"], posicion["latitude"], posicion["longitude"], posicion["speed"],
                                        posicion["heading"], progreso, cfg.MAX_POSICIONES)
        envio = repo.update(envio["id"], progreso=progreso, ultima_lat=posicion["latitude"],
                            ultima_lon=posicion["longitude"], ultima_velocidad=posicion["speed"],
                            ultimo_rumbo=posicion["heading"], ultima_posicion_en=guardada["received_at"], **cambios)

    if envio["estado"] == ENTREGADO:
        log.info("Envio %s ENTREGADO", codigo)
    difusion.publicar(codigo, evento_update(envio))
    ack = {"type": "ack", "codigo": codigo, "estado": envio["estado"], "progreso": float(envio["progreso"])}
    if aviso:
        ack["detail"] = aviso
    return ack


# ------------------------------------------------------------------ tareas por tiempo
def avanzar_por_tiempo():
    """CONFIRMADO -> PREPARANDO -> ENVIADO segun el tiempo en cada estado. Devuelve los codigos que cambiaron."""
    cambiados = []
    for desde, hacia, segundos in ((CONFIRMADO, PREPARANDO, cfg.SEGUNDOS_CONFIRMADO),
                                   (PREPARANDO, ENVIADO, cfg.SEGUNDOS_PREPARANDO)):
        with repository.unit_of_work() as repo:
            actualizados = [repo.update(envio["id"], estado=hacia, estado_desde=AHORA)
                            for envio in repo.vencidos(desde, segundos)]
        for envio in actualizados:
            log.info("Envio %s: %s -> %s", envio["codigo"], desde, hacia)
            difusion.publicar(envio["codigo"], evento_update(envio))
            cambiados.append((envio["codigo"], hacia))
    return cambiados


def _pasos_pendientes(envio):
    """Estados que falta avisar a pedidos, en orden (ENTREGADO exige ENVIADO antes)."""
    pasos = []
    if envio["pedido_estado_sync"] is None:
        pasos.append(ENVIADO)
    if envio["estado"] == ENTREGADO and envio["pedido_estado_sync"] != ENTREGADO:
        pasos.append(ENTREGADO)
    return pasos


def _marcar(envio_id, **campos):
    with repository.unit_of_work() as repo:
        repo.update(envio_id, **campos)


def sincronizar_pendientes():
    """Avisa a pedidos de los envios ENVIADO/EN_RUTA/ENTREGADO que todavia no conoce.
    Nunca lanza por un fallo de pedidos: se reintenta en la siguiente vuelta. Devuelve lo sincronizado."""
    with repository.unit_of_work() as repo:
        pendientes = repo.pendientes_de_sincronizar()
    hechos = []
    for envio in pendientes:
        for paso in _pasos_pendientes(envio):
            try:
                pedidos_client.cambiar_estado(envio["pedido_id"], paso)
            except pedidos_client.PedidosNoDisponible:
                log.warning("No se pudo avisar a pedidos que el pedido %s esta %s (envio %s); se reintentara",
                            envio["pedido_id"], paso, envio["codigo"])
                break
            except pedidos_client.TransicionRechazada:
                try:
                    pedido = pedidos_client.obtener_interno(envio["pedido_id"])
                except pedidos_client.PedidosNoDisponible:
                    log.warning("pedidos rechazo %s para el pedido %s y no se pudo consultar; se reintentara",
                                paso, envio["pedido_id"])
                    break
                estado_pedido = pedido.get("estado") if pedido else None
                if not (estado_pedido == paso or (paso == ENVIADO and estado_pedido == ENTREGADO)):
                    mensaje = f"pedidos rechazo {paso}: el pedido {envio['pedido_id']} esta en {estado_pedido}"
                    log.error("Envio %s: %s; no se reintenta", envio["codigo"], mensaje)
                    _marcar(envio["id"], sync_error=mensaje)
                    break
                # pedidos ya estaba en ese estado: cuenta como sincronizado.
            _marcar(envio["id"], pedido_estado_sync=paso)
            hechos.append((envio["codigo"], paso))
            log.info("Pedido %s marcado %s en pedidos (envio %s)", envio["pedido_id"], paso, envio["codigo"])
    return hechos
