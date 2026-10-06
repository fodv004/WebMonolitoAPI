# Arquitectura de los microservicios (proyecto Library)

Documento de referencia para todas las partes del proyecto. **Léelo antes de escribir código**: describe lo que
ya existe (Parte 1, ambiente base) y las convenciones que las siguientes partes deben respetar.

## 1. Servicios y puertos

| Servicio | Carpeta | Puerto | Estado (Parte 1) | Dueño de las tablas |
|---|---|---|---|---|
| login | `apps/services/login` | 5000 | Completo: registro, login, refresh, logout, sesión | `tokens_confirmacion` (lee `usuarios`) |
| books | `apps/services/library_soap_service` | 5001 | Completo: REST de libros + endpoint `/soap` (no se modifica) | `libros`, `formatos`, `generos`, `imagenes`, tablas SOAP |
| users | `apps/services/users` | 5002 | Esqueleto (`/health`, `/metrics`) | `usuarios`, `roles` |
| authors | `apps/services/authors` | 5003 | Esqueleto | `autores`, `libro_autor` |
| pedidos | `apps/services/pedidos` | 5004 | Esqueleto | `pedidos`, líneas de pedido |
| pagos | `apps/services/pagos` | 5005 | Esqueleto | `pagos` |
| Redis / Valkey | VM | 6379 | Solo en `127.0.0.1`, con contraseña | — |
| PostgreSQL | VM | 5432 | Base `library_db`, usuario `library_user` | — |

- Los microservicios corren en la VM de GCP (`maquina-01`, CentOS Stream 10) como unidades systemd con gunicorn.
- La app de escritorio (`apps/Python_app`, Tkinter) corre en la máquina local y consume los 6 servicios.
- `apps/WebMonolito` y el endpoint `/soap` **no se tocan**.

**Regla de propiedad de datos:** cada servicio es dueño de sus tablas y ningún servicio escribe en las de otro.
Si necesita datos de otro servicio los pide por HTTP con **timeout de 3 segundos** y el header `X-Internal-Key`
(valor de `INTERNAL_API_KEY`, igual en todos; del lado receptor se valida con `@require_internal_key`).

## 2. Estructura de carpetas

```
apps/
  services/
    common/                  módulo compartido (ver sección 3)
      tests/                 pytest + fakeredis
    login/                   app.py, routes.py, sessions.py, security.py, config.py, db.py, ...
    library_soap_service/    app.py (/soap + init común), api/rest.py (books), api/auth_jwt.py, soap/, ...
    users/  authors/  pedidos/  pagos/        (los 4 con la misma forma)
      app.py                 entrypoint; crea la app con common/app_factory.py
      config/settings.py     SERVICE_NAME, DEFAULT_PORT, VERSION
      db/connection.py       get_conn(), ping()  (psycopg 3, DATABASE_URL)
      routes/__init__.py     register_routes(app): aquí se registran los blueprints
      services/              lógica de negocio (sin Flask)
      sql/                   migraciones NNN_descripcion.sql, idempotentes
      tests/                 pytest + fakeredis
      deploy/<nombre>.service
      .env.example  requirements.txt  requirements-dev.txt  README.md
  Python_app/                api/  screens/  widgets/  config/  session.py  main.py  tests/
scripts/
  levantar_servicios.sh      dependencias + migraciones + systemd (se ejecuta en la VM)
  estado_servicios.sh        systemctl status + curl a cada /health
  run_tests.sh               pytest de todas las suites
docs/
  ARQUITECTURA.md  REDIS.md
VMComandos.md                comandos para ejecutar y comprobar todo en la VM
```

Todos los servicios, incluidos login y books, tienen `deploy/<nombre>.service` (`login.service`, `books.service`...).

## 3. Módulo común (`apps/services/common`)

Cada `app.py` carga su `.env` y agrega `apps/services` al `sys.path` **antes** de importar `common`:

```python
load_dotenv(Path(__file__).with_name(".env"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common.app_factory import create_service_app
```

