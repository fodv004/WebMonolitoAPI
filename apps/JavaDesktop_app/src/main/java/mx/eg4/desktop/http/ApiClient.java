package mx.eg4.desktop.http;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import java.util.Objects;
import java.util.function.Consumer;

import com.fasterxml.jackson.databind.JsonNode;

import mx.eg4.desktop.config.AppConfig;
import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.session.Session;
import mx.eg4.desktop.util.Log;

/**
 * Cliente HTTP de todos los servicios.
 * - login y books: agrega ?format=json.
 * - Peticiones protegidas: Authorization: Bearer &lt;token&gt;.
 * - 401 TOKEN_EXPIRADO: POST /refresh una vez y repite la peticion.
 * - 401 TOKEN_INVALIDO / TOKEN_REVOCADO / TOKEN_AUSENTE, o refresh fallido: avisa (onSessionLost).
 * Todas las llamadas son bloqueantes: se usan solo desde hilos de fondo.
 */
public final class ApiClient {

    private final AppConfig cfg;
    private final Session session;
    private final HttpClient http;
    private final Object refreshLock = new Object();
    private volatile Consumer<String> onSessionLost = msg -> { };

    public ApiClient(AppConfig cfg, Session session) {
        this.cfg = cfg;
        this.session = session;
        this.http = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(cfg.timeoutSeconds()))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    public AppConfig config() {
        return cfg;
    }

    public Session session() {
        return session;
    }

    public HttpClient httpClient() {
        return http;
    }

    public void setOnSessionLost(Consumer<String> handler) {
        this.onSessionLost = handler;
    }

    // ------------------------------------------------------------------ atajos JSON

    public JsonNode get(Service s, String path, boolean auth) throws ApiException {
        return json(s, send(s, "GET", path, null, null, Map.of(), auth));
    }

    public JsonNode post(Service s, String path, Object body, boolean auth) throws ApiException {
        return post(s, path, body, auth, Map.of());
    }

    public JsonNode post(Service s, String path, Object body, boolean auth, Map<String, String> headers)
            throws ApiException {
        return json(s, send(s, "POST", path, body == null ? null : Json.write(body), "application/json", headers, auth));
    }

    public JsonNode patch(Service s, String path, Object body, boolean auth) throws ApiException {
        return json(s, send(s, "PATCH", path, body == null ? null : Json.write(body), "application/json", Map.of(), auth));
    }

    /** Peticion con cuerpo de texto crudo (SOAP). Devuelve la respuesta sin interpretar el status. */
    public HttpResponse<String> raw(Service s, String method, String path, String body, String contentType,
                                    Map<String, String> headers) throws ApiException {
        return sendOnce(s, method, url(s, path, false), body, contentType, headers, null);
    }

    // ------------------------------------------------------------------ nucleo

    private HttpResponse<String> send(Service s, String method, String path, String body, String contentType,
                                      Map<String, String> headers, boolean auth) throws ApiException {
        String url = url(s, path, true);
        if (!auth) {
            return sendOnce(s, method, url, body, contentType, headers, null);
        }
        String tokenUsado = session.token();
        if (tokenUsado == null) {
            throw new ApiException(s.key, 0, ApiException.SESION_TERMINADA, "No hay una sesion activa.");
        }
        HttpResponse<String> resp = sendOnce(s, method, url, body, contentType, headers, tokenUsado);
        if (resp.statusCode() != 401) {
            return resp;
        }
        ApiException err = ErrorParser.parse(s.key, 401, resp.body());
        if ("TOKEN_EXPIRADO".equals(err.code())) {
            Log.info("401 TOKEN_EXPIRADO en " + s.key + ": se intenta renovar el token");
            if (refresh(tokenUsado)) {
                resp = sendOnce(s, method, url, body, contentType, headers, session.token());
                if (resp.statusCode() != 401) {
                    return resp;
                }
                err = ErrorParser.parse(s.key, 401, resp.body());
            }
            throw sessionLost(s.key, "Tu sesion expiro y no se pudo renovar (" + err.code() + "). Inicia sesion de nuevo.");
        }
        if ("TOKEN_INVALIDO".equals(err.code()) || "TOKEN_REVOCADO".equals(err.code())
                || "TOKEN_AUSENTE".equals(err.code())) {
            throw sessionLost(s.key, err.userMessage() + " (" + err.code() + "). Inicia sesion de nuevo.");
        }
        return resp;   // otro 401 (p. ej. CREDENCIALES_INVALIDAS): lo maneja json()
    }

