# Microservicio pagos (`apps/services/pagos`)

Registra los pagos de los pedidos y actualiza su estado. Puerto **5005**. **El pago es SIMULADO**: no hay pasarela real.
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> Flujo completo, reglas y errores: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md), sección *Microservicio pagos*.

## Endpoints

| Método | Endpoint | Quién |
|---|---|---|
| POST | `/pagos` (header `Idempotency-Key`) | JWT, dueño del pedido |
| GET | `/pagos?estado=&metodo=&user_id=&page=&per_page=` | JWT (cliente: los suyos; admin: todos) |
| GET | `/pagos/{id}` · `/pagos/pedido/{pedido_id}` | dueño o admin |
| PATCH | `/pagos/{id}` | admin (solo `referencia` y `notas`; nunca el monto) |
| POST | `/pagos/{id}/reembolso` | admin (pago → `REEMBOLSADO`, pedido → `CANCELADO` con liberación de stock) |
| DELETE | `/pagos/{id}` | admin (borrado lógico; solo `RECHAZADO`) |
| GET | `/health`, `/metrics` | público |

```bash
curl -X POST http://127.0.0.1:5005/pagos -H "Authorization: Bearer $TOKEN" -H "Idempotency-Key: $(uuidgen)" \
     -H 'Content-Type: application/json' \
     -d '{"pedido_id": 7, "metodo": "TARJETA_SIMULADA", "tarjeta": "4111111111111111", "cvv": "123"}'
```

## Reglas principales

- **Idempotencia:** reenviar la misma `Idempotency-Key` devuelve el mismo pago (`200`, `"repetido": true`) sin cobrar
  otra vez. Se guarda en Redis (`pago:idem:<key>`, 24 h) y, como respaldo, en la columna `UNIQUE`.
- **El monto sale del pedido** (`GET {PEDIDOS_URL}/pedidos/internal/{id}`), nunca del cliente.
- **Simulación:** una tarjeta terminada en `0000` se rechaza; lo demás se aprueba.
- **Lock** `pago:lock:<pedido_id>` (`SET NX EX 30`) durante todo el proceso. **Redis caído → 503.**
- **Pedidos caído tras aprobar:** el pago queda con `sincronizado = false` y una tarea en segundo plano
  (lock `lock:pagos:sync`) reintenta marcar el pedido como `PAGADO` cada minuto.
- **Tarjeta:** solo se guardan los últimos 4 dígitos. El número completo y el CVV no se guardan ni se registran.

## Base de datos

`sql/001_pagos.sql` (versión `007_pagos` en `schema_migraciones`) crea la tabla `pagos`. No modifica ninguna tabla
existente. La ejecuta `scripts/levantar_servicios.sh`.

## Variables de entorno

Las comunes (`DATABASE_URL` hacia la base `library`, `REDIS_URL`, `JWT_SECRET_KEY`, `INTERNAL_API_KEY`,
`PEDIDOS_URL`) y una propia opcional: `SINCRONIZACION_AUTOMATICA=0` desactiva la tarea en segundo plano.

## Estructura

```
app.py                         entrypoint; arranca la tarea de sincronización
routes/pagos.py                endpoints
services/pagos_service.py      idempotencia, lock, cobro simulado, reembolso y permisos
services/sincronizacion.py     tarea en segundo plano + lock de Redis
services/pedidos_client.py     endpoints internos de pedidos (timeout 3 s)
services/validators.py
db/repository.py               SQL y unit_of_work()
sql/001_pagos.sql              tabla pagos
tests/                         pytest + fakeredis
deploy/pagos.service           systemd + gunicorn en 0.0.0.0:5005
```

## Pruebas

No necesitan PostgreSQL, Redis, pedidos ni ningún servicio levantado (usan fakeredis y dobles en memoria):

```powershell
cd apps\services\pagos
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz, Parte 5).
