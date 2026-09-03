"""
cliente_zeep.py
Cliente de interoperabilidad (Tarea 4 del trabajo en casa).

A diferencia de soap/envelope.py (servidor, Python) y SoapClient.java
(cliente de escritorio, Java) -- ambos construyen el SOAP Envelope
MANUALMENTE -- este cliente usa zeep, que genera automaticamente las
llamadas SOAP a partir del contrato WSDL, sin que el desarrollador
escriba ni un solo tag XML a mano.

Instalacion (una sola vez):
    pip install zeep

Uso:
    python cliente_zeep.py
"""
from zeep import Client
from zeep.exceptions import Fault

WSDL_PATH = "wsdl/library-classifier.wsdl"

CORREO = "fernando.olivaresd@udem.edu"


def main():
    client = Client(WSDL_PATH)

    print("=" * 60)
    print("1) ObtenerConceptosPendientes")
    print("=" * 60)
    try:
        pendientes = client.service.ObtenerConceptosPendientes(
            correoClasificador=CORREO
        )
        if not pendientes.conceptoPendiente:
            print("No hay conceptos pendientes para este correo.")
        else:
            for c in pendientes.conceptoPendiente:
                print(f"- [{c.isbn}] {c.tituloLibro} -- {c.nombreConcepto} "
                      f"(id {c.idConcepto}): {c.definicion}")
    except Fault as f:
        print("SOAP Fault:", f.message)

    print()
    print("=" * 60)
    print("2) RegistrarClasificacion")
    print("=" * 60)
    try:
        resultado = client.service.RegistrarClasificacion(
            nombre="Fernando",
            apellidos="Olivares",
            correo=CORREO,
            isbn="9780000000027",
            idConcepto=19,
            modeloCloud="PaaS",
            tipoCliente="zeep-python-interop",
            identificadorCliente="cliente-zeep-tarea4",
        )
        print("Registrado. idClasificacion:", resultado.idClasificacion)
        print("Fecha:", resultado.fechaClasificacion)
        print("Mensaje:", resultado.mensaje)
    except Fault as f:
        print("SOAP Fault:", f.message)
        if f.detail is not None:
            print("Detalle:", f.detail)


if __name__ == "__main__":
    main()