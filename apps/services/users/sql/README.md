# Migraciones de users

Archivos `NNN_descripcion.sql`, idempotentes y transaccionales, que solo tocan las tablas de este servicio.
`scripts/levantar_servicios.sh` los ejecuta en orden con `psql` (como `library_user`).

- `001_roles.sql`: tabla `roles` (1 = admin, 2 = cliente) y `usuarios.role_id` (FK, default 2).
