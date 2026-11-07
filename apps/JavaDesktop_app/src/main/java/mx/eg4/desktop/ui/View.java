package mx.eg4.desktop.ui;

import javafx.scene.Node;

/** Una pantalla de la barra lateral. */
public interface View {

    Node node();

    /** Al entrar a la pantalla. */
    default void onShow() {
    }

    /** Al salir de la pantalla o cerrar sesion. */
    default void onHide() {
    }
}
