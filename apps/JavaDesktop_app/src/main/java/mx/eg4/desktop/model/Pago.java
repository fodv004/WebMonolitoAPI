package mx.eg4.desktop.model;

/** Pago de pagos. repetido = true cuando se reenvio una Idempotency-Key ya usada. */
public record Pago(Integer id, Integer pedidoId, Integer userId, Double monto, String metodo, String estado,
                   String referencia, String ultimos4, Boolean sincronizado, String notas, String createdAt,
                   String updatedAt, Boolean repetido) {
}
