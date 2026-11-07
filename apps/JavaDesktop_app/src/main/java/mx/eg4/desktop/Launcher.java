package mx.eg4.desktop;

import javafx.application.Application;

/** Punto de entrada (main) que lanza la aplicacion JavaFX. */
public final class Launcher {

    private Launcher() {
    }

    public static void main(String[] args) {
        Application.launch(App.class, args);
    }
}