    /** Para el WebSocket: la sesion ya no es valida (token invalido/revocado o refresh fallido). */
    public void notifySessionLost(String message) {
        Log.warn("Sesion terminada: " + message);
        onSessionLost.accept(message);
    }

    private ApiException sessionLost(String service, String message) {
        Log.warn("Sesion terminada: " + message);
        onSessionLost.accept(message);
        return new ApiException(service, 401, ApiException.SESION_TERMINADA, message);
    }

    /**
     * POST /refresh con el refresh_token. Si otro hilo ya renovo el token (distinto de tokenFallido)
     * no se vuelve a llamar. Devuelve true si hay un token nuevo.
     */
    public boolean refresh(String tokenFallido) {
        synchronized (refreshLock) {
            String actual = session.token();
            if (actual != null && !Objects.equals(actual, tokenFallido)) {
                return true;
            }
            String rt = session.refreshToken();
            if (rt == null) {
                return false;
            }
            try {
                HttpResponse<String> resp = sendOnce(Service.LOGIN, "POST", url(Service.LOGIN, "/refresh", true),
                        Json.write(Map.of("refresh_token", rt)), "application/json", Map.of(), null);
                if (resp.statusCode() != 200) {
                    Log.warn("POST /refresh rechazado: " + ErrorParser.parse("login", resp.statusCode(), resp.body()));
                    return false;
                }
                JsonNode data = Json.MAPPER.readTree(resp.body()).path("data");
                String token = data.path("token").asText(null);
                if (token == null) {
                    return false;
                }
                session.updateTokens(token, data.path("refresh_token").asText(null));
                Log.info("Token renovado: " + Log.mask(token));
                return true;
            } catch (Exception e) {
                Log.warn("POST /refresh fallo: " + e.getMessage());
                return false;
            }
        }
    }

    private HttpResponse<String> sendOnce(Service s, String method, String url, String body, String contentType,
                                          Map<String, String> headers, String token) throws ApiException {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url))
                .timeout(Duration.ofSeconds(cfg.timeoutSeconds()))
                .header("Accept", "application/json");
        if (token != null) {
            b.header("Authorization", "Bearer " + token);
        }
        headers.forEach(b::header);
        if (body != null) {
            b.header("Content-Type", contentType);
            b.method(method, HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8));
        } else {
            b.method(method, HttpRequest.BodyPublishers.noBody());
        }
        long t0 = System.nanoTime();
        try {
            HttpResponse<String> resp = http.send(b.build(), HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
            Log.http(method, url, resp.statusCode(), (System.nanoTime() - t0) / 1_000_000);
            return resp;
        } catch (HttpTimeoutException e) {
            Log.http(method, url, 0, (System.nanoTime() - t0) / 1_000_000);
            throw new ApiException(s.key, 0, ApiException.RED,
                    "El servicio " + s.key + " no respondio a tiempo (" + cfg.host() + ":" + cfg.port(s) + ").");
        } catch (IOException e) {
            Log.http(method, url, 0, (System.nanoTime() - t0) / 1_000_000);
            throw new ApiException(s.key, 0, ApiException.RED,
                    "No se pudo conectar con el servicio " + s.key + " (" + cfg.host() + ":" + cfg.port(s)
                            + "). Revisa tu red o que el servicio este corriendo.");
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new ApiException(s.key, 0, ApiException.RED, "Peticion interrumpida.");
        }
    }

    private JsonNode json(Service s, HttpResponse<String> resp) throws ApiException {
        if (resp.statusCode() >= 400) {
            throw ErrorParser.parse(s.key, resp.statusCode(), resp.body());
        }
        String body = resp.body();
        if (body == null || body.isBlank()) {
            return Json.MAPPER.nullNode();
        }
        try {
            return Json.MAPPER.readTree(body);
        } catch (IOException e) {
            throw new ApiException(s.key, resp.statusCode(), "RESPUESTA_INVALIDA",
                    "El servicio " + s.key + " no respondio JSON.");
        }
    }

    /** URL completa; login y books llevan ?format=json. */
    public String url(Service s, String path, boolean jsonFormat) {
        String url = cfg.baseUrl(s) + path;
        if (jsonFormat && (s == Service.LOGIN || s == Service.BOOKS)) {
            url += (path.contains("?") ? "&" : "?") + "format=json";
        }
        return url;
    }
}
