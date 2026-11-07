package mx.eg4.desktop.ui;

import java.util.List;
import java.util.Locale;

import com.fasterxml.jackson.databind.JsonNode;

import javafx.application.Platform;
import javafx.concurrent.Worker;
import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Button;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressBar;
import javafx.scene.control.ScrollPane;
import javafx.scene.control.SplitPane;
import javafx.scene.control.TextField;
import javafx.scene.layout.BorderPane;
import javafx.scene.layout.GridPane;
import javafx.scene.layout.HBox;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.VBox;
import javafx.scene.shape.Circle;

import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.model.Envio;
import mx.eg4.desktop.model.Posicion;
import mx.eg4.desktop.ui.util.Alerts;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.ui.util.LoadingPane;
import mx.eg4.desktop.ws.TrackingSocket;

/**
 * Rastreo: GET /envios/&lt;codigo&gt; para la informacion inicial y luego el WebSocket
 * ws://host:5900/ws?role=cliente&amp;codigo=... para el snapshot y los updates.
 */
public final class TrackingView implements View {

    /** Estados del servicio tracking (envios_service.py) con su etiqueta para el cliente. */
    private static final List<String[]> ESTADOS = List.of(
            new String[]{"CONFIRMADO", "Pedido confirmado"},
            new String[]{"PREPARANDO", "Preparando pedido"},
            new String[]{"ENVIADO", "Pedido enviado"},
            new String[]{"EN_RUTA", "En ruta de entrega"},
            new String[]{"ENTREGADO", "Entregado"});

    private final Ctx ctx;
    private final BorderPane root = new BorderPane();
    private final TextField codeField = new TextField();
    private final Label connection = new Label("Sin conexion");
    private final MapView map;
    private final LoadingPane loading;
    private final Label banner = new Label();

    private final Label vCodigo = value();
    private final Label vPedido = value();
    private final Label vEstado = value();
    private final VBox timeline = new VBox(0);
    private final ProgressBar progress = new ProgressBar(0);
    private final Label vProgress = value();
    private final Label vCoords = value();
    private final Label vSpeed = value();
    private final Label vUpdated = value();
    private final Label vRuta = value();

    private TrackingSocket socket;
    private String currentCode;
    private String currentEstado;
    private boolean entregadoAvisado;
    private String pendingOnShow;
    private boolean visible;

    public TrackingView(Ctx ctx) {
        this.ctx = ctx;
        map = new MapView(ctx.config.mapUserAgent());

        Label title = new Label("Rastrear pedido");
        title.getStyleClass().add("view-title");
        codeField.setPromptText("Codigo de rastreo, p. ej. LIB-MTY-2026-000007");
        codeField.setId("tracking-code");
        progress.setId("tracking-progress");
        vEstado.setId("tracking-estado");
        banner.setId("tracking-banner");
        connection.setId("tracking-conn");
        codeField.setPrefWidth(320);
        codeField.setOnAction(e -> consultFromField());
        Button go = new Button("Consultar");
        go.setId("tracking-consult");
        go.getStyleClass().add("primary");
        go.setOnAction(e -> consultFromField());
        connection.getStyleClass().addAll("conn", "conn-off");
        Region sp = new Region();
        HBox.setHgrow(sp, Priority.ALWAYS);
        HBox header = new HBox(12, title, sp, connection, codeField, go);
        header.setAlignment(Pos.CENTER_LEFT);
        header.getStyleClass().add("view-header");

        banner.getStyleClass().add("banner");
        banner.setWrapText(true);
        banner.setMaxWidth(Double.MAX_VALUE);
        setBanner(null, null);

        // El WebView va en el centro de un BorderPane: crece con todo el espacio junto al panel lateral.
        BorderPane mapBox = new BorderPane(map.node());
        mapBox.setMinSize(0, 0);
        mapBox.getStyleClass().add("map-box");
        map.node().widthProperty().addListener((o, a, b) -> map.refrescarTamano());
        map.node().heightProperty().addListener((o, a, b) -> map.refrescarTamano());
        map.engine().getLoadWorker().stateProperty().addListener((o, a, st) -> {
            if (st == Worker.State.SUCCEEDED) {
                map.refrescarTamano();
            }
        });
        SplitPane split = new SplitPane(mapBox, sidePanel());
        split.setDividerPositions(0.7);
        SplitPane.setResizableWithParent(split.getItems().get(1), false);
        loading = new LoadingPane(split);

        VBox center = new VBox(10, banner, loading);
        VBox.setVgrow(loading, Priority.ALWAYS);
        loading.setMaxSize(Double.MAX_VALUE, Double.MAX_VALUE);
        split.setMaxSize(Double.MAX_VALUE, Double.MAX_VALUE);
        root.getStyleClass().add("view");
        root.setTop(header);
        root.setCenter(center);
        clearPanel();
    }

