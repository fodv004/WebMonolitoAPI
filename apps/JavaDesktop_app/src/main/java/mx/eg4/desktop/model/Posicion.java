package mx.eg4.desktop.model;

/** Posicion de un envio (tracking). progreso solo viene en los puntos de "recorrido". */
public record Posicion(Double latitude, Double longitude, Double speed, Double heading, String receivedAt,
                       Double progreso) {
}
