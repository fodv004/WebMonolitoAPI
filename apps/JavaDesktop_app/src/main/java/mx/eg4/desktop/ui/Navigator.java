package mx.eg4.desktop.ui;

/** Navegacion entre pantallas de la ventana principal. */
public interface Navigator {

    void goCatalog();

    void goCart();

    /** pedidoId puede ser null. */
    void goPurchases(Integer pedidoId);

    /** codigo puede ser null (solo abre la pantalla). */
    void goTracking(String codigo);
}
