package mx.eg4.desktop.config;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

/**
 * Lee src/main/resources/config.properties.
 *
 * Todas las peticiones salen por el API Gateway (nginx) con UNA sola URL base:
 *   gateway.url=http://IP_EXTERNA:8080/catalogo/api
 * El gateway enruta por prefijo (/login, /books, /users, /authors, /pedidos,
 * /pagos, /envios, /ws...) al microservicio que corresponde.
 *
 * La URL se puede sobrescribir sin recompilar (en este orden de prioridad):
 *   1. propiedad del sistema  -Dgateway.url=...
 *   2. variable de entorno    EG4_GATEWAY_URL=...
 *   3. gateway.url de config.properties
 */
public final class AppConfig {

    /** Microservicio destino (solo para mensajes y para saber que respuestas llevan ?format=json). */
    public enum Service {
        LOGIN("login"), BOOKS("books"), USERS("users"), AUTHORS("authors"),
        PEDIDOS("pedidos"), PAGOS("pagos"), TRACKING("tracking");

        public final String key;

        Service(String key) {
            this.key = key;
        }
    }

    public static final String ENV_GATEWAY_URL = "EG4_GATEWAY_URL";
    public static final String PROP_GATEWAY_URL = "gateway.url";

    private final Properties props = new Properties();
    private final String gatewayUrl;

    public AppConfig() {
        try (InputStream in = AppConfig.class.getResourceAsStream("/config.properties")) {
            if (in == null) {
                throw new IllegalStateException("No se encontro config.properties en resources");
            }
            props.load(new InputStreamReader(in, StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new IllegalStateException("No se pudo leer config.properties", e);
        }
        gatewayUrl = resolverGatewayUrl();
    }

    private String resolverGatewayUrl() {
        String v = System.getProperty(PROP_GATEWAY_URL);
        if (v == null || v.isBlank()) {
            v = System.getenv(ENV_GATEWAY_URL);
        }
        if (v == null || v.isBlank()) {
            v = props.getProperty(PROP_GATEWAY_URL);
        }
        if (v == null || v.isBlank()) {
            throw new IllegalStateException("Falta " + PROP_GATEWAY_URL + " en config.properties");
        }
        v = v.trim().replaceAll("/+$", "");
        if (!v.startsWith("http://") && !v.startsWith("https://")) {
            throw new IllegalStateException(PROP_GATEWAY_URL + " debe empezar con http:// o https://: " + v);
        }
        return v;
    }

    /** URL base del gateway, p. ej. http://IP_EXTERNA:8080/catalogo/api (sin "/" final). */
    public String gatewayUrl() {
        return gatewayUrl;
    }

    /** host:puerto del gateway (para mostrar en pantalla y en el log). */
    public String host() {
        URI uri = URI.create(gatewayUrl);
        return uri.getPort() > 0 ? uri.getHost() + ":" + uri.getPort() : uri.getHost();
    }

    /** URL base HTTP de cualquier servicio: siempre la del gateway. */
    public String baseUrl(Service s) {
        return gatewayUrl;
    }

    /** URL base WebSocket: la del gateway con ws:// (o wss:// si el gateway es https). */
    public String wsBaseUrl(Service s) {
        return gatewayUrl.startsWith("https://")
                ? "wss://" + gatewayUrl.substring("https://".length())
                : "ws://" + gatewayUrl.substring("http://".length());
    }

    public int timeoutSeconds() {
        return Integer.parseInt(props.getProperty("http.timeout.seconds", "20").trim());
    }

    public String mapUserAgent() {
        return props.getProperty("map.user.agent", "EG4-LibraryDesktop/1.0").trim();
    }
}
