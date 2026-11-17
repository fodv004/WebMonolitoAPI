package mx.eg4.desktop.service;

import java.io.ByteArrayInputStream;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import javax.xml.XMLConstants;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;

import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.ProgresoSoap;

/**
 * SOAP 1.1 de books (POST <gateway.url>/soap), operacion ObtenerProgresoUsuario.
 * Contrato: apps/services/library_soap_service/wsdl/library-classifier.wsdl.
 * (El soap:address del WSDL apunta a otra IP/puerto; se usa gateway.url del config.)
 */
public final class SoapService {

    static final String NS_SOAP = "http://schemas.xmlsoap.org/soap/envelope/";
    static final String NS_TNS = "http://libraryclassifier/library/soap/classifier";
    static final String ACTION_PROGRESO = NS_TNS + "/ObtenerProgresoUsuario";

    private final ApiClient api;

    SoapService(ApiClient api) {
        this.api = api;
    }

    public ProgresoSoap progresoUsuario(String correo) throws ApiException {
        String envelope = """
                <?xml version="1.0" encoding="UTF-8"?>
                <soap:Envelope xmlns:soap="%s" xmlns:tns="%s">
                  <soap:Header/>
                  <soap:Body>
                    <tns:ObtenerProgresoUsuarioRequest>
                      <tns:correoClasificador>%s</tns:correoClasificador>
                    </tns:ObtenerProgresoUsuarioRequest>
                  </soap:Body>
                </soap:Envelope>
                """.formatted(NS_SOAP, NS_TNS, escape(correo));

        HttpResponse<String> resp = api.raw(Service.BOOKS, "POST", "/soap", envelope, "text/xml; charset=utf-8",
                Map.of("SOAPAction", "\"" + ACTION_PROGRESO + "\""));
        Document doc = parse(resp);

        Element fault = first(doc, NS_SOAP, "Fault");
        if (fault != null) {
            String faultstring = childText(fault, null, "faultstring");
            String codigo = firstText(fault, NS_TNS, "codigo");
            String mensaje = firstText(fault, NS_TNS, "mensaje");
            throw new ApiException("books-soap", resp.statusCode(), codigo != null ? codigo : "SOAP_FAULT",
                    "soap:Fault: " + (mensaje != null ? mensaje : faultstring));
        }
        Element r = first(doc, NS_TNS, "ObtenerProgresoUsuarioResponse");
        if (r == null) {
            throw new ApiException("books-soap", resp.statusCode(), "SOAP_RESPUESTA_INVALIDA",
                    "La respuesta SOAP no trae ObtenerProgresoUsuarioResponse.");
        }
        return new ProgresoSoap(firstText(r, NS_TNS, "correo"),
                parseInt(firstText(r, NS_TNS, "totalClasificados")),
                parseInt(firstText(r, NS_TNS, "totalPendientes")));
    }

    private static Document parse(HttpResponse<String> resp) throws ApiException {
        try {
            DocumentBuilderFactory f = DocumentBuilderFactory.newInstance();
            f.setNamespaceAware(true);
            f.setFeature(XMLConstants.FEATURE_SECURE_PROCESSING, true);
            f.setFeature("http://apache.org/xml/features/disallow-doctype-decl", true);
            DocumentBuilder b = f.newDocumentBuilder();
            return b.parse(new ByteArrayInputStream(resp.body().getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new ApiException("books-soap", resp.statusCode(), "SOAP_RESPUESTA_INVALIDA",
                    "books respondio HTTP " + resp.statusCode() + " sin un sobre SOAP valido.");
        }
    }

    private static Element first(Document doc, String ns, String local) {
        NodeList l = doc.getElementsByTagNameNS(ns, local);
        return l.getLength() == 0 ? null : (Element) l.item(0);
    }

    private static String firstText(Element parent, String ns, String local) {
        NodeList l = parent.getElementsByTagNameNS(ns, local);
        return l.getLength() == 0 ? null : l.item(0).getTextContent().trim();
    }

    /** faultstring/faultcode no llevan namespace. */
    private static String childText(Element parent, String ns, String local) {
        NodeList l = ns == null ? parent.getElementsByTagName(local) : parent.getElementsByTagNameNS(ns, local);
        return l.getLength() == 0 ? null : l.item(0).getTextContent().trim();
    }

    private static int parseInt(String v) {
        try {
            return v == null ? 0 : Integer.parseInt(v.trim());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private static String escape(String s) {
        if (s == null) {
            return "";
        }
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("\"", "&quot;").replace("'", "&apos;");
    }
}
