package mx.eg4.desktop.config;

import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

/** Lee src/main/resources/config.properties (host y puerto de cada servicio). */
public final class AppConfig {

    public enum Service {
        LOGIN("login"), BOOKS("books"), USERS("users"), AUTHORS("authors"),
        PEDIDOS("pedidos"), PAGOS("pagos"), TRACKING("tracking");

        public final String key;

        Service(String key) {
            this.key = key;
        }
    }

    private final Properties props = new Properties();

    public AppConfig() {
        try (InputStream in = AppConfig.class.getResourceAsStream("/config.properties")) {
            if (in == null) {
                throw new IllegalStateException("No se encontro config.properties en resources");
            }
            props.load(new InputStreamReader(in, StandardCharsets.UTF_8));
        } catch (IOException e) {
            throw new IllegalStateException("No se pudo leer config.properties", e);
        }
    }

    public String host() {
        return props.getProperty("host", "localhost").trim();
    }

    public int port(Service s) {
        String v = props.getProperty("port." + s.key);
        if (v == null) {
            throw new IllegalStateException("Falta port." + s.key + " en config.properties");
        }
        return Integer.parseInt(v.trim());
    }

    /** http://host:puerto */
    public String baseUrl(Service s) {
        return "http://" + host() + ":" + port(s);
    }

    /** ws://host:puerto */
    public String wsBaseUrl(Service s) {
        return "ws://" + host() + ":" + port(s);
    }

    public int timeoutSeconds() {
        return Integer.parseInt(props.getProperty("http.timeout.seconds", "20").trim());
    }

    public String mapUserAgent() {
        return props.getProperty("map.user.agent", "EG4-LibraryDesktop/1.0").trim();
    }
}
