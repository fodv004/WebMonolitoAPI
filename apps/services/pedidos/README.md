# Microservicio pedidos (`apps/services/pedidos`)

Crea y gestiona pedidos, líneas de pedido, stock y estados. Puerto **5004**.
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> Endpoints, estados, reglas de stock y errores: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md), sección *Microservicio pedidos*.

## Endpoints

| Método | Endpoint | Quién |
|---|---|---|
| POST | `/pedidos` `{"lineas":[{"isbn","cantidad"}]}` | JWT (el `user_id` sale del token) |
| GET | `/pedidos?estado=&user_id=&page=&per_page=` | JWT (cliente: los suyos; admin: todos) |
| GET | `/pedidos/{id}` | dueño o admin (con líneas e historial) |
| PUT | `/pedidos/{id}` · PATCH `/pedidos/{id}/lineas` | dueño, solo en `PENDIENTE_PAGO` |
| PATCH | `/pedidos/{id}/cancelar` | dueño en `PENDIENTE_PAGO`; admin si es cancelable |
| PATCH | `/pedidos/{id}/estado` `{"estado"}` | admin (`ENVIADO`, `ENTREGADO`) |
| DELETE | `/pedidos/{id}` | admin (borrado lógico; solo `CANCELADO` o `EXPIRADO`) |
| GET | `/pedidos/internal/{id}` · PATCH `/pedidos/internal/{id}/estado` | `X-Internal-Key` (servicio pagos) |
| GET | `/inventario`, `/inventario/{isbn}` | público |
| POST · PUT · DELETE | `/inventario`, `/inventario/{isbn}` | admin |
| GET | `/health`, `/metrics` | público |

## Estados

```
PENDIENTE_PAGO → PAGADO | CANCELADO | EXPIRADO
PAGADO         → ENVIADO | CANCELADO
ENVIADO        → ENTREGADO
```

Cualquier otra transición responde `409 TRANSICION_INVALIDA`.

## Stock

`inventario` guarda por ISBN el stock **disponible** y el **reservado**. Crear un pedido reserva sus unidades en una
transacción con `SELECT ... FOR UPDATE`; si no alcanza responde `409 STOCK_INSUFICIENTE` indicando el ISBN.
Cancelar o expirar devuelve las unidades; pagar las descuenta definitivamente.

## Expiración de reservas

Un pedido en `PENDIENTE_PAGO` conserva su reserva `RESERVA_MINUTOS` (15 por defecto). Una tarea en segundo plano,
dentro del propio servicio, revisa cada minuto (con el lock de Redis `lock:pedidos:expirar`) y pasa a `EXPIRADO`
los vencidos, liberando su stock. La decisión se toma con `pedidos.expira_en` de PostgreSQL.

Para probarla rápido: `RESERVA_MINUTOS=1` en el `.env` y reiniciar el servicio.

## Variables de entorno propias

| Variable | Default | Descripción |
|---|---|---|
| `RESERVA_MINUTOS` | `15` | Minutos que dura la reserva de stock de un pedido sin pagar |
| `EXPIRACION_AUTOMATICA` | `1` | `0` desactiva la tarea en segundo plano (pruebas) |

Además usa `BOOKS_URL` (títulos y precios), `USERS_URL` (validar al usuario) e `INTERNAL_API_KEY`.

## Estructura

```
app.py                        entrypoint; arranca la tarea de expiración
routes/pedidos.py             endpoints de pedidos e inventario
services/pedidos_service.py   estados, reservas de stock y permisos
services/inventario_service.py
services/expiracion.py        tarea en segundo plano + lock de Redis
services/clientes_http.py     consultas a books y users (timeout 3 s)
services/validators.py
db/repository.py              SQL y unit_of_work()
sql/001_pedidos.sql           tablas e inventario inicial
tests/                        pytest + fakeredis
deploy/pedidos.service        systemd + gunicorn en 0.0.0.0:5004
```

## Ejecución local y pruebas

```bash
cd apps/services/pedidos
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # y completa JWT_SECRET_KEY, DATABASE_URL, REDIS_URL e INTERNAL_API_KEY
python app.py                     # http://localhost:5004/health
pytest                            # no necesita PostgreSQL, Redis, books ni users
```

Migración, bloqueos y concurrencia real contra PostgreSQL (base **desechable**):

```bash
TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/base_de_pruebas pytest tests/test_integracion_pg.py
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz).
