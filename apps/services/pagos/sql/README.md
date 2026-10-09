# Migraciones de pagos

Archivos `NNN_descripcion.sql`, idempotentes y transaccionales, que solo tocan las tablas de este servicio.
`scripts/levantar_servicios.sh` los ejecuta en orden con `psql` (como `library_user`, sobre la base `library`).

- `001_pagos.sql` (versión `007_pagos` en `schema_migraciones`): crea la tabla `pagos` con sus índices, entre ellos
  `idempotency_key UNIQUE` y el índice único que impide dos pagos `APROBADO` para el mismo pedido.
  No modifica ninguna tabla existente. No tiene columnas para el número de tarjeta ni el CVV: solo `ultimos4`.
