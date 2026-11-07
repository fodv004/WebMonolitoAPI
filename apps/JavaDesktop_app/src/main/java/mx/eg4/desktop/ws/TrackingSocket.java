package mx.eg4.desktop.ws;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Set;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;

import com.fasterxml.jackson.databind.JsonNode;

import mx.eg4.desktop.config.AppConfig.Service;
import mx.eg4.desktop.http.ApiClient;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Envio;
import mx.eg4.desktop.util.Log;

/**
 * WebSocket de tracking: ws://host:5900/ws?role=cliente&amp;codigo=&lt;codigo&gt;
 * con el header Authorization: Bearer &lt;token&gt; (java.net.http.WebSocket).
 *
 * Mensajes del servidor (apps/services/tracking/routes/ws.py):
 *   {"type":"snapshot", ...envio completo}
 *   {"type":"update","codigo","estado","progreso","latitude","longitude","speed","heading","received_at"}
 *   {"type":"error","error":"&lt;CODIGO&gt;","message":"..."} y cierre.
 *
 * Si la conexion se cae, reintenta con espera creciente (1, 2, 4, 8, 16, 30 s...).
 * Los callbacks del Listener llegan en hilos de fondo: la UI debe usar Platform.runLater.
 */
public final class TrackingSocket implements AutoCloseable {

    public interface Listener {
        void onSnapshot(Envio envio);

        void onUpdate(JsonNode update);

        /** Estado de la conexion para mostrar en pantalla. */
        void onStatus(String texto, boolean conectado);

        /** Error definitivo: ya no se reintenta (envio inexistente, permiso, sesion). */
        void onFatal(String code, String message);
    }

    private static final Set<String> FATALES = Set.of("ENVIO_NO_ENCONTRADO", "ROL_INSUFICIENTE", "VALIDACION",
            "ROL_INVALIDO");
    private static final Set<String> SESION = Set.of("TOKEN_INVALIDO", "TOKEN_REVOCADO", "TOKEN_AUSENTE");
    private static final long[] ESPERAS_S = {1, 2, 4, 8, 16, 30};

    private final ApiClient api;
    private final String codigo;
    private final Listener listener;
    private final ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor(r -> {
        Thread t = new Thread(r, "ws-reconexion");
        t.setDaemon(true);
        return t;
    });

    private volatile WebSocket ws;
    private volatile boolean closed;
    private volatile boolean refreshTried;
    private volatile ScheduledFuture<?> pendingReconnect;
    private int intento;

    public TrackingSocket(ApiClient api, String codigo, Listener listener) {
        this.api = api;
        this.codigo = codigo.trim().toUpperCase();
        this.listener = listener;
    }

    public String codigo() {
        return codigo;
    }

    public void connect() {
        if (closed) {
            return;
        }
        String token = api.session().token();
        if (token == null) {
            listener.onFatal("SESION_TERMINADA", "No hay sesion activa.");
            return;
        }
        String url = api.config().wsBaseUrl(Service.TRACKING) + "/ws?role=cliente&codigo="
                + URLEncoder.encode(codigo, StandardCharsets.UTF_8);
        Log.ws("Conectando " + url + (intento > 0 ? " (reintento " + intento + ")" : ""));
        listener.onStatus(intento > 0 ? "Reconectando (intento " + intento + ")…" : "Conectando…", false);
        long t0 = System.nanoTime();
        api.httpClient().newWebSocketBuilder()
                .connectTimeout(Duration.ofSeconds(api.config().timeoutSeconds()))
                .header("Authorization", "Bearer " + token)
                .buildAsync(URI.create(url), new WsListener())
                .whenComplete((socket, err) -> {
                    if (err != null) {
                        Log.ws("No se pudo abrir el WebSocket (" + (System.nanoTime() - t0) / 1_000_000 + " ms): "
                                + rootMessage(err));
                        scheduleReconnect("No se pudo conectar");
                        return;
                    }
                    if (closed) {
                        socket.sendClose(WebSocket.NORMAL_CLOSURE, "cerrado");
                        return;
                    }
                    Log.ws("Conectado a " + codigo + " (" + (System.nanoTime() - t0) / 1_000_000 + " ms)");
                });
    }

    /** Cierra la conexion y detiene los reintentos. */
    @Override
    public void close() {
        if (closed) {
            return;
        }
        closed = true;
        ScheduledFuture<?> p = pendingReconnect;
        if (p != null) {
            p.cancel(false);
        }
        WebSocket s = ws;
        if (s != null && !s.isOutputClosed()) {
            s.sendClose(WebSocket.NORMAL_CLOSURE, "cliente salio").exceptionally(e -> null);
            Log.ws("Cerrado por el cliente (" + codigo + ")");
        }
        api.session().unregister(this);
        scheduler.shutdownNow();
    }

