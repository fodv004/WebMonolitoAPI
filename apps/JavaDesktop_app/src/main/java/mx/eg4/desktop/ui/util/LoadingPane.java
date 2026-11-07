package mx.eg4.desktop.ui.util;

import java.util.concurrent.Callable;
import java.util.function.Consumer;

import javafx.geometry.Pos;
import javafx.scene.Node;
import javafx.scene.control.Label;
import javafx.scene.control.ProgressIndicator;
import javafx.scene.layout.StackPane;
import javafx.scene.layout.VBox;

/** Contenedor con indicador de carga encima del contenido mientras hay peticiones en curso. */
public final class LoadingPane extends StackPane {

    private final VBox overlay;
    private final Label message = new Label();
    private int pending;

    public LoadingPane(Node content) {
        ProgressIndicator pi = new ProgressIndicator();
        pi.setMaxSize(56, 56);
        message.getStyleClass().add("loading-text");
        overlay = new VBox(12, pi, message);
        overlay.setAlignment(Pos.CENTER);
        overlay.getStyleClass().add("loading-overlay");
        overlay.setVisible(false);
        getChildren().addAll(content, overlay);
    }

    /** Ejecuta en segundo plano; los errores se muestran con Alerts.error. */
    public <T> void run(String texto, Callable<T> work, Consumer<T> ok) {
        run(texto, work, ok, Alerts::error);
    }

    public <T> void run(String texto, Callable<T> work, Consumer<T> ok, Consumer<Throwable> err) {
        show(texto);
        Async.run(work, v -> {
            hide();
            ok.accept(v);
        }, e -> {
            hide();
            err.accept(e);
        });
    }

    private void show(String texto) {
        pending++;
        message.setText(texto == null ? "Cargando…" : texto);
        overlay.setVisible(true);
    }

    private void hide() {
        pending = Math.max(0, pending - 1);
        overlay.setVisible(pending > 0);
    }
}
