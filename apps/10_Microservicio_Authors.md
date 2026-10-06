Proyecto Library (monorepo WebMonolitoAPI). Ya están completas las PARTES 1 y 2. Antes de empezar, lee docs/ARQUITECTURA.md y apps/services/common. No modifiques otros servicios salvo lo indicado.

ESTA ES LA PARTE 3: microservicio authors (apps/services/authors, puerto 5003; en la configuración se le llama "autores") y su pantalla en la app Tk.

Responsabilidad: administrar autores y su relación con los libros.

Base de datos:
- authors (id, nombre, apellido, nacionalidad, fecha_nacimiento, biografia, created_at, updated_at)
- author_books (author_id, isbn, orden), con PK compuesta.
- Sin llave foránea al ISBN: antes de crear la relación, valida que el libro exista con GET {BOOKS_URL}/books/{isbn}. Si books no responde, devuelve 503.

Endpoints:
- GET /authors (público, paginado, filtros ?q=&nacionalidad=)
- GET /authors/{id} (público)
- GET /authors/{id}/books (público): enriquecido con el título desde books; si books falla, solo los ISBN
- GET /authors/by-book/{isbn} (público)
- POST /authors, PUT /authors/{id}, PATCH /authors/{id} (JWT + admin)
- DELETE /authors/{id} (JWT + admin): 409 si tiene libros relacionados, salvo ?force=true
- POST /authors/{id}/books con body {"isbn", "orden"} (JWT + admin)
- DELETE /authors/{id}/books/{isbn} (JWT + admin)

Caché en Redis:
- Claves authors:list:<filtros>, authors:<id>, authors:<id>:books y authors:by-book:<isbn>, con TTL de 60 segundos.
- Invalidar con SCAN en cada escritura.
- Si Redis falla, las lecturas se sirven desde PostgreSQL.

App Tk, pantalla Autores:
- Tabla de autores con búsqueda y formulario de alta y edición.
- Panel lateral con los libros del autor, buscador de libros por ISBN o título para relacionar, y botón para quitar la relación.
- En la pantalla Libros, mostrar los autores de cada libro en su detalle.
- Las acciones de admin se ocultan para el cliente.

Pruebas con pytest: CRUD, relación con un ISBN inexistente, books caído, caché e invalidación, permisos.

Comprobación de la Parte 3:
- Crear un autor, relacionarlo con un libro existente y verlo desde la pantalla Libros.
- Ver en /metrics un cache hit en la segunda consulta.
- Intentar relacionar un ISBN inexistente y recibir el error correcto.
- Actualiza docs/ARQUITECTURA.md.