    private Node sidePanel() {
        GridPane g = new GridPane();
        g.setHgap(12);
        g.setVgap(8);
        int r = 0;
        g.addRow(r++, key("Codigo"), vCodigo);
        g.addRow(r++, key("Pedido"), vPedido);
        g.addRow(r++, key("Estado actual"), vEstado);
        g.addRow(r++, key("Ruta"), vRuta);

        progress.setMaxWidth(Double.MAX_VALUE);
        HBox progRow = new HBox(10, progress, vProgress);
        progRow.setAlignment(Pos.CENTER_LEFT);
        HBox.setHgrow(progress, Priority.ALWAYS);

        GridPane live = new GridPane();
        live.setHgap(12);
        live.setVgap(8);
        live.addRow(0, key("Coordenadas"), vCoords);
        live.addRow(1, key("Velocidad"), vSpeed);
        live.addRow(2, key("Ultima actualizacion"), vUpdated);

        VBox side = new VBox(14, section("Envio"), g, section("Progreso"), progRow, section("Linea de tiempo"),
                timeline, section("Ultima posicion"), live);
        side.getStyleClass().add("tracking-side");
        ScrollPane sc = new ScrollPane(side);
        sc.setFitToWidth(true);
        sc.setMinWidth(300);
        sc.getStyleClass().add("plain-scroll");
        return sc;
    }

    // ------------------------------------------------------------------ ciclo de vida

    /** Desde Mis compras / compra: consultar este codigo al entrar. */
    public void consultOnShow(String codigo) {
        pendingOnShow = codigo;
    }

    @Override
    public void onShow() {
        visible = true;
        map.refrescarTamano();
        if (pendingOnShow != null) {
            String c = pendingOnShow;
            pendingOnShow = null;
            consult(c);
        } else if (currentCode != null && !"ENTREGADO".equals(currentEstado)) {
            consult(currentCode);      // se cerro al salir: se vuelve a conectar
        }
    }

    @Override
    public void onHide() {
        visible = false;
        closeSocket();
    }

    public void close() {
        visible = false;
        closeSocket();
    }

    private void closeSocket() {
        if (socket != null) {
            socket.close();
            socket = null;
        }
        setConnection("Sin conexion", false);
    }

    // ------------------------------------------------------------------ consulta

    private void consultFromField() {
        String c = codeField.getText() == null ? "" : codeField.getText().trim();
        if (c.isEmpty()) {
            setBanner("Escribe un codigo de rastreo.", "banner-warn");
            return;
        }
        consult(c);
    }

    public void consult(String codigo) {
        String code = codigo.trim().toUpperCase(Locale.ROOT);
        closeSocket();
        codeField.setText(code);
        currentCode = code;
        currentEstado = null;
        entregadoAvisado = false;
        setBanner(null, null);
        clearPanel();
        map.reset();
        loading.run("Consultando " + code + "…", () -> ctx.services.envios.obtener(code), envio -> {
            if (!code.equals(currentCode)) {
                return;                 // el usuario ya pidio otro codigo
            }
            applyEnvio(envio);
            if ("ENTREGADO".equals(envio.estado())) {
                entregadoAvisado = true;
                setBanner("Este pedido ya fue entregado" + (envio.entregadoEn() != null ? " el "
                        + Fmt.date(envio.entregadoEn()) : "") + ".", "banner-ok");
                return;                 // ya no habra updates
            }
            if (visible) {
                openSocket(code);
            }
        }, err -> {
            if (!code.equals(currentCode)) {
                return;
            }
            currentCode = null;
            ApiException api = Alerts.unwrap(err);
            if (api != null && api.isSessionEnded()) {
                return;
            }
            setBanner(friendly(api, code, Alerts.message(err)), "banner-error");
        });
    }

