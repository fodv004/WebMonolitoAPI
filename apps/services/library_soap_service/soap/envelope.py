"""
soap/envelope.py
Construcción y parseo manual del SOAP Envelope usando
xml.etree.ElementTree. No se usa Spyne/Zeep ni ningún framework
que genere el XML automáticamente (Parte 6, punto 11 del PDF).
"""
import xml.etree.ElementTree as ET

# ============================================================
# Namespaces usados por el contrato
# ============================================================
NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/"
NS_TNS = "http://libraryclassifier/library/soap/classifier"  # debe coincidir con el WSDL

ET.register_namespace("soap", NS_SOAP)
ET.register_namespace("tns", NS_TNS)


class SoapParseError(Exception):
    """XML mal formado o Envelope/Body ausente -> SOAP Fault de cliente."""
    pass


def parse_envelope(raw_xml_bytes):
    """
    Recibe el body crudo del HTTP POST (bytes) y devuelve una tupla:
    (operation_name, params_dict, header_element_or_None)
    """
    try:
        root = ET.fromstring(raw_xml_bytes)
    except ET.ParseError as e:
        raise SoapParseError(f"XML invalido: {e}")

    if root.tag != f"{{{NS_SOAP}}}Envelope":
        raise SoapParseError("El documento no es un soap:Envelope valido.")

    header_el = root.find(f"{{{NS_SOAP}}}Header")
    body_el = root.find(f"{{{NS_SOAP}}}Body")

    if body_el is None:
        raise SoapParseError("El Envelope no contiene soap:Body.")

    children = list(body_el)
    if not children:
        raise SoapParseError("El soap:Body esta vacio; no hay operacion.")

    operation_el = children[0]
    operation_name = operation_el.tag.split("}")[-1]

    params = {}
    for child in operation_el:
        field_name = child.tag.split("}")[-1]
        params[field_name] = (child.text or "").strip()

    return operation_name, params, header_el


def _add_text_element(parent, tag_name, value):
    """Crea <tns:tag_name>value</tns:tag_name> escapando el valor
    automaticamente (ElementTree escapa texto por defecto, nunca
    se concatena XML a mano)."""
    el = ET.SubElement(parent, f"{{{NS_TNS}}}{tag_name}")
    el.text = "" if value is None else str(value)
    return el


def build_response_envelope(response_element_name, fields_dict):
    """
    Construye un Envelope de RESPUESTA exitosa.
    fields_dict: {nombre_campo: valor}. Si un valor es una lista,
    se generan varios sub-elementos repetidos (ej. conceptoPendiente).
    """
    envelope = ET.Element(f"{{{NS_SOAP}}}Envelope")
    ET.SubElement(envelope, f"{{{NS_SOAP}}}Header")
    body = ET.SubElement(envelope, f"{{{NS_SOAP}}}Body")

    response_el = ET.SubElement(body, f"{{{NS_TNS}}}{response_element_name}")

    for key, value in fields_dict.items():
        if isinstance(value, list):
            for item in value:
                item_el = ET.SubElement(response_el, f"{{{NS_TNS}}}{key}")
                for sub_key, sub_val in item.items():
                    _add_text_element(item_el, sub_key, sub_val)
        else:
            _add_text_element(response_el, key, value)

    return ET.tostring(envelope, encoding="unicode", xml_declaration=False)


def build_fault_envelope(faultcode, faultstring, detail_codigo, detail_mensaje):
    """
    Construye un soap:Fault estandar (Parte 7 del PDF).
    detail_codigo / detail_mensaje: nunca incluir SQL, stack traces
    ni rutas internas aqui.
    """
    envelope = ET.Element(f"{{{NS_SOAP}}}Envelope")
    ET.SubElement(envelope, f"{{{NS_SOAP}}}Header")
    body = ET.SubElement(envelope, f"{{{NS_SOAP}}}Body")

    fault_el = ET.SubElement(body, f"{{{NS_SOAP}}}Fault")
    ET.SubElement(fault_el, "faultcode").text = faultcode
    ET.SubElement(fault_el, "faultstring").text = faultstring

    detail_el = ET.SubElement(fault_el, "detail")
    classifier_fault = ET.SubElement(detail_el, f"{{{NS_TNS}}}ClassifierFaultDetail")
    _add_text_element(classifier_fault, "codigo", detail_codigo)
    _add_text_element(classifier_fault, "mensaje", detail_mensaje)

    return ET.tostring(envelope, encoding="unicode", xml_declaration=False)