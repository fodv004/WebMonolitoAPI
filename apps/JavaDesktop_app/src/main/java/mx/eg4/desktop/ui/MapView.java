package mx.eg4.desktop.ui;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import javafx.application.Platform;
import javafx.concurrent.Worker;
import javafx.scene.web.WebEngine;
import javafx.scene.web.WebView;

import mx.eg4.desktop.model.Envio;
import mx.eg4.desktop.http.Json;
import mx.eg4.desktop.util.Log;

/**
 * Mapa Leaflet + OpenStreetMap en un WebView (leaflet.js y leaflet.css van dentro de resources).
 * Java manda los datos al mapa con WebEngine.executeScript dentro de Platform.runLater.
 */
public final class MapView {

    private final WebView web = new WebView();
    private final WebEngine engine = web.getEngine();
    private final List<String> queue = new ArrayList<>();
    private boolean ready;

    public MapView(String userAgent) {
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
        // Que el WebView acepte cualquier tamano: el contenedor decide (ocupa todo el espacio libre).
        web.setMinSize(0, 0);
        web.setPrefSize(800, 600);
        web.setMaxSize(Double.MAX_VALUE, Double.MAX_VALUE);
        engine.load(MapView.class.getResource("/map/map.html").toExternalForm());
    }

    public WebView node() {
        return web;
    }

    /** Ruta completa en gris, recorrido en color y camion en la ultima posicion. */
    public void showEnvio(Envio envio) {
        run("showEnvio(" + Json.write(envio) + ")");
    }

    /** Mueve el camion y alarga la linea recorrida (sin recargar el mapa). */
    public void update(Double lat, Double lon, double progreso, String estado) {
        run(String.format(Locale.ROOT, "updatePosition(%s, %s, %f, %s)",
                lat == null ? "null" : lat.toString(), lon == null ? "null" : lon.toString(), progreso,
                Json.write(estado)));
    }

    public void reset() {
        run("resetMap()");
    }

    public WebEngine engine() {
        return engine;
    }

    /**
     * map.invalidateSize() en Leaflet. Siempre con Platform.runLater: se ejecuta despues de que JavaFX
     * termino el layout, cuando el WebView ya tiene su tamano final.
     */
    public void refrescarTamano() {
        Platform.runLater(() -> {
            if (ready) {
                try {
                    engine.executeScript("refrescarTamano()");
                } catch (Exception e) {
                    Log.warn("Error al refrescar el mapa: " + e.getMessage());
                }
            }
        });
    }

    private void run(String js) {
        Runnable r = () -> {
            if (ready) {
                try {
                    engine.executeScript(js);
                } catch (Exception e) {
                    Log.warn("Error en el mapa: " + e.getMessage());
                }
            } else {
                queue.add(js);
            }
        };
        if (Platform.isFxApplicationThread()) {
            r.run();
        } else {
            Platform.runLater(r);
        }
    }
}
