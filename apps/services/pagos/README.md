# Microservicio pagos (`apps/services/pagos`)

Servicio que registra pagos y actualiza el estado de los pedidos. Puerto **5005**.
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> **Parte 1 (ambiente base):** solo expone `GET /health` y `GET /metrics`. Sin endpoints de negocio todavía.
> Convenciones, claims del JWT, roles y claves de Redis: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md).

Tablas de las que es dueño: `pagos` (se crea en su parte del proyecto). Ningún otro servicio escribe en ellas.

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
deploy/       pagos.service (systemd + gunicorn en 0.0.0.0:5005)
```

## Ejecución local

```bash
cd apps/services/pagos
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # y completa JWT_SECRET_KEY, DATABASE_URL y REDIS_URL
python app.py                     # http://localhost:5005/health
pytest
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz).
