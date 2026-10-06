# Migraciones de authors

Archivos `NNN_descripcion.sql`, idempotentes y transaccionales, que solo tocan las tablas de este servicio.
`scripts/levantar_servicios.sh` los ejecuta en orden con `psql` (como `library_user`).

- `001_authors.sql`: tablas `authors` y `author_books` (PK compuesta, sin FK al ISBN) y carga inicial, una sola vez,
  desde las tablas `autores` y `libro_autor` del monolito (que no se modifican).