| Módulo | Qué ofrece |
|---|---|
| `config.py` | `settings`: `PORT`, `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET_KEY`, `JWT_ALGORITHM`, `ACCESS_TOKEN_MINUTES`, `CORS_ALLOWED_ORIGINS`, `INTERNAL_API_KEY`, `LOGIN_URL`, `BOOKS_URL`, `USERS_URL`, `AUTHORS_URL`, `PEDIDOS_URL`, `PAGOS_URL`. **Si falta `JWT_SECRET_KEY` el servicio no arranca.** |
| `redis_client.py` | `get_client()` (timeouts de 2 s), `ping()`, `cache_get`, `cache_set`, `cache_delete`, `cache_invalidate(patron)` con `SCAN` (nunca `KEYS`) |
| `redis_keys.py` | Nombres de claves y TTL (única fuente de verdad) |
| `auth.py` | `@require_auth`, `@require_role(ADMIN_ROLE_ID)`, `@require_internal_key`, `ADMIN_ROLE_ID`, `CLIENTE_ROLE_ID`, `ROLES` |
| `health.py` | `init_health(app, nombre, db_check, version)` → `GET /health` |
| `metrics.py` | `init_metrics(app, nombre)` → `GET /metrics`; `metrics.inc("...")` |
| `errors.py` | `ApiError(status, code, message)`, `error_response(...)`, `register_error_handlers(app)` |
| `logging_utils.py` | `init_logging(app)` (log HTTP + filtro), `redact(texto)`, `mask(dict)` |
| `cors.py` | `init_cors(app)` |
| `db.py` | `get_conn()` y `ping()` con psycopg 3 |
| `app_factory.py` | `create_service_app(nombre, version, db_check)`: todo lo anterior ya conectado |

### Convenciones

- **Errores:** siempre `{"error": "<CODIGO>", "message": "<texto>"}`. En las rutas nuevas, `raise ApiError(409, "PEDIDO_YA_PAGADO", "...")`.
  (login conserva su sobre `{status, code, message, data}` y books su `{"error", "mensaje"}`; la app Tk entiende los tres.)
- **Códigos HTTP:** 401 token ausente/inválido/expirado/revocado · 403 rol insuficiente · 409 conflicto de estado · 503 dependencia caída.
- **Escrituras** (`POST`, `PUT`, `PATCH`, `DELETE`): siempre con `@require_auth` o `@require_role(...)`.
  Las lecturas `GET` pueden ser públicas si solo consultan información; las administrativas llevan JWT y rol.
- **`/health`:** `{"service","status","db","redis","version"}`; 200 solo si PostgreSQL **y** Redis responden; 503 si no.
- **`/metrics`:** `requests_total`, `errors_4xx`, `errors_5xx`, `responses_401`, `responses_403`, `cache_hits`,
  `cache_misses`, `redis_errors`, `uptime_seconds`. Los contadores viven en memoria del proceso, por eso gunicorn
  corre con **1 worker y 4 hilos**.
- **Logs:** una línea por petición (`MÉTODO ruta status tiempo`), **sin query string ni body**. El filtro oculta
  `Authorization`, `password`, `password_actual`, `password_nueva`, `refresh_token`, `token` y `tarjeta` en cualquier
  línea de log. Para registrar un body usa `mask(datos)`.
- **Redis:** opcional para caché (los `cache_*` nunca lanzan: registran, cuentan y devuelven `None`/`False`);
  obligatorio para sesión, revocación y autorización (`get_client()` propaga `redis.RedisError` → 503).
- **CORS:** solo los orígenes de `CORS_ALLOWED_ORIGINS`; nunca `*`. Vacío = sin CORS.
- **Secretos:** solo en variables de entorno / `.env` (no versionado). Nunca en el código ni en los logs.

## 4. JWT de acceso

Lo emite `POST /login` (y `POST /refresh`) de login. HS256, firmado con `JWT_SECRET_KEY`, **20 minutos**.

| Claim | Ejemplo | Descripción |
|---|---|---|
| `sub` | `"31"` | id del usuario como texto |
| `user_id` | `31` | id del usuario (`usuarios.id_usuario`) |
| `role_id` | `2` | 1 = admin, 2 = cliente |
| `role` | `"cliente"` | nombre del rol |
| `jti` | `"9f1c..."` | id único del token (para revocarlo) |
| `iat` / `exp` | epoch | emisión y expiración (`exp = iat + 1200`) |
| `type` | `"access"` | siempre `access` |
| `email`, `sid` | | extras: correo y id de la sesión en Redis |

Validación en cada servicio (`common/auth.py`), en este orden:

1. Sin `Authorization: Bearer <token>` → **401** `TOKEN_AUSENTE`
2. `jwt.decode(..., algorithms=["HS256"])` fijo; firma o expiración inválidas → **401** `TOKEN_INVALIDO` / `TOKEN_EXPIRADO`
3. Falta algún claim (`sub`, `user_id`, `role_id`, `jti`, `iat`, `exp`, `type="access"`) → **401** `TOKEN_INVALIDO`
4. Existe `jwt:revoked:<jti>` → **401** `TOKEN_REVOCADO`. Redis caído → **503** `REDIS_NO_DISPONIBLE`
5. Rol insuficiente → **403** `ROL_INSUFICIENTE`

Uso en una ruta:

```python
from flask import g
from common.auth import ADMIN_ROLE_ID, require_auth, require_role

@bp.post("/pedidos")
@require_auth
def crear_pedido():
    user_id = g.jwt_payload["user_id"]

@bp.delete("/users/<int:user_id>")
@require_role(ADMIN_ROLE_ID)          # ya incluye la autenticación
def eliminar_usuario(user_id): ...
```

### Sesión, refresh y logout (login)

| Endpoint | Entrada | Resultado |
|---|---|---|
| `POST /login` | `{"email","password"}` | `data.token` (JWT), `data.refresh_token`, `data.expires_in` (1200), `data.user` (`role_id`, `role`) |
| `POST /refresh` | `{"refresh_token"}` | JWT nuevo y **refresh token nuevo** (el anterior queda inválido: un solo uso). Revalida la cuenta y relee el rol |
| `POST /logout` | `Authorization: Bearer` y/o `{"refresh_token"}` | Borra sesión y refresh token; agrega `jwt:revoked:<jti>` con TTL = vida restante |

Los tres responden **503** si Redis no está disponible. El cliente renueva de forma proactiva a los **17 minutos**.

## 5. Roles

| `role_id` | `nombre` | Uso |
|---|---|---|
| 1 | `admin` | Operaciones administrativas y todas las escrituras del catálogo |
| 2 | `cliente` | Valor por defecto de cualquier cuenta nueva |

- Tabla `roles` y columna `usuarios.role_id` (FK, `NOT NULL DEFAULT 2`): migración `apps/services/users/sql/001_roles.sql`.
  Vive en users porque **users es el dueño de la tabla**; login solo lee `role_id`.
- La primera vez que corre, la migración copia `es_admin = TRUE` → `role_id = 1`. La columna `es_admin` se conserva
  para el monolito; **el servicio users debe mantener `es_admin = (role_id = 1)` al cambiar el rol de un usuario.**
- Admin inicial: `apps/services/users/scripts/seed_admin.py` lo crea o actualiza con `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
  `ADMIN_NOMBRE`, `ADMIN_APELLIDO_PATERNO` y `ADMIN_APELLIDO_MATERNO` del `.env` de users.

## 6. Claves de Redis y TTL

| Clave | TTL | Constante en `redis_keys.py` |
|---|---|---|
| `session:<session_id>` | 7 días | `SESSION_TTL` |
| `refresh:<token_hash>` | 7 días | `SESSION_TTL` |
| `user:sessions:<user_id>` (SET) | 7 días | `SESSION_TTL` |
| `jwt:revoked:<jti>` | vida restante del JWT | — |
| `books:list:<filtros normalizados>` | 60 s | `CACHE_TTL` |
| `books:<isbn>` | 60 s | `CACHE_TTL` |
| Reserva de stock | 15 min | `STOCK_RESERVATION_TTL` |
| Idempotencia de pagos | 24 h | `PAYMENT_IDEMPOTENCY_TTL` |
| Locks | 30 s | `LOCK_TTL` |

JWT de acceso: 20 minutos (`ACCESS_TOKEN_MINUTES`); renovación proactiva del cliente a los 17.
Toda clave nueva se agrega **primero** a `redis_keys.py` (función + TTL) y a esta tabla. Detalle operativo en [`REDIS.md`](REDIS.md).

Patrón de caché (así lo hace books):

```python
datos = redis_client.cache_get(redis_keys.book(isbn))      # None si no hay o Redis falló
if datos is None:
    datos = consultar_postgresql(isbn)
    redis_client.cache_set(redis_keys.book(isbn), datos, redis_keys.CACHE_TTL)
