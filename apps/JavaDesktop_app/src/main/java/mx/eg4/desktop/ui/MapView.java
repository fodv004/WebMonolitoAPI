package mx.eg4.desktop.ui;

import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import javafx.application.Platform;
import javafx.beans.property.ReadOnlyStringWrapper;
import javafx.collections.FXCollections;
import javafx.collections.ObservableList;
import javafx.concurrent.Worker;
import javafx.scene.control.Label;
import javafx.scene.control.TableColumn;
import javafx.scene.control.TableView;
import javafx.scene.layout.Priority;
import javafx.scene.layout.Region;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;
import javafx.scene.web.WebEngine;
import javafx.scene.web.WebView;

import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.model.Envio;
import mx.eg4.desktop.model.Posicion;
import mx.eg4.desktop.ui.util.Fmt;
import mx.eg4.desktop.util.Log;

/**
 * Mapa Leaflet + OpenStreetMap en un WebView (leaflet.js y leaflet.css van dentro de resources).
 * Java manda los datos al mapa con WebEngine.executeScript dentro de Platform.runLater.
 *
 * El WebView necesita la DLL nativa jfxwebkit. Si el equipo la bloquea (p. ej. Windows Smart App
 * Control: UnsatisfiedLinkError) o no se puede inicializar, NO se truena la app: en lugar del mapa
 * se muestra un aviso "Mapa no disponible en este equipo" y una tabla con las posiciones recibidas
 * (codigo, estado, latitud, longitud, hora). El tracking por WebSocket sigue funcionando igual.
 */
public final class MapView {

    /** Error de la primera vez que fallo el WebView: no se vuelve a intentar en esta ejecucion. */
    private static volatile Throwable webViewError;

    private final StackPane container = new StackPane();
    private final WebMap web;            // null si el WebView no esta disponible
    private final Fallback fallback;     // null si el WebView si esta disponible

    public MapView(String userAgent) {
        WebMap w = null;
        if (webViewError == null) {
            try {
                w = new WebMap(userAgent);
            } catch (UnsatisfiedLinkError | ExceptionInInitializerError | NoClassDefFoundError e) {
                webViewError = e;
                Log.warn("Mapa no disponible (WebView/jfxwebkit no se pudo cargar): " + e);
            }
        }
        web = w;
        fallback = web == null ? new Fallback() : null;
        container.getChildren().add(web != null ? web.view : fallback.root);
        // Que el mapa acepte cualquier tamano: el contenedor decide (ocupa todo el espacio libre).
        container.setMinSize(0, 0);
        container.setPrefSize(800, 600);
        container.setMaxSize(Double.MAX_VALUE, Double.MAX_VALUE);
    }

    /** Nodo para poner en la vista: el WebView o el panel alternativo. */
    public Region node() {
        return container;
    }

    /** true si el mapa Leaflet (WebView) esta disponible en este equipo. */
    public boolean available() {
        return web != null;
    }

    /** Ejecuta la accion cada vez que map.html termina de cargar (solo con WebView). */
    public void onLoaded(Runnable action) {
        if (web != null) {
            web.engine.getLoadWorker().stateProperty().addListener((o, a, s) -> {
                if (s == Worker.State.SUCCEEDED) {
                    action.run();
                }
            });
        }
    }

    /** Ruta completa en gris, recorrido en color y camion en la ultima posicion. */
    public void showEnvio(Envio envio) {
        if (web != null) {
            web.run("showEnvio(" + Json.write(envio) + ")");
        } else {
            fx(() -> fallback.envio(envio));
        }
    }

    /** Mueve el camion y alarga la linea recorrida (sin recargar el mapa). */
    public void update(Double lat, Double lon, double progreso, String estado) {
        update(lat, lon, progreso, estado, null);
    }

    /** Igual que update(...), con la hora received_at del mensaje del WebSocket (para la tabla alternativa). */
    public void update(Double lat, Double lon, double progreso, String estado, String receivedAt) {
        if (web != null) {
            web.run(String.format(Locale.ROOT, "updatePosition(%s, %s, %f, %s)",
                    lat == null ? "null" : lat.toString(), lon == null ? "null" : lon.toString(), progreso,
                    Json.write(estado)));
        } else {
            fx(() -> fallback.add(null, estado, lat, lon, receivedAt));
        }
    }

    public void reset() {
        if (web != null) {
            web.run("resetMap()");
        } else {
            fx(fallback::clear);
        }
    }

    /**
     * map.invalidateSize() en Leaflet. Siempre con Platform.runLater: se ejecuta despues de que JavaFX
     * termino el layout, cuando el WebView ya tiene su tamano final.
     */
    public void refrescarTamano() {
        if (web == null) {
            return;
        }
        Platform.runLater(() -> {
            if (web.ready) {
                try {
                    web.engine.executeScript("refrescarTamano()");
                } catch (Exception e) {
                    Log.warn("Error al refrescar el mapa: " + e.getMessage());
                }
            }
        });
    }

    private static void fx(Runnable r) {
        if (Platform.isFxApplicationThread()) {
            r.run();
        } else {
            Platform.runLater(r);
        }
    }

