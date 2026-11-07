package mx.eg4.desktop.model;

import java.util.List;

/** Ruta de Monterrey de un envio: puntos [[lat, lon], ...]. */
public record Ruta(String id, Double distanciaM, List<Double> inicio, List<Double> destino, List<List<Double>> puntos) {
}