# en cada POST/PUT/PATCH/DELETE:
redis_client.cache_delete(redis_keys.book(isbn))
redis_client.cache_invalidate(redis_keys.BOOKS_LIST_PATTERN)
```

## 7. Variables de entorno

| Variable | Servicios | Descripción |
|---|---|---|
| `PORT` | todos | Puerto (login y books también aceptan `FLASK_PORT`) |
| `DATABASE_URL` | users, authors, pedidos, pagos | `postgresql://library_user:<pass>@localhost:5432/library_db` |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | login, books | Conexión de los dos servicios anteriores (psycopg2) |
| `REDIS_URL` | todos | `redis://:<pass>@127.0.0.1:6379/0` |
| `JWT_SECRET_KEY` | todos | **Mismo valor en los 6.** Obligatoria. Respaldo de compatibilidad: `JWT_SECRET`, luego `SECRET_KEY` |
| `JWT_ALGORITHM` | todos | `HS256` (cualquier otro valor impide arrancar) |
| `ACCESS_TOKEN_MINUTES` | login | `20` |
| `CORS_ALLOWED_ORIGINS` | todos | Orígenes separados por comas; nunca `*` |
| `INTERNAL_API_KEY` | todos | Mismo valor en los 6; header `X-Internal-Key` |
| `BOOKS_URL`, `USERS_URL`, `AUTHORS_URL`, `PEDIDOS_URL`, `PAGOS_URL` | los que llamen a otro | Por defecto `http://127.0.0.1:<puerto>` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `ADMIN_NOMBRE`, `ADMIN_APELLIDO_*` | users | Admin inicial (`seed_admin.py`) |
| `SECRET_KEY`, `SMTP_*`, `MAIL_MODE`, `PUBLIC_BASE_URL`... | login | Cookie de Flask y correo (sin cambios) |
| `WS_SECURITY_USER`, `WS_SECURITY_PASSWORD_HASH` | books | WS-Security de `/soap` (sin cambios) |

## 8. Cómo agregar un servicio nuevo

1. Copia la carpeta de un esqueleto (por ejemplo `apps/services/pagos`) a `apps/services/<nombre>`.
2. En `config/settings.py` cambia `SERVICE_NAME` y `DEFAULT_PORT` (siguiente puerto libre: 5006).
3. Ajusta `.env.example` (`PORT`), `README.md` y `deploy/<nombre>.service` (nombre, carpeta y puerto en `--bind`).
4. Agrega el servicio a `SERVICIOS` en `scripts/levantar_servicios.sh` y `scripts/estado_servicios.sh`, y a la lista de `scripts/run_tests.sh`.
5. Agrega `<NOMBRE>_URL` en `common/config.py` si otros servicios lo van a llamar.
6. Tablas propias: migración `sql/001_<descripcion>.sql`, transaccional e idempotente (`IF NOT EXISTS`, registro en `schema_migraciones`).
7. Endpoints: blueprint en `routes/`, registrado en `register_routes(app)`; lógica en `services/`.
8. App Tk: nuevo cliente en `apps/Python_app/api/`, el servicio en `SERVICIOS`, `ETIQUETAS` y puertos por defecto de
   `config/settings.py` (el semáforo y Configuración lo toman de ahí) y su pantalla en `screens/`.
9. Abre el puerto en `firewalld` y en el firewall de GCP (ver `VMComandos.md`), y documenta el servicio en este archivo.

Para agregar **endpoints** a users, authors, pedidos o pagos solo aplican los pasos 6 a 8.

## 9. App de escritorio (`apps/Python_app`)

| Carpeta | Contenido |
|---|---|
| `api/` | `http_base.py` (cliente base: URL, timeout 5 s, `Authorization` automático, refresh ante 401, log sin secretos), un cliente por servicio y `health.py` |
| `screens/` | login, registro, inicio, libros (+ formulario), configuración y "En construcción" |
| `widgets/` | tema, menú lateral, panel de semáforos y tooltip |
| `config/` | `settings.py`: `config.json` (IP, puertos, protocolo, certificado, semáforo). Sin tokens |
| `session.py` | JWT y refresh token **solo en memoria** |

- URL de un servicio: HTTP (por defecto) `http://<IP>:<puerto>`; HTTPS `https://<IP>/api/<servicio>`
  (proxy inverso en la VM que quita el prefijo `/api/<servicio>`; ver `VMComandos.md`).
- Semáforo: verde si `GET /health` responde 200 con `status: "ok"`; rojo en cualquier otro caso.
- Una pantalla nueva recibe `(parent, app)` y usa `app.<cliente>` (`app.users`, `app.pedidos`...), `utils.run_async`
  para no congelar la ventana y `app.sesion_invalida(e)` cuando `e.es_sesion_invalida`.
