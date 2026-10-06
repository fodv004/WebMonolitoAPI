"""
app.py
Entrypoint del modulo SOAP (Flask). Expone un unico endpoint /soap
que recibe HTTP POST con un SOAP Envelope XML, identifica la
operacion solicitada y delega a soap/service.py (Paso 12: ya
conectado a PostgreSQL de verdad, no placeholder).

La capa REST (api/rest.py, servicio "books") usa el modulo compartido
apps/services/common: JWT + rol admin en las escrituras, cache en Redis,
/health, /metrics, log HTTP con filtro y CORS. El endpoint /soap no cambia.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, Response

load_dotenv(Path(__file__).with_name(".env"))
# apps/services en el path: ahi vive el modulo compartido `common`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.cors import init_cors  # noqa: E402
from common.health import init_health  # noqa: E402
from common.logging_utils import init_logging  # noqa: E402
from common.metrics import init_metrics  # noqa: E402
from db.connection import get_connection  # noqa: E402

from soap.envelope import (
    parse_envelope,
    build_response_envelope,
    build_fault_envelope,
    SoapParseError,
)
from soap import service
from soap import service, faults, security
from api.rest import rest_bp

SERVICE_NAME = "books"
VERSION = "2.0.0"


def _db_ok():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()
    return True


app = Flask(__name__)
init_logging(app)
init_cors(app)
init_metrics(app, SERVICE_NAME)
init_health(app, SERVICE_NAME, _db_ok, VERSION)
app.register_blueprint(rest_bp)


@app.route("/soap", methods=["POST"])
def soap_endpoint():
    raw_body = request.get_data()

    try:
        operation_name, params, header_el = parse_envelope(raw_body)
    except SoapParseError as e:
        fault_xml = build_fault_envelope(
            faultcode="soap:Client",
            faultstring="Solicitud SOAP invalida.",
            detail_codigo="XML_INVALIDO",
            detail_mensaje=str(e),
        )
        return Response(fault_xml, status=400, mimetype="text/xml")

    try:
        if operation_name == "ObtenerConceptosPendientesRequest":
            pendientes = service.obtener_conceptos_pendientes(
                params["correoClasificador"]
            )
            response_xml = build_response_envelope(
                "ObtenerConceptosPendientesResponse",
                {"conceptoPendiente": pendientes},
            )
            return Response(response_xml, status=200, mimetype="text/xml")

        elif operation_name == "RegistrarClasificacionRequest":
            resultado = service.registrar_clasificacion(
                nombre=params["nombre"],
                apellidos=params["apellidos"],
                correo=params["correo"],
                isbn=params["isbn"],
                id_concepto=int(params["idConcepto"]),
                modelo_cloud=params["modeloCloud"],
                tipo_cliente=params["tipoCliente"],
                identificador_cliente=params["identificadorCliente"],
            )
            response_xml = build_response_envelope(
                "RegistrarClasificacionResponse", resultado
            )
            return Response(response_xml, status=200, mimetype="text/xml")

        elif operation_name == "ObtenerProgresoUsuarioRequest":
            progreso = service.obtener_progreso_usuario(
                params["correoClasificador"]
            )
            response_xml = build_response_envelope(
                "ObtenerProgresoUsuarioResponse", progreso
            )
            return Response(response_xml, status=200, mimetype="text/xml")

        elif operation_name == "ObtenerEstadisticasPorModeloRequest":
            # Operacion protegida con WS-Security (Tarea 1): valida el
            # UsernameToken del Header antes de ejecutar cualquier logica.
            security.validar_ws_security(header_el)
            estadisticas = service.obtener_estadisticas_por_modelo()
            response_xml = build_response_envelope(
                "ObtenerEstadisticasPorModeloResponse", estadisticas
            )
            return Response(response_xml, status=200, mimetype="text/xml")

        else:
            fault_xml = build_fault_envelope(
                faultcode="soap:Client",
                faultstring="Operacion no reconocida.",
                detail_codigo="OPERACION_DESCONOCIDA",
                detail_mensaje=f"'{operation_name}' no esta definida en el contrato.",
            )
            return Response(fault_xml, status=400, mimetype="text/xml")

    except service.ConceptoInexistente as e:
        fault_xml = build_fault_envelope("soap:Client", "Concepto inexistente.", "CONCEPTO_INEXISTENTE", str(e))
        return Response(fault_xml, status=400, mimetype="text/xml")

    except service.ModeloInvalido as e:
        fault_xml = build_fault_envelope("soap:Client", "Modelo Cloud invalido.", "MODELO_INVALIDO", str(e))
        return Response(fault_xml, status=400, mimetype="text/xml")

    except service.ClasificacionDuplicada as e:
        fault_xml = build_fault_envelope("soap:Client", "Clasificacion duplicada.", "DUPLICADO_409", str(e))
        return Response(fault_xml, status=409, mimetype="text/xml")

    except faults.AutenticacionInvalida as e:
        fault_xml, status = faults.build_business_fault(e)
        return Response(fault_xml, status=status, mimetype="text/xml")

    except Exception as e:
        fault_xml = build_fault_envelope(
            faultcode="soap:Server",
            faultstring="Error interno del servidor.",
            detail_codigo="ERROR_INTERNO",
            detail_mensaje="Ocurrio un error inesperado. Contacte al administrador.",
        )
        app.logger.error(f"Error interno en operacion {operation_name}: {e}")
        return Response(fault_xml, status=500, mimetype="text/xml")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("FLASK_PORT", 5001)), debug=True)