package mx.eg4.desktop.model;

import java.util.List;

/** Envio de tracking. ruta y recorrido solo vienen en el envio completo (GET /envios/<codigo>, POST, snapshot). */
public record Envio(String codigo, Integer pedidoId, Integer userId, String rutaId, String estado, Double progreso,
                    Posicion posicion, Boolean pedidoSincronizado, String createdAt, String updatedAt,
                    String entregadoEn, Ruta ruta, List<Posicion> recorrido) {
}