    // ------------------------------------------------------------------ mapa Leaflet (WebView)

    /** Todo el uso de WebView/WebEngine vive aqui: si la DLL nativa falla, falla al construir esta clase. */
    private static final class WebMap {
        final WebView view;
        final WebEngine engine;
        final List<String> queue = new ArrayList<>();
        boolean ready;

        WebMap(String userAgent) {
            view = new WebView();
            engine = view.getEngine();
            engine.setUserAgent(userAgent);
            engine.setOnAlert(e -> Log.info("[mapa] " + e.getData()));
            engine.getLoadWorker().stateProperty().addListener((o, a, s) -> {
                if (s == Worker.State.SUCCEEDED) {
                    ready = true;
                    Log.info("Mapa cargado (User-Agent: " + userAgent + ")");
                    queue.forEach(engine::executeScript);
                    queue.clear();
                } else if (s == Worker.State.FAILED) {
                    Log.warn("No se pudo cargar map.html: " + engine.getLoadWorker().getException());
                }
            });
            view.setMinSize(0, 0);
            view.setPrefSize(800, 600);
            view.setMaxSize(Double.MAX_VALUE, Double.MAX_VALUE);
            engine.load(MapView.class.getResource("/map/map.html").toExternalForm());
        }

        void run(String js) {
            fx(() -> {
                if (ready) {
                    try {
                        engine.executeScript(js);
                    } catch (Exception e) {
                        Log.warn("Error en el mapa: " + e.getMessage());
                    }
                } else {
                    queue.add(js);
                }
            });
        }
    }

    // ------------------------------------------------------------------ panel alternativo (sin WebView)

    /** Una fila de la tabla alternativa (ya formateada para mostrar). */
    private record Fila(String codigo, String estado, String latitud, String longitud, String hora) {
    }

    /** Aviso + tabla con las posiciones recibidas; la mas reciente arriba. */
    private static final class Fallback {
        private static final int MAX_FILAS = 500;
        private static final DateTimeFormatter HORA_LOCAL = DateTimeFormatter.ofPattern("HH:mm:ss");

        final VBox root = new VBox(10);
        final ObservableList<Fila> filas = FXCollections.observableArrayList();
        String codigo;

        Fallback() {
            Label aviso = new Label("⚠ Mapa no disponible en este equipo");
            aviso.getStyleClass().addAll("banner", "banner-warn");
            aviso.setMaxWidth(Double.MAX_VALUE);
            Label detalle = new Label("Windows bloqueó el componente nativo del mapa (WebView). El rastreo en "
                    + "tiempo real sigue funcionando: abajo se listan las posiciones que llegan por el WebSocket.");
            detalle.setWrapText(true);

            TableView<Fila> tabla = new TableView<>(filas);
            tabla.setId("tracking-fallback-table");
            tabla.getColumns().add(columna("Código", Fila::codigo, 190));
            tabla.getColumns().add(columna("Estado", Fila::estado, 120));
            tabla.getColumns().add(columna("Latitud", Fila::latitud, 110));
            tabla.getColumns().add(columna("Longitud", Fila::longitud, 110));
            tabla.getColumns().add(columna("Hora", Fila::hora, 100));
            tabla.setColumnResizePolicy(TableView.CONSTRAINED_RESIZE_POLICY_FLEX_LAST_COLUMN);
            tabla.setPlaceholder(new Label("Consulta un código de rastreo para ver sus posiciones."));
            VBox.setVgrow(tabla, Priority.ALWAYS);

            root.getStyleClass().add("map-fallback");
            root.setStyle("-fx-padding: 12;");
            root.setMinSize(0, 0);
            root.getChildren().addAll(aviso, detalle, tabla);
        }

        private static TableColumn<Fila, String> columna(String titulo,
                                                         java.util.function.Function<Fila, String> valor,
                                                         double ancho) {
            TableColumn<Fila, String> c = new TableColumn<>(titulo);
            c.setCellValueFactory(cd -> new ReadOnlyStringWrapper(valor.apply(cd.getValue())));
            c.setPrefWidth(ancho);
            c.setSortable(false);
            return c;
        }

        void envio(Envio e) {
            codigo = e.codigo();
            Posicion p = e.posicion();
            add(e.codigo(), e.estado(), p == null ? null : p.latitude(), p == null ? null : p.longitude(),
                    p == null ? e.updatedAt() : p.receivedAt());
        }

        void add(String cod, String estado, Double lat, Double lon, String receivedAt) {
            String hora = receivedAt == null || receivedAt.isBlank()
                    ? LocalTime.now().format(HORA_LOCAL) : Fmt.time(receivedAt);
            filas.add(0, new Fila(cod != null ? cod : Fmt.text(codigo), Fmt.text(estado), coord(lat), coord(lon), hora));
            if (filas.size() > MAX_FILAS) {
                filas.remove(MAX_FILAS, filas.size());
            }
        }

        void clear() {
            codigo = null;
            filas.clear();
        }

        private static String coord(Double v) {
            return v == null ? "—" : String.format(Locale.ROOT, "%.5f", v);
        }
    }
}
