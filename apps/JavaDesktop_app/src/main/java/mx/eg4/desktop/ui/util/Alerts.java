package mx.eg4.desktop.ui.util;

import java.util.Optional;

import javafx.scene.control.Alert;
import javafx.scene.control.ButtonType;
import javafx.scene.control.Label;
import javafx.stage.Window;

import mx.eg4.desktop.http.ApiException;
import mx.eg4.desktop.util.Log;

/** Dialogos de aviso. Solo desde el hilo de JavaFX. */
public final class Alerts {

    private static Window owner;

    private Alerts() {
    }

    public static void setOwner(Window w) {
        owner = w;
    }

    /** Muestra el error de un servicio. Si la sesion termino no muestra nada (la App ya avisa). */
    public static void error(Throwable t) {
        ApiException api = unwrap(t);
        if (api != null && api.isSessionEnded()) {
            return;
        }
        if (api == null) {
            Log.warn("Error inesperado: " + t);
        }
        show(Alert.AlertType.ERROR, "Error", api != null ? title(api) : "Error inesperado", message(t));
    }

    public static String message(Throwable t) {
        ApiException api = unwrap(t);
        if (api != null) {
            return api.userMessage();
        }
        return t == null ? "Error desconocido" : (t.getMessage() != null ? t.getMessage() : t.toString());
    }

    public static String title(ApiException e) {
        return "Servicio " + e.service() + (e.status() > 0 ? " · HTTP " + e.status() : "") + " · " + e.code();
    }

    public static ApiException unwrap(Throwable t) {
        while (t != null) {
            if (t instanceof ApiException a) {
                return a;
            }
            t = t.getCause();
        }
        return null;
    }

    public static void info(String header, String text) {
        show(Alert.AlertType.INFORMATION, "Aviso", header, text);
    }

    public static void warn(String header, String text) {
        show(Alert.AlertType.WARNING, "Atencion", header, text);
    }

    public static boolean confirm(String header, String text) {
        Alert a = build(Alert.AlertType.CONFIRMATION, "Confirmar", header, text);
        Optional<ButtonType> r = a.showAndWait();
        return r.isPresent() && r.get() == ButtonType.OK;
    }

    private static void show(Alert.AlertType type, String title, String header, String text) {
        build(type, title, header, text).showAndWait();
    }

    private static Alert build(Alert.AlertType type, String title, String header, String text) {
        Alert a = new Alert(type);
        if (owner != null) {
            a.initOwner(owner);
        }
        a.setTitle(title);
        a.setHeaderText(header);
        Label l = new Label(text);
        l.setWrapText(true);
        l.setMaxWidth(460);
        a.getDialogPane().setContent(l);
        a.getDialogPane().getStylesheets().add(Alerts.class.getResource("/css/app.css").toExternalForm());
        return a;
    }
}