    private static String friendly(ApiException api, String code, String fallback) {
        if (api == null) {
            return fallback;
        }
        if ("ENVIO_NO_ENCONTRADO".equals(api.code()) || api.status() == 404) {
            return "No existe un envio con el codigo " + code + ". Revisa que este bien escrito.";
        }
        if (api.status() == 403 || "ROL_INSUFICIENTE".equals(api.code())) {
            return "El codigo " + code + " pertenece a un pedido de otra cuenta: solo puedes rastrear tus propios "
                    + "pedidos. (" + api.userMessage() + ")";
        }
        return api.userMessage() + " (" + api.code() + ")";
    }

    private void openSocket(String code) {
        TrackingSocket s = new TrackingSocket(ctx.services.api, code, new TrackingSocket.Listener() {
            @Override
            public void onSnapshot(Envio envio) {
                Platform.runLater(() -> {
                    if (code.equals(currentCode)) {
                        applyEnvio(envio);
                        checkDelivered(envio.estado());
                    }
                });
            }

            @Override
            public void onUpdate(JsonNode u) {
                Platform.runLater(() -> {
                    if (code.equals(currentCode)) {
                        applyUpdate(u);
                    }
                });
            }

            @Override
            public void onStatus(String texto, boolean conectado) {
                Platform.runLater(() -> {
                    if (code.equals(currentCode)) {
                        setConnection(texto, conectado);
                    }
                });
            }

            @Override
            public void onFatal(String errCode, String message) {
                Platform.runLater(() -> {
                    if (!code.equals(currentCode)) {
                        return;
                    }
                    setConnection("Desconectado", false);
                    if ("SESION_TERMINADA".equals(errCode)) {
                        setBanner("La sesion ya no es valida para el rastreo en tiempo real: " + message,
                                "banner-error");
                    } else {
                        setBanner(friendly(new ApiException("tracking", 0, errCode, message), code, message),
                                "banner-error");
                    }
                });
            }
        });
        socket = s;
        ctx.session.register(s);
        s.connect();
    }

    // ------------------------------------------------------------------ pintar

    private void applyEnvio(Envio e) {
        currentEstado = e.estado();
        vCodigo.setText(e.codigo());
        vPedido.setText(e.pedidoId() == null ? "—" : "#" + e.pedidoId());
        vRuta.setText(e.ruta() == null ? Fmt.text(e.rutaId())
                : e.ruta().id() + (e.ruta().distanciaM() == null ? "" : String.format(Locale.ROOT, " · %.1f km",
                e.ruta().distanciaM() / 1000)));
        setEstado(e.estado(), e.progreso() == null ? 0 : e.progreso());
        Posicion p = e.posicion();
        setPosition(p == null ? null : p.latitude(), p == null ? null : p.longitude(),
                p == null ? null : p.speed(), p == null ? null : p.receivedAt());
        map.showEnvio(e);
    }

    private void applyUpdate(JsonNode u) {
        String estado = u.path("estado").asText(null);
        double prog = u.path("progreso").asDouble(0);
        Double lat = u.hasNonNull("latitude") ? u.get("latitude").asDouble() : null;
        Double lon = u.hasNonNull("longitude") ? u.get("longitude").asDouble() : null;
        Double speed = u.hasNonNull("speed") ? u.get("speed").asDouble() : null;
        currentEstado = estado;
        setEstado(estado, prog);
        if (lat != null) {
            setPosition(lat, lon, speed, u.path("received_at").asText(null));
        }
        map.update(lat, lon, prog, estado);
        checkDelivered(estado);
    }

