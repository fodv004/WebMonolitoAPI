# Migraciones de pedidos

Archivos `NNN_descripcion.sql`, idempotentes y transaccionales, que solo tocan las tablas de este servicio.
`scripts/levantar_servicios.sh` los ejecuta en orden con `psql` (como `library_user`).

Sin migraciones todavía (Parte 1).
