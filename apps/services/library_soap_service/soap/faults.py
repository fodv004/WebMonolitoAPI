"""
soap/faults.py
Catalogo centralizado de errores del servicio y su traduccion a
SOAP Fault (Parte 7 del PDF). Ningun Fault enviado al cliente
incluye SQL, stack traces, rutas internas ni credenciales -- eso
solo se registra en el log del servidor.
"""
from soap.envelope import build_fault_envelope


class ConceptoInexistente(Exception):
    pass


class ModeloInvalido(Exception):
    pass


class ClasificacionDuplicada(Exception):
    pass


_CASOS = {
    ConceptoInexistente: (400, "soap:Client", "Concepto inexistente.", "CONCEPTO_INEXISTENTE"),
    ModeloInvalido: (400, "soap:Client", "Modelo Cloud invalido.", "MODELO_INVALIDO"),
    ClasificacionDuplicada: (409, "soap:Client", "Clasificacion duplicada.", "DUPLICADO_409"),
}


def build_business_fault(exc):
    tipo = type(exc)
    if tipo not in _CASOS:
        return build_server_fault(exc, logger=None)

    http_status, faultcode, faultstring, codigo = _CASOS[tipo]
    xml = build_fault_envelope(
        faultcode=faultcode,
        faultstring=faultstring,
        detail_codigo=codigo,
        detail_mensaje=str(exc),
    )
    return xml, http_status


def build_client_fault_xml_invalido(mensaje_tecnico):
    xml = build_fault_envelope(
        faultcode="soap:Client",
        faultstring="Solicitud SOAP invalida.",
        detail_codigo="XML_INVALIDO",
        detail_mensaje=mensaje_tecnico,
    )
    return xml, 400


def build_client_fault_operacion_desconocida(operation_name):
    xml = build_fault_envelope(
        faultcode="soap:Client",
        faultstring="Operacion no reconocida.",
        detail_codigo="OPERACION_DESCONOCIDA",
        detail_mensaje=f"'{operation_name}' no esta definida en el contrato.",
    )
    return xml, 400


def build_server_fault(exc, logger=None):
    if logger is not None:
        logger.error(f"Error interno no controlado: {exc}")

    xml = build_fault_envelope(
        faultcode="soap:Server",
        faultstring="Error interno del servidor.",
        detail_codigo="ERROR_INTERNO",
        detail_mensaje="Ocurrio un error inesperado. Contacte al administrador.",
    )
    return xml, 500