    public boolean isClosed() {
        return closed;
    }

    private void scheduleReconnect(String motivo) {
        if (closed) {
            return;
        }
        long espera = ESPERAS_S[Math.min(intento, ESPERAS_S.length - 1)];
        intento++;
        Log.ws(motivo + "; reintento en " + espera + " s");
        listener.onStatus(motivo + ". Reintentando en " + espera + " s…", false);
        try {
            pendingReconnect = scheduler.schedule(this::connect, espera, TimeUnit.SECONDS);
        } catch (Exception e) {
            // scheduler cerrado: la pantalla ya se cerro
        }
    }

    private void handleMessage(String text) {
        JsonNode msg;
        try {
            msg = Json.MAPPER.readTree(text);
        } catch (Exception e) {
            Log.ws("Mensaje no JSON ignorado");
            return;
        }
        String type = msg.path("type").asText("");
        switch (type) {
            case "snapshot" -> {
                intento = 0;
                refreshTried = false;
                Envio envio = Json.convert(msg, Envio.class);
                Log.ws("snapshot " + envio.codigo() + " estado=" + envio.estado() + " progreso=" + envio.progreso());
                listener.onStatus("Conectado en tiempo real", true);
                listener.onSnapshot(envio);
            }
            case "update" -> {
                Log.ws("update " + msg.path("codigo").asText() + " estado=" + msg.path("estado").asText()
                        + " progreso=" + msg.path("progreso").asDouble()
                        + " pos=" + msg.path("latitude").asText() + "," + msg.path("longitude").asText());
                listener.onUpdate(msg);
            }
            case "error" -> handleServerError(msg.path("error").asText("ERROR"),
                    msg.path("message").asText(msg.path("detail").asText("")));
            default -> Log.ws("Mensaje de tipo desconocido: " + type);
        }
    }

    private void handleServerError(String code, String message) {
        Log.ws("error del servidor: " + code + " - " + message);
        if ("TOKEN_EXPIRADO".equals(code) && !refreshTried) {
            refreshTried = true;
            String usado = api.session().token();
            if (api.refresh(usado)) {
                listener.onStatus("Token renovado, reconectando…", false);
                reconnectNow();
                return;
            }
        }
        if ("TOKEN_EXPIRADO".equals(code) || SESION.contains(code)) {
            closed = true;
            listener.onFatal("SESION_TERMINADA", message + " (" + code + ")");
            api.notifySessionLost("El rastreo en tiempo real rechazo la sesion: " + message + " (" + code
                    + "). Inicia sesion de nuevo.");
            return;
        }
        if (FATALES.contains(code)) {
            closed = true;
            listener.onFatal(code, message);
            return;
        }
        // Otros errores: el servidor cerrara la conexion; onClose decide el reintento.
        listener.onStatus("Error del servidor: " + code, false);
    }

    private void reconnectNow() {
        WebSocket s = ws;
        ws = null;
        if (s != null) {
            s.abort();
        }
        try {
            scheduler.execute(this::connect);
        } catch (Exception ignored) {
            // cerrado
        }
    }

    private static String rootMessage(Throwable t) {
        while (t.getCause() != null) {
            t = t.getCause();
        }
        return t.getClass().getSimpleName() + (t.getMessage() != null ? ": " + t.getMessage() : "");
    }

    private final class WsListener implements WebSocket.Listener {

        private final StringBuilder buffer = new StringBuilder();

        @Override
        public void onOpen(WebSocket webSocket) {
            ws = webSocket;
            webSocket.request(1);
        }

        @Override
        public CompletionStage<?> onText(WebSocket webSocket, CharSequence data, boolean last) {
            buffer.append(data);
            if (last) {
                String text = buffer.toString();
                buffer.setLength(0);
                try {
                    handleMessage(text);
                } catch (Exception e) {
                    Log.ws("Error procesando mensaje: " + e);
                }
            }
            webSocket.request(1);
            return null;
        }

        @Override
        public CompletionStage<?> onClose(WebSocket webSocket, int statusCode, String reason) {
            Log.ws("Conexion cerrada por el servidor (" + statusCode + (reason.isEmpty() ? "" : " " + reason) + ")");
            if (webSocket == ws) {
                ws = null;
                scheduleReconnect("Conexion cerrada");
            }
            return null;
        }

        @Override
        public void onError(WebSocket webSocket, Throwable error) {
            Log.ws("Error de conexion: " + rootMessage(error));
            if (webSocket == ws) {
                ws = null;
                scheduleReconnect("Se perdio la conexion");
            }
        }
    }
}
