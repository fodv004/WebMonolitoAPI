# Migraciones de pedidos

Archivos `NNN_descripcion.sql`, idempotentes y transaccionales, que solo tocan las tablas de este servicio.
`scripts/levantar_servicios.sh` los ejecuta en orden con `psql` (como `library_user`).

- `001_pedidos.sql`: tablas `inventario`, `pedidos`, `pedido_lineas` y `pedido_historial`, y carga inicial del
  inventario, una sola vez, con el `stock` de la tabla `libros` del monolito (que no se modifica).
