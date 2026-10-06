# Microservicio pedidos (`apps/services/pedidos`)

Servicio que crea y gestiona pedidos, líneas de pedido, stock y estados. Puerto **5004**.
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> **Parte 1 (ambiente base):** solo expone `GET /health` y `GET /metrics`. Sin endpoints de negocio todavía.
> Convenciones, claims del JWT, roles y claves de Redis: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md).

Tablas de las que es dueño: `pedidos` y `pedido_lineas` (se crean en su parte del proyecto). Ningún otro servicio escribe en ellas.

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
deploy/       pedidos.service (systemd + gunicorn en 0.0.0.0:5004)
```

## Ejecución local

```bash
cd apps/services/pedidos
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # y completa JWT_SECRET_KEY, DATABASE_URL y REDIS_URL
python app.py                     # http://localhost:5004/health
pytest
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz).