    private void checkDelivered(String estado) {
        if (!"ENTREGADO".equals(estado) || entregadoAvisado) {
            return;
        }
        entregadoAvisado = true;
        setBanner("✔ ¡Tu pedido " + currentCode + " fue entregado!", "banner-ok");
        closeSocket();
        setConnection("Entregado · conexion cerrada", false);
        Alerts.info("Pedido entregado", "El envio " + currentCode + " llego a su destino.");
    }

    private void setEstado(String estado, double progreso) {
        vEstado.setText(estado == null ? "—" : estado);
        progress.setProgress(Math.max(0, Math.min(1, progreso)));
        vProgress.setText(String.format(Locale.ROOT, "%.1f %%", progreso * 100));
        int idx = -1;
        for (int i = 0; i < ESTADOS.size(); i++) {
            if (ESTADOS.get(i)[0].equals(estado)) {
                idx = i;
            }
        }
        timeline.getChildren().clear();
        for (int i = 0; i < ESTADOS.size(); i++) {
            String cls = idx < 0 ? "step-pending" : i < idx ? "step-done"
                    : i == idx ? ("ENTREGADO".equals(estado) ? "step-done" : "step-current") : "step-pending";
            Circle dot = new Circle(8);
            dot.getStyleClass().addAll("step-dot", cls);
            Label l = new Label(ESTADOS.get(i)[1]);
            l.getStyleClass().addAll("step-label", cls);
            Label raw = new Label(ESTADOS.get(i)[0]);
            raw.getStyleClass().add("muted-small");
            VBox text = new VBox(0, l, raw);
            HBox row = new HBox(10, dot, text);
            row.setAlignment(Pos.CENTER_LEFT);
            row.getStyleClass().add("step-row");
            timeline.getChildren().add(row);
            if (i < ESTADOS.size() - 1) {
                Region line = new Region();
                line.getStyleClass().addAll("step-line", i < idx ? "step-done" : "step-pending");
                HBox lineBox = new HBox(line);
                lineBox.getStyleClass().add("step-line-box");
                timeline.getChildren().add(lineBox);
            }
        }
        if (idx < 0 && estado != null) {
            Label otro = new Label("Estado no reconocido por la linea de tiempo: " + estado);
            otro.getStyleClass().add("warn-text");
            timeline.getChildren().add(otro);
        }
    }

    private void setPosition(Double lat, Double lon, Double speed, String receivedAt) {
        vCoords.setText(lat == null || lon == null ? "—"
                : String.format(Locale.ROOT, "%.5f, %.5f", lat, lon));
        vSpeed.setText(speed == null ? "—" : String.format(Locale.ROOT, "%.1f km/h", speed));
        vUpdated.setText(receivedAt == null ? "—" : Fmt.time(receivedAt));
    }

    private void clearPanel() {
        vCodigo.setText("—");
        vPedido.setText("—");
        vRuta.setText("—");
        setEstado(null, 0);
        setPosition(null, null, null, null);
    }

    private void setConnection(String text, boolean on) {
        connection.setText((on ? "● " : "○ ") + text);
        connection.getStyleClass().removeAll("conn-on", "conn-off");
        connection.getStyleClass().add(on ? "conn-on" : "conn-off");
    }

    private void setBanner(String text, String cls) {
        banner.getStyleClass().removeAll("banner-ok", "banner-warn", "banner-error");
        if (text == null) {
            banner.setVisible(false);
            banner.setManaged(false);
            return;
        }
        banner.setText(text);
        banner.getStyleClass().add(cls);
        banner.setVisible(true);
        banner.setManaged(true);
    }

    private static Label value() {
        Label l = new Label("—");
        l.getStyleClass().add("value");
        l.setWrapText(true);
        return l;
    }

    private static Label key(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("field-label");
        return l;
    }

    private static Label section(String s) {
        Label l = new Label(s);
        l.getStyleClass().add("section-title");
        return l;
    }

    @Override
    public Node node() {
        return root;
    }
}
