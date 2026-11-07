package mx.eg4.desktop.model;

import java.util.List;

/** Pedido de pedidos. En la lista (GET /pedidos) no vienen lineas ni historial. */
public record Pedido(Integer id, Integer userId, String estado, Double total, String createdAt, String updatedAt,
                     String expiraEn, Integer articulos, List<LineaPedido> lineas, List<HistorialPedido> historial) {
}
