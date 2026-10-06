# Microservicio authors (`apps/services/authors`)

Servicio que administra autores y sus relaciones con libros. Puerto **5003**.
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> **Parte 1 (ambiente base):** solo expone `GET /health` y `GET /metrics`. Sin endpoints de negocio todavía.
> Convenciones, claims del JWT, roles y claves de Redis: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md).

Tablas de las que es dueño: `autores` y `libro_autor`. Ningún otro servicio escribe en ellas.

## Endpoints

| Método | Endpoint | Función |
|---|---|---|
| GET | `/health` | `{"service","status","db","redis","version"}`; 200 solo si PostgreSQL y Redis responden, 503 si no |
| GET | `/metrics` | Peticiones, errores 4xx/5xx, 401, 403, cache hits/misses y errores de Redis |

## Estructura

```
app.py        entrypoint (usa common/app_factory.py)
config/       constantes del servicio (nombre, puerto, versión)
db/           conexión a PostgreSQL
routes/       blueprints (register_routes)
services/     lógica de negocio
sql/          migraciones NNN_descripcion.sql (idempotentes)
tests/        pytest + fakeredis
deploy/       authors.service (systemd + gunicorn en 0.0.0.0:5003)
```

## Ejecución local

```bash
cd apps/services/authors
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # y completa JWT_SECRET_KEY, DATABASE_URL y REDIS_URL
python app.py                     # http://localhost:5003/health
pytest
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz).
