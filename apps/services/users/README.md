# Microservicio users (`apps/services/users`)

Administra usuarios, roles, correos y contraseñas. Puerto **5002**.
Python 3 · Flask · psycopg · PostgreSQL · redis-py · PyJWT · flask-cors · gunicorn.

> Usa la **misma** tabla `usuarios` de login y del monolito (no la duplica). Login se queda solo con la autenticación.
> Endpoints, reglas y mapeo de columnas: [`docs/ARQUITECTURA.md`](../../../docs/ARQUITECTURA.md), sección *Microservicio users*.

## Endpoints

| Método | Endpoint | Quién |
|---|---|---|
| GET | `/users?q=&role_id=&activo=&page=&per_page=` | admin |
| GET | `/users/me` | JWT |
| GET | `/users/{id}` | admin o el mismo usuario |
| POST | `/users` | admin |
| PUT / PATCH | `/users/{id}` | admin o el mismo usuario (solo admin: `activo`, `role_id`) |
| DELETE | `/users/{id}` | admin (baja lógica) |
| PATCH | `/users/{id}/password` | el usuario (con su contraseña actual) o el admin (restablece la de otro) |
| PATCH | `/users/{id}/email` | admin o el mismo usuario (queda sin verificar; login envía la confirmación) |
| PATCH | `/users/{id}/role` | admin |
| GET | `/roles` | JWT |
| GET | `/users/internal/{id}` | `X-Internal-Key` (pedidos y pagos) |
| GET | `/health`, `/metrics` | público |

Nunca se devuelve `password_hash`. Las contraseñas se hashean con bcrypt (12 rondas), igual que login.

## Reglas principales

- Al cambiar la contraseña, desactivar o cambiar el rol se cierran las sesiones del usuario en Redis **antes** del
  COMMIT; si Redis falla la respuesta es 503 y el cambio no se aplica.
- El último administrador activo no puede perder el rol ni desactivarse (`409 ULTIMO_ADMIN`).
- El esquema del monolito admite **un solo administrador** (índice `un_solo_admin`): nombrar otro responde
  `409 UN_SOLO_ADMIN`. `sql/opcional_permitir_varios_admins.sql` quita esa restricción si decides permitir varios.

## Base de datos

| Archivo | Qué hace |
|---|---|
| `sql/001_roles.sql` | Tabla `roles` (1 admin, 2 cliente) y `usuarios.role_id` |
| `sql/002_users.sql` | `usuarios.updated_at` y el trigger que sincroniza `es_admin` ↔ `role_id` |
| `sql/opcional_permitir_varios_admins.sql` | **Opcional, manual.** Elimina el índice `un_solo_admin` |

Las numeradas las ejecuta `scripts/levantar_servicios.sh`; son idempotentes y no borran ni reescriben columnas.

Admin inicial (una vez, después de las migraciones; lee `ADMIN_EMAIL` y `ADMIN_PASSWORD` del `.env`):

```bash
.venv/bin/python scripts/crear_admin.py
```

## Estructura

```
app.py                      entrypoint (common/app_factory.py)
routes/users.py             endpoints
services/users_service.py   reglas de negocio
services/passwords.py       bcrypt (igual que login)
services/validators.py      nombres, correo + MX (igual que login), filtros
services/login_client.py    pide a login el correo de confirmación
db/repository.py            SQL y unit_of_work()
scripts/crear_admin.py      administrador inicial
sql/                        migraciones
tests/                      pytest + fakeredis
deploy/users.service        systemd + gunicorn en 0.0.0.0:5002
```

## Ejecución local y pruebas

```bash
cd apps/services/users
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env              # y completa JWT_SECRET_KEY, DATABASE_URL, REDIS_URL e INTERNAL_API_KEY
python app.py                     # http://localhost:5002/health
pytest                            # no necesita PostgreSQL ni Redis
```

Pruebas de las migraciones y del SQL contra un PostgreSQL real (base **desechable**, nunca la de la aplicación):

```bash
TEST_DATABASE_URL=postgresql://usuario:clave@localhost:5432/base_de_pruebas pytest tests/test_integracion_pg.py
```

En la VM se despliega con `scripts/levantar_servicios.sh` (ver `VMComandos.md` en la raíz).
