# Microservicio authors (`apps/services/authors`)

Administra los autores y su relación con los libros. Puerto **5003** (en la configuración se le llama "autores").
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> Endpoints, reglas y claves de caché: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md), sección *Microservicio authors*.

## Endpoints

| Método | Endpoint | Quién |
|---|---|---|
| GET | `/authors?q=&nacionalidad=&page=&per_page=` | público |
| GET | `/authors/{id}` | público |
| GET | `/authors/{id}/books` | público (con el título desde books; si books falla, solo los ISBN) |
| GET | `/authors/by-book/{isbn}` | público |
| POST | `/authors` | admin |
| PUT / PATCH | `/authors/{id}` | admin |
| DELETE | `/authors/{id}` | admin (`409` si tiene libros, salvo `?force=true`) |
| POST | `/authors/{id}/books` `{"isbn","orden"}` | admin (valida el ISBN en books) |
| DELETE | `/authors/{id}/books/{isbn}` | admin |
| GET | `/health`, `/metrics` | público |

## Base de datos

Tablas propias, creadas por `sql/001_authors.sql`:

- `authors (id, nombre, apellido, nacionalidad, fecha_nacimiento, biografia, created_at, updated_at)`
- `author_books (author_id, isbn, orden)` con PK compuesta `(author_id, isbn)` y **sin llave foránea al ISBN**:
  el libro vive en books. Antes de crear una relación se valida con `GET {BOOKS_URL}/books/{isbn}`
  (`404 LIBRO_NO_ENCONTRADO` si no existe, `503 BOOKS_NO_DISPONIBLE` si books no responde).

La migración copia **una sola vez** los autores y relaciones de las tablas del monolito (`autores`, `libro_autor`),
que no se modifican. El nombre completo queda en `nombre` (apellido vacío) y se corrige editando el autor.

## Caché (Redis, 60 s)

`authors:list:<filtros>`, `authors:<id>`, `authors:<id>:books` y `authors:by-book:<isbn>`. Cualquier escritura
invalida `authors:*` con `SCAN`. Si Redis falla, las lecturas se sirven desde PostgreSQL.

## Estructura

```
app.py                       entrypoint (common/app_factory.py)
routes/authors.py            endpoints
services/authors_service.py  reglas de negocio y caché
services/books_client.py     consulta de libros a books (timeout 3 s)
services/validators.py       validación de entradas
db/repository.py             SQL y unit_of_work()
sql/001_authors.sql          tablas y carga inicial
tests/                       pytest + fakeredis
deploy/authors.service       systemd + gunicorn en 0.0.0.0:5003
```

## Ejecución local y pruebas

```bash
cd apps/services/authors
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # y completa JWT_SECRET_KEY, DATABASE_URL, REDIS_URL y BOOKS_URL
python app.py                     # http://localhost:5003/health
pytest                            # no necesita PostgreSQL, Redis ni books
```

Migración y SQL contra un PostgreSQL real (base **desechable**):

```bash
TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/base_de_pruebas pytest tests/test_integracion_pg.py
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz).
