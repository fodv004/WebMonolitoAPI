package mx.eg4.desktop.http;

import com.fasterxml.jackson.databind.JsonNode;

/** Convierte una respuesta de error (status >= 400) de cualquier servicio en ApiException. */
public final class ErrorParser {

    private ErrorParser() {
    }

    public static ApiException parse(String service, int status, String body) {
        if (body != null && !body.isBlank()) {
            try {
                JsonNode n = Json.MAPPER.readTree(body);
                if (n != null && n.isObject()) {
                    ApiException e = fromJson(service, status, n);
                    if (e != null) {
                        return e;
                    }
                }
            } catch (Exception ignored) {
                // No es JSON (XML, HTML de un proxy, texto): mensaje generico abajo.
            }
        }
        return new ApiException(service, status, "HTTP_" + status,
                "El servicio " + service + " respondio HTTP " + status + " sin un mensaje de error reconocible.");
    }

    private static ApiException fromJson(String service, int status, JsonNode n) {
        String code = null;
        String msg = null;
        if (n.hasNonNull("code") && n.hasNonNull("status")) {
            // login: {"status":"error","code","message","errors":[{"field","message"}]}
            code = n.get("code").asText();
            msg = text(n, "message");
            JsonNode errors = n.get("errors");
            if (errors != null && errors.isArray() && !errors.isEmpty()) {
                StringBuilder sb = new StringBuilder(msg == null ? "" : msg);
                for (JsonNode e : errors) {
                    sb.append("\n• ").append(text(e, "field")).append(": ").append(text(e, "message"));
                }
                msg = sb.toString();
            }
        } else if (n.hasNonNull("error")) {
            // books: {"error","mensaje"} | users/authors/pedidos/pagos/tracking: {"error","message"}
            code = n.get("error").asText();
            msg = text(n, "mensaje");
            if (msg == null) {
                msg = text(n, "message");
            }
            if (msg == null) {
                msg = text(n, "detail");
            }
        }
        if (code == null && msg == null) {
            return null;
        }
        return new ApiException(service, status, code, msg != null ? msg : code);
    }

    private static String text(JsonNode n, String field) {
        JsonNode v = n.get(field);
        return v == null || v.isNull() ? null : v.asText();
    }
}
