/** Cliente de escritorio de Library (JavaFX). */
module mx.eg4.desktop {
    requires javafx.controls;
    requires javafx.web;
    requires java.net.http;
    requires java.xml;
    requires com.fasterxml.jackson.databind;
    requires java.desktop;          // ImageIO: guardar PNG en el modo de demostracion

    exports mx.eg4.desktop to javafx.graphics;
    exports mx.eg4.desktop.demo to javafx.graphics;
    // Jackson lee y escribe los records por reflexion.
    opens mx.eg4.desktop.model to com.fasterxml.jackson.databind;
}
