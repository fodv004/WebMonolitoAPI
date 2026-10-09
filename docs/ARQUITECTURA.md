# Arquitectura de los microservicios (proyecto Library)

Documento de referencia para todas las partes del proyecto. **Léelo antes de escribir código**: describe lo que
ya existe (Parte 1, ambiente base) y las convenciones que las siguientes partes deben respetar.

## 1. Servicios y puertos

| Servicio | Carpeta | Puerto | Estado (Parte 1) | Dueño de las tablas |
|---|---|---|---|---|
| login | `apps/services/login` | 5000 | Completo: registro, login, refresh, logout, sesión y confirmación de correo | `tokens_confirmacion` (lee `usuarios`) |
| books | `apps/services/library_soap_service` | 5001 | Completo: REST de libros + endpoint `/soap` (no se modifica) | `libros`, `formatos`, `generos`, `imagenes`, tablas SOAP y las heredadas `autores`, `libro_autor` |
| users | `apps/services/users` | 5002 | Completo (Parte 2): usuarios, roles, correos y contraseñas | `usuarios`, `roles` |
| authors | `apps/services/authors` | 5003 | Completo (Parte 3): autores y su relación con los libros | `authors`, `author_books` |
| pedidos | `apps/services/pedidos` | 5004 | Completo (Parte 4): pedidos, líneas, inventario y estados | `inventario`, `pedidos`, `pedido_lineas`, `pedido_historial` |
| pagos | `apps/services/pagos` | 5005 | Completo (Parte 5): pagos simulados y estado de los pedidos | `pagos` |
| Redis / Valkey | VM | 6379 | Solo en `127.0.0.1`, con contraseña | — |
| PostgreSQL | VM | 5432 | Base `library` (así se llama en la VM), usuario `library_user` | — |

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
| `session_store.py` | `revoke_user_sessions(user_id)`: cierra todas las sesiones de un usuario y revoca sus JWT (para cualquier servicio) |
| `auth.py` | `@require_auth`, `@require_role(ADMIN_ROLE_ID)`, `@require_internal_key`, `ADMIN_ROLE_ID`, `CLIENTE_ROLE_ID`, `ROLES` |
| `health.py` | `init_health(app, nombre, db_check, version)` → `GET /health` |
| `metrics.py` | `init_metrics(app, nombre)` → `GET /metrics`; `metrics.inc("...")` |
| `errors.py` | `ApiError(status, code, message)`, `error_response(...)`, `register_error_handlers(app)` (incluye 503 para `redis.RedisError` y PostgreSQL caído) |
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

### Endpoint interno de login

| Endpoint | Protección | Uso |
|---|---|---|
| `POST /internal/confirmation` `{"user_id","email","nombre"}` | `X-Internal-Key` | Crea el token en `tokens_confirmacion` y envía el correo de confirmación. Lo llama users al cambiar un correo; `GET /confirm` devuelve la cuenta a `confirmado` |

Al renovar (`POST /refresh`) login revoca el JWT anterior de la sesión: una sesión nunca tiene dos tokens vivos, y
por eso `revoke_user_sessions` los alcanza todos.

## 5. Roles

| `role_id` | `nombre` | Uso |
|---|---|---|
| 1 | `admin` | Operaciones administrativas y todas las escrituras del catálogo |
| 2 | `cliente` | Valor por defecto de cualquier cuenta nueva |

- Tabla `roles` y columna `usuarios.role_id` (FK, `NOT NULL DEFAULT 2`): migración `apps/services/users/sql/001_roles.sql`.
  Vive en users porque **users es el dueño de la tabla**; login solo lee `role_id`.
- La columna booleana del monolito es `usuarios.es_admin`. Las migraciones asignan `role_id = 1` a quien la tiene en
  `TRUE` y `2` al resto (solo la primera vez), y `es_admin` se conserva porque el monolito la sigue usando.
- **Sincronía `es_admin` ↔ `role_id`:** users escribe ambas al cambiar un rol y, además, el trigger
  `trg_usuarios_rol_y_fecha` (migración `002_users.sql`) las mantiene iguales sin importar quién escriba.
- **Un solo administrador:** el esquema del monolito trae el índice único `un_solo_admin` (`es_admin = TRUE`). Mientras
  exista, nombrar un segundo admin responde `409 UN_SOLO_ADMIN`. Para permitir varios hay que ejecutar a mano
  `apps/services/users/sql/opcional_permitir_varios_admins.sql` (no lo corre ningún script).
- Admin inicial: `apps/services/users/scripts/crear_admin.py` (una vez, después de las migraciones) asigna
  `role_id = 1` y `activo = true` a `ADMIN_EMAIL` y, solo si su `password_hash` es un valor de ejemplo del monolito,
  lo reemplaza por el hash bcrypt de `ADMIN_PASSWORD`.

## 6. Claves de Redis y TTL

| Clave | TTL | Constante en `redis_keys.py` |
|---|---|---|
| `session:<session_id>` | 7 días | `SESSION_TTL` |
| `refresh:<token_hash>` | 7 días | `SESSION_TTL` |
| `user:sessions:<user_id>` (SET) | 7 días | `SESSION_TTL` |
| `jwt:revoked:<jti>` | vida restante del JWT | — |
| `books:list:<filtros normalizados>` | 60 s | `CACHE_TTL` |
| `books:<isbn>` | 60 s | `CACHE_TTL` |
| `authors:list:<filtros>`, `authors:<id>`, `authors:<id>:books`, `authors:by-book:<isbn>` | 60 s | `CACHE_TTL` (todas bajo `AUTHORS_PATTERN`) |
| `pedido:reserva:<pedido_id>` (reserva de stock) | 15 min (`RESERVA_MINUTOS`) | `STOCK_RESERVATION_TTL` |
| `lock:pedidos:expirar` (`SET NX EX`) | 30 s | `LOCK_TTL` |
| `pago:idem:<idempotency_key>` (id del pago ya registrado con esa llave) | 24 h | `PAYMENT_IDEMPOTENCY_TTL`, `pago_idem()` |
| `pago:lock:<pedido_id>` (`SET NX EX`, mientras se paga o reembolsa un pedido) | 30 s | `LOCK_TTL`, `pago_lock()` |
| `lock:pagos:sync` (`SET NX EX`, tarea de sincronización de pagos) | 30 s | `LOCK_TTL`, `LOCK_SYNC_PAGOS` |

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

## 6 bis. Microservicio users (puerto 5002)

Administra usuarios, roles, correos y contraseñas sobre la **misma** tabla `usuarios` de login y del monolito
(no hay tabla duplicada). Login se queda solo con la autenticación.

### Columnas de `usuarios` y su nombre en la API

| Columna real | En la API | Nota |
|---|---|---|
| `id_usuario` | `id_usuario` | |
| `nombre`, `apellido_paterno`, `apellido_materno` | igual | apellidos opcionales (NULL) |
| `correo` | `email` | único; un trigger del monolito lo guarda en minúsculas |
| `password_hash` | *(nunca se devuelve)* | bcrypt 12 rondas, igual que login |
| `role_id` | `role_id`, `role` | FK a `roles` |
| `es_admin` | — | columna del monolito, sincronizada con `role_id` |
| `activo` | `activo` | baja lógica |
| `estado_cuenta` (`confirmado`/`pendiente`) | `email_verificado` (true/false) | no se creó una columna nueva |
| `fecha_registro` | `created_at` | no se creó una columna nueva |
| `updated_at` | `updated_at` | **única columna agregada** (`sql/002_users.sql`); la actualiza el trigger |

### Endpoints

| Método y ruta | Quién | Descripción |
|---|---|---|
| `GET /users?q=&role_id=&activo=&page=&per_page=` | admin | Lista paginada: `{"items","page","per_page","total","pages"}` (`per_page` máx. 100, default 20) |
| `GET /users/me` | JWT | La cuenta del token |
| `GET /users/{id}` | admin o el mismo usuario | |
| `POST /users` | admin | Alta: `nombre`, `apellido_paterno`, `apellido_materno`, `email`, `password`, `role_id` (default 2), `activo`. Nace con el correo verificado → 201 |
| `PUT /users/{id}` | admin o el mismo usuario | Reemplaza nombre y apellidos (`nombre` obligatorio). Solo admin: `activo`, `role_id` |
| `PATCH /users/{id}` | admin o el mismo usuario | Solo los campos enviados. Solo admin: `activo`, `role_id` (así se reactiva una cuenta) |
| `DELETE /users/{id}` | admin | Baja lógica (`activo = false`), idempotente |
| `PATCH /users/{id}/password` | admin o el mismo usuario | Propia: `password_actual` + `password_nueva`. El admin restablece la de **otro** usuario solo con `password_nueva` |
| `PATCH /users/{id}/email` | admin o el mismo usuario | Valida formato y registro MX (misma lógica de login), deja `email_verificado = false` y pide a login el correo de confirmación |
| `PATCH /users/{id}/role` | admin | `{"role_id": 1 \| 2}` |
| `GET /roles` | JWT | Catálogo de roles |
| `GET /users/internal/{id}` | `X-Internal-Key` | Datos mínimos para pedidos y pagos: `id_usuario`, `nombre` (completo), `email`, `role_id`, `activo`, `email_verificado` |

Usuario en las respuestas:

```json
{"id_usuario": 31, "nombre": "Ana", "apellido_paterno": "Pérez", "apellido_materno": null,
 "email": "ana@correo.com", "role_id": 2, "role": "cliente", "activo": true, "email_verificado": true,
 "created_at": "2026-09-01T10:00:00", "updated_at": "2026-10-06T12:00:00"}
```

### Reglas

- Un cliente que pide la cuenta de otro recibe **403** (antes de consultar la base: no se revela qué ids existen).
- `email` y `password` no se cambian con `PUT`/`PATCH /users/{id}` (400): tienen su propio endpoint.
- **Cierre de sesiones:** al cambiar la contraseña, desactivar o cambiar el rol se llama a
  `session_store.revoke_user_sessions(id)` **antes del COMMIT**. Si Redis falla, la transacción se deshace y la
  respuesta es **503** `REDIS_NO_DISPONIBLE`: el cambio no se aplica. El token anterior del usuario recibe 401.
- **Último admin:** el último administrador activo no puede perder el rol ni desactivarse → **409** `ULTIMO_ADMIN`.
- **Un solo admin (regla del monolito):** nombrar un segundo admin → **409** `UN_SOLO_ADMIN` mientras exista el índice.
- **Cambio de correo:** users pide el correo a login (`POST /internal/confirmation`, timeout 3 s) y *después*
  actualiza `correo`; si login no puede enviarlo → **503** `CORREO_NO_ENVIADO` y no cambia nada. Hasta abrir el
  enlace la cuenta queda `pendiente` y login no la deja entrar.
- Otros códigos: `VALIDACION` (400), `PASSWORD_ACTUAL_INCORRECTA` (400), `EMAIL_DUPLICADO` (409),
  `USUARIO_NO_ENCONTRADO` (404).

### Código

`routes/users.py` (HTTP) → `services/users_service.py` (reglas) → `db/repository.py` (SQL, `unit_of_work()`).
`services/passwords.py` y `services/validators.py` replican el algoritmo y las validaciones de login.
Pruebas: `tests/test_users.py` y `tests/test_crear_admin.py` (sin base de datos) y `tests/test_integracion_pg.py`
(migraciones y SQL sobre PostgreSQL real; solo corre con `TEST_DATABASE_URL` apuntando a una base desechable).

## 6 ter. Microservicio authors (puerto 5003)

Administra los autores y su relación con los libros, en tablas **propias** (migración `sql/001_authors.sql`):

| Tabla | Columnas |
|---|---|
| `authors` | `id`, `nombre` (obligatorio), `apellido`, `nacionalidad`, `fecha_nacimiento`, `biografia`, `created_at`, `updated_at` |
| `author_books` | `author_id` (FK a `authors`, `ON DELETE CASCADE`), `isbn`, `orden`; PK compuesta `(author_id, isbn)` |

- `author_books.isbn` **no tiene llave foránea**: el libro es de books. `orden` es la posición del autor entre los
  autores de ese libro (1 = primero); si no se envía se asigna el siguiente.
- **Tablas heredadas:** el monolito ya tenía `autores` y `libro_autor`, que books sigue usando para el campo de
  texto `autor` de sus tarjetas. No se modifican. La migración copia su contenido a las tablas nuevas **una sola
  vez** (mismo `id`; el nombre completo va a `nombre` y `apellido` queda vacío). Desde ahí cada lado evoluciona por
  separado: la fuente de verdad de autores es este servicio, y los clientes deben leer `GET /authors/by-book/{isbn}`
  en lugar del campo `autor` de books.

### Endpoints

| Método y ruta | Quién | Descripción |
|---|---|---|
| `GET /authors?q=&nacionalidad=&page=&per_page=` | público | Lista paginada `{"items","page","per_page","total","pages"}`, ordenada por apellido. `q` busca en nombre y apellido |
| `GET /authors/{id}` | público | |
| `GET /authors/{id}/books` | público | `{"author_id","enriquecido","books":[{"isbn","orden","titulo"}]}`. El título viene de books; si books falla, `enriquecido: false` y `titulo: null` |
| `GET /authors/by-book/{isbn}` | público | `{"isbn","authors":[{...autor,"orden"}]}` en orden. Sin relaciones → lista vacía (no consulta a books) |
| `POST /authors` | admin | `nombre` obligatorio; `apellido`, `nacionalidad`, `fecha_nacimiento` (`AAAA-MM-DD`, no futura), `biografia` → 201 |
| `PUT /authors/{id}` / `PATCH /authors/{id}` | admin | PUT reemplaza todos los campos; PATCH solo los enviados |
| `DELETE /authors/{id}` | admin | `409 AUTOR_CON_LIBROS` si tiene libros relacionados, salvo `?force=true` (borra también las relaciones) |
| `POST /authors/{id}/books` | admin | Body `{"isbn","orden"}`. Valida el libro con `GET {BOOKS_URL}/books/{isbn}` (timeout 3 s) → 201 |
| `DELETE /authors/{id}/books/{isbn}` | admin | Quita la relación (no borra ni el autor ni el libro) |

Autor en las respuestas:

```json
{"id": 3, "nombre": "Jorge Luis", "apellido": "Borges", "nombre_completo": "Jorge Luis Borges",
 "nacionalidad": "Argentina", "fecha_nacimiento": "1899-08-24", "biografia": null, "total_libros": 1,
 "created_at": "2026-10-06T12:00:00", "updated_at": "2026-10-06T12:00:00"}
```

### Reglas y errores

| Caso | Respuesta |
|---|---|
| Relacionar un ISBN que no existe en books | `404 LIBRO_NO_ENCONTRADO` |
| books no responde al validar el ISBN | `503 BOOKS_NO_DISPONIBLE` (no se crea la relación) |
| El libro ya está relacionado con ese autor | `409 RELACION_DUPLICADA` |
| Eliminar un autor con libros sin `?force=true` | `409 AUTOR_CON_LIBROS` |
| Autor o relación inexistente | `404 AUTOR_NO_ENCONTRADO` / `404 RELACION_NO_ENCONTRADA` |
| Datos inválidos | `400 VALIDACION` |
| Escritura sin token / sin rol admin / con Redis caído | `401` / `403` / `503` (módulo común) |

### Caché

Las cuatro lecturas se cachean 60 s (claves de la sección 6). **Cada escritura invalida `authors:*` con `SCAN`.**
La respuesta degradada de `/authors/{id}/books` (books caído) no se cachea. Si Redis falla, las lecturas se sirven
desde PostgreSQL y el fallo se cuenta en `/metrics` (`redis_errors`).

### Código

`routes/authors.py` → `services/authors_service.py` (reglas y caché) → `db/repository.py`;
`services/books_client.py` es el único punto que habla con books. Mismo esquema de pruebas que users
(`tests/test_authors.py` sin base de datos; `tests/test_integracion_pg.py` con `TEST_DATABASE_URL`).

## 6 quater. Microservicio pedidos (puerto 5004)

Crea y gestiona pedidos, líneas, stock y estados, en tablas **propias** (migración `sql/001_pedidos.sql`):

| Tabla | Columnas |
|---|---|
| `inventario` | `isbn` (PK), `stock_disponible`, `stock_reservado`, `updated_at` |
| `pedidos` | `id`, `user_id`, `estado`, `total`, `created_at`, `updated_at`, `expira_en`, `eliminado_en` (borrado lógico) |
| `pedido_lineas` | `id`, `pedido_id`, `isbn`, `titulo`, `cantidad`, `precio_unitario`, `subtotal` |
| `pedido_historial` | `id`, `pedido_id`, `estado_anterior`, `estado_nuevo`, `actor`, `fecha` |

- Sin llaves foráneas hacia otros servicios: `user_id` se valida con `GET {USERS_URL}/users/internal/{id}` e `isbn`
  con `GET {BOOKS_URL}/books/{isbn}` (timeout 3 s). El **título y el precio se copian** a la línea al crear el pedido.
- **Inventario vs. `libros.stock`:** el stock vendible es el de `inventario`. La migración lo carga una sola vez con
  `libros.stock`; a partir de ahí books conserva su columna `stock` (informativa, del monolito) y **no se
  sincronizan**. Los clientes deben leer `GET /inventario`.
- `actor` del historial: `user:<id>`, `admin:<id>`, `servicio:pagos` o `sistema:expiracion`.

### Estados

```
PENDIENTE_PAGO → PAGADO | CANCELADO | EXPIRADO
PAGADO         → ENVIADO | CANCELADO
ENVIADO        → ENTREGADO
```

Cualquier otra transición → `409 TRANSICION_INVALIDA`. Quién provoca cada una:

| Transición | Quién |
|---|---|
| → `PAGADO` | Servicio pagos, `PATCH /pedidos/internal/{id}/estado` |
| → `CANCELADO` | Dueño (solo desde `PENDIENTE_PAGO`), admin (desde `PENDIENTE_PAGO` o `PAGADO`) o pagos (interno) |
| → `EXPIRADO` | Tarea en segundo plano |
| → `ENVIADO`, `ENTREGADO` | Admin, `PATCH /pedidos/{id}/estado` |

### Stock

| Momento | `stock_disponible` | `stock_reservado` |
|---|---|---|
| Crear el pedido / agregar unidades al editar | `- n` (409 si no alcanza) | `+ n` |
| Cancelar o expirar un `PENDIENTE_PAGO` / quitar unidades al editar | `+ n` | `- n` |
| `PENDIENTE_PAGO` → `PAGADO` | — | `- n` (venta confirmada) |
| `PAGADO` → `CANCELADO` | `+ n` (las unidades regresan) | — |

Siempre dentro de una transacción y con las filas bloqueadas (`SELECT ... FOR UPDATE`), en orden fijo —primero el
pedido, después el inventario por `isbn`— para que dos peticiones simultáneas no se bloqueen entre sí. Los `CHECK`
de la tabla impiden stock negativo. `_cambiar_estado()` en `services/pedidos_service.py` es el **único** punto
donde un pedido cambia de estado y mueve stock.

### Endpoints

| Método y ruta | Quién | Descripción |
|---|---|---|
| `POST /pedidos` | JWT | Body `{"lineas":[{"isbn","cantidad"}]}` (1–999 por línea, sin ISBN repetidos). El `user_id` sale del token. Valida usuario y libros, reserva el stock → 201 |
| `GET /pedidos?estado=&user_id=&page=&per_page=` | JWT | Cliente: solo los suyos (el filtro `user_id` se ignora). Admin: todos. Cada elemento trae `articulos` |
| `GET /pedidos/{id}` | dueño o admin | Con `lineas` e `historial` |
| `PUT /pedidos/{id}` | dueño | Las líneas enviadas pasan a ser el pedido completo. Solo `PENDIENTE_PAGO` sin vencer; reajusta la reserva |
| `PATCH /pedidos/{id}/lineas` | dueño | Cambia solo las enviadas; `cantidad: 0` quita la línea |
| `PATCH /pedidos/{id}/cancelar` | dueño / admin | Libera el stock |
| `PATCH /pedidos/{id}/estado` | admin | `{"estado": "ENVIADO" \| "ENTREGADO"}` |
| `DELETE /pedidos/{id}` | admin | Borrado lógico; solo `CANCELADO` o `EXPIRADO` |
| `GET /pedidos/internal/{id}` | `X-Internal-Key` | Pedido completo, para pagos |
| `PATCH /pedidos/internal/{id}/estado` | `X-Internal-Key` | `{"estado": "PAGADO" \| "CANCELADO"}` |
| `GET /inventario?page=&per_page=` | público | `per_page` hasta 500 |
| `GET /inventario/{isbn}` | público | |
| `POST /inventario` | admin | `{"isbn","stock_disponible"}`; el libro debe existir en books |
| `PUT /inventario/{isbn}` | admin | Fija `stock_disponible` (no toca el reservado) |
| `DELETE /inventario/{isbn}` | admin | `409` si tiene unidades reservadas |

Pedido en las respuestas:

```json
{"id": 7, "user_id": 31, "estado": "PENDIENTE_PAGO", "total": 850.5, "articulos": 3,
 "created_at": "2026-10-06T12:00:00", "updated_at": "2026-10-06T12:00:00", "expira_en": "2026-10-06T12:15:00",
 "lineas": [{"isbn": "9780000000001", "titulo": "Cien años de soledad", "cantidad": 2, "precio_unitario": 300.0, "subtotal": 600.0}],
 "historial": [{"estado_anterior": null, "estado_nuevo": "PENDIENTE_PAGO", "actor": "user:31", "fecha": "2026-10-06T12:00:00"}]}
```

### Errores propios

| Código | HTTP | Caso |
|---|---|---|
| `STOCK_INSUFICIENTE` | 409 | No alcanza el stock; el mensaje indica el ISBN, lo disponible y lo solicitado |
| `TRANSICION_INVALIDA` | 409 | Cambio de estado no permitido |
| `PEDIDO_NO_EDITABLE` / `PEDIDO_EXPIRADO` | 409 | Editar un pedido que no está en `PENDIENTE_PAGO` o cuya reserva venció |
| `PEDIDO_NO_ELIMINABLE` | 409 | `DELETE` de un pedido que no está `CANCELADO` ni `EXPIRADO` |
| `INVENTARIO_DUPLICADO` / `INVENTARIO_CON_RESERVAS` | 409 | Alta repetida / baja con unidades reservadas |
| `LIBRO_NO_ENCONTRADO`, `PEDIDO_NO_ENCONTRADO`, `INVENTARIO_NO_ENCONTRADO` | 404 | |
| `USUARIO_NO_VALIDO` | 403 | La cuenta del token no existe o está desactivada |
| `BOOKS_NO_DISPONIBLE` / `USERS_NO_DISPONIBLE` | 503 | No se pudo validar el pedido |

### Expiración de reservas

- Al crear el pedido: `expira_en = NOW() + RESERVA_MINUTOS` (15 por defecto) y se escribe `pedido:reserva:<id>` en
  Redis con ese TTL. La clave es solo un espejo: **PostgreSQL es la fuente de verdad** y escribirla o borrarla
  nunca hace fallar una operación.
- `services/expiracion.py` corre como hilo dentro del servicio: cada 60 s toma `lock:pedidos:expirar`
  (`SET NX EX 30`) y, si lo obtiene, pasa a `EXPIRADO` los `PENDIENTE_PAGO` con `expira_en <= NOW()` (con
  `FOR UPDATE SKIP LOCKED`: no espera a un pedido que otra petición esté modificando) y libera su stock.
  Si Redis no responde, la vuelta se salta.
- Variables propias: `RESERVA_MINUTOS` (`1` para probar la expiración) y `EXPIRACION_AUTOMATICA` (`0` la desactiva).

### Código

`routes/pedidos.py` → `services/pedidos_service.py` / `services/inventario_service.py` → `db/repository.py`.
`services/clientes_http.py` es el único punto que habla con books y users. Pruebas: `tests/test_pedidos.py` (sin
base de datos) y `tests/test_integracion_pg.py` (bloqueos y concurrencia real; requiere `TEST_DATABASE_URL`).

## 6 quinquies. Microservicio pagos (puerto 5005)

Registra los pagos de los pedidos y actualiza su estado. **El pago es simulado**: no hay pasarela real.
Tabla propia (migración `sql/001_pagos.sql`, versión `007_pagos`):

| Columna | Nota |
|---|---|
| `id`, `pedido_id`, `user_id` | Sin llaves foráneas: el pedido es de pedidos y el usuario de users |
| `monto` | Copiado del pedido al pagar. **Nunca** se toma del cliente ni se edita |
| `metodo` | `TARJETA_SIMULADA`, `TRANSFERENCIA` o `EFECTIVO` |
| `estado` | `APROBADO`, `RECHAZADO` o `REEMBOLSADO` |
| `referencia` | `PAG-<fecha>-<8 hex>`; el admin puede corregirla |
| `ultimos4` | Últimos 4 dígitos de la tarjeta. **El número completo y el CVV no se guardan ni se registran en logs** |
| `idempotency_key` | `UNIQUE`: respaldo en base de la idempotencia |
| `sincronizado` | `FALSE` = pago aprobado que pedidos todavía no conoce |
| `notas`, `activo`, `created_at`, `updated_at` | `activo = false` es el borrado lógico |

Además hay un índice único `uq_pagos_pedido_aprobado`: un pedido no puede tener dos pagos `APROBADO`.

### Endpoints

| Método y ruta | Quién | Descripción |
|---|---|---|
| `POST /pagos` | JWT, dueño del pedido | Header **`Idempotency-Key`** obligatorio (8–100 caracteres). Body `{"pedido_id","metodo"}` y, con `TARJETA_SIMULADA`, `"tarjeta"` (13–19 dígitos) y `"cvv"` (3–4). **No lleva monto.** → `201`; si la llave ya se usó → `200` con el mismo pago y `"repetido": true` |
| `GET /pagos?estado=&metodo=&user_id=&page=&per_page=` | JWT | Cliente: solo los suyos. Admin: todos |
| `GET /pagos/{id}` | dueño o admin | |
| `GET /pagos/pedido/{pedido_id}` | dueño o admin | `{"pedido_id","items":[...]}` |
| `PATCH /pagos/{id}` | admin | Solo `referencia` y `notas`; cualquier otro campo (p. ej. `monto`) → 400 |
| `POST /pagos/{id}/reembolso` | admin | Body opcional `{"notas"}`. Pago → `REEMBOLSADO`, pedido → `CANCELADO` |
| `DELETE /pagos/{id}` | admin | Borrado lógico; solo pagos `RECHAZADO` |

Pago en las respuestas (nunca incluye la llave de idempotencia ni datos de tarjeta más allá de `ultimos4`):

```json
{"id": 12, "pedido_id": 7, "user_id": 31, "monto": 850.5, "metodo": "TARJETA_SIMULADA", "estado": "APROBADO",
 "referencia": "PAG-20261006-8F3A2C1B", "ultimos4": "1111", "sincronizado": true, "notas": null,
 "created_at": "2026-10-06T12:00:00", "updated_at": "2026-10-06T12:00:00"}
```

### Flujo de `POST /pagos`

1. **Idempotencia:** busca `pago:idem:<key>` en Redis y, como respaldo, la columna `idempotency_key`. Si ya existe
   devuelve el mismo pago sin cobrar otra vez (la llave debe ser del mismo usuario y pedido; si no, `409 LLAVE_YA_USADA`).
2. **Lock:** `pago:lock:<pedido_id>` con `SET NX EX 30` durante todo el proceso. Si otro proceso lo tiene →
   `409 PAGO_EN_PROCESO`. **Si Redis está caído → 503** y no se cobra.
3. **Pedido:** `GET {PEDIDOS_URL}/pedidos/internal/{id}` con `X-Internal-Key`. Debe existir (404), ser del `user_id`
   del token (403) y estar en `PENDIENTE_PAGO` (`409 PEDIDO_NO_PAGABLE`). El **monto es `total` del pedido**.
   Si pedidos no responde aquí → `503 PEDIDOS_NO_DISPONIBLE` y no se registra nada.
4. **Simulación:** una tarjeta terminada en `0000` se rechaza; todo lo demás se aprueba. El pago se guarda
   (`RECHAZADO` también queda registrado, con `201`).
5. **Aviso a pedidos (solo si se aprobó):** `PATCH {PEDIDOS_URL}/pedidos/internal/{id}/estado` con
   `{"estado": "PAGADO"}`. Si pedidos no responde, el pago queda con `sincronizado = false` y la respuesta sigue
   siendo `201`: lo reintenta la tarea en segundo plano.

Los endpoints internos y los estados de pedidos que usa pagos son exactamente los de la Parte 4
(`GET /pedidos/internal/{id}`, `PATCH /pedidos/internal/{id}/estado` con `PAGADO` o `CANCELADO`).

### Sincronización y reembolso

- **Tarea de sincronización** (`services/sincronizacion.py`, hilo dentro del servicio): cada 60 s toma
  `lock:pagos:sync` (`SET NX EX 30`) y reintenta el aviso de los pagos `APROBADO` con `sincronizado = false`, tomando
  también el lock del pedido. Si al reintentar pedidos responde 409, consulta el pedido: si ya está `PAGADO` (o
  más adelante) solo marca `sincronizado`; si quedó `CANCELADO` o `EXPIRADO` (la reserva venció mientras pedidos
  estaba caído) el pago se pasa a `REEMBOLSADO` automáticamente, con una nota. Si Redis no responde, la vuelta se salta.
- **Reembolso** (`POST /pagos/{id}/reembolso`): con el lock del pedido, pide a pedidos `CANCELADO` (ahí se
  **libera el stock**) y después marca el pago `REEMBOLSADO`. Si pedidos no responde → 503 y nada cambia. Si el
  pedido ya está `ENVIADO` o `ENTREGADO` → `409 PEDIDO_NO_CANCELABLE`.

### Errores propios

| Código | HTTP | Caso |
|---|---|---|
| `VALIDACION` | 400 | Falta `Idempotency-Key`, método o datos de tarjeta inválidos (el mensaje nunca repite la tarjeta) |
| `ROL_INSUFICIENTE` | 403 | Pagar un pedido ajeno, consultar pagos ajenos o acciones de admin |
| `PEDIDO_NO_ENCONTRADO`, `PAGO_NO_ENCONTRADO` | 404 | |
| `PEDIDO_NO_PAGABLE` | 409 | El pedido no está en `PENDIENTE_PAGO` |
| `PEDIDO_YA_PAGADO` | 409 | Ya tiene un pago aprobado (aunque aún no esté sincronizado) |
| `PAGO_EN_PROCESO` | 409 | El lock del pedido lo tiene otra petición |
| `LLAVE_YA_USADA` | 409 | Esa `Idempotency-Key` pertenece a otro pago |
| `PAGO_NO_REEMBOLSABLE` / `PAGO_NO_ELIMINABLE` / `PEDIDO_NO_CANCELABLE` | 409 | Reembolsar algo que no está `APROBADO`; eliminar algo que no está `RECHAZADO`; pedido ya enviado |
| `PEDIDOS_NO_DISPONIBLE` / `REDIS_NO_DISPONIBLE` | 503 | |

### Código

`routes/pagos.py` → `services/pagos_service.py` → `db/repository.py`; `services/pedidos_client.py` es el único
punto que habla con pedidos. Variable propia: `SINCRONIZACION_AUTOMATICA` (`0` desactiva la tarea).
Pruebas: `tests/test_pagos.py` (pytest + fakeredis, sin base de datos ni otros servicios).

## 7. Variables de entorno

| Variable | Servicios | Descripción |
|---|---|---|
| `PORT` | todos | Puerto (login y books también aceptan `FLASK_PORT`) |
| `DATABASE_URL` | users, authors, pedidos, pagos | `postgresql://library_user:<pass>@localhost:5432/library` |
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | login, books | Conexión de los dos servicios anteriores (psycopg2) |
| `REDIS_URL` | todos | `redis://:<pass>@127.0.0.1:6379/0` |
| `JWT_SECRET_KEY` | todos | **Mismo valor en los 6.** Obligatoria. Respaldo de compatibilidad: `JWT_SECRET`, luego `SECRET_KEY` |
| `JWT_ALGORITHM` | todos | `HS256` (cualquier otro valor impide arrancar) |
| `ACCESS_TOKEN_MINUTES` | login | `20` |
| `CORS_ALLOWED_ORIGINS` | todos | Orígenes separados por comas; nunca `*` |
| `INTERNAL_API_KEY` | todos | Mismo valor en los 6; header `X-Internal-Key` |
| `BOOKS_URL`, `USERS_URL`, `AUTHORS_URL`, `PEDIDOS_URL`, `PAGOS_URL` | los que llamen a otro | Por defecto `http://127.0.0.1:<puerto>`. authors usa `BOOKS_URL` para validar ISBN y traer títulos |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | users | Admin inicial (`scripts/crear_admin.py`) |
| `RESERVA_MINUTOS`, `EXPIRACION_AUTOMATICA` | pedidos | Duración de la reserva de stock (default 15) y tarea de expiración (default activa) |
| `SINCRONIZACION_AUTOMATICA` | pagos | Tarea que reintenta avisar a pedidos de los pagos sin sincronizar (default activa). Pagos usa además `PEDIDOS_URL` e `INTERNAL_API_KEY` |
| `LOGIN_URL` | users | Para pedir a login el correo de confirmación (default `http://127.0.0.1:5000`) |
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
| `screens/` | login, registro, inicio, libros (+ formulario), autores, usuarios, pedidos, pagos y configuración |
| `widgets/` | tema, menú lateral, panel de semáforos, tooltip y `dialogs.py` (formulario modal genérico) |
| `config/` | `settings.py`: `config.json` (IP, puertos, protocolo, certificado, semáforo). Sin tokens |
| `session.py` | JWT y refresh token **solo en memoria** |

- URL de un servicio: HTTP (por defecto) `http://<IP>:<puerto>`; HTTPS `https://<IP>/api/<servicio>`
  (proxy inverso en la VM que quita el prefijo `/api/<servicio>`; ver `VMComandos.md`).
- Semáforo: verde si `GET /health` responde 200 con `status: "ok"`; rojo en cualquier otro caso.
- Pantalla **Usuarios** (`screens/users_screen.py`): con rol admin es un panel de administración (filtros, tabla
  paginada y panel de acciones); con rol cliente es "Mi perfil". Se deshabilita sola si el semáforo de users está en
  rojo (`app.semaforos.en_rojo("users")` y `app.semaforos.al_cambiar(funcion)`): úsala de modelo para las siguientes.
- Pantalla **Autores** (`screens/authors_screen.py`): tabla con búsqueda a la izquierda y, a la derecha, los libros
  del autor con un buscador de libros (por ISBN o título) para relacionarlos. Las acciones de admin se ocultan al
  cliente. En **Libros**, la franja de detalle muestra los autores del libro seleccionado (`GET /authors/by-book`).
- Pantalla **Pedidos** (`screens/pedidos_screen.py`): pestaña *Comprar* (catálogo con stock, carrito y "Mis
  pedidos" con el estado en color) y, solo para el admin, *Gestión* e *Inventario*. El botón **Ir a pagar** llama a
  `app.ir_a_pagar(pedido_id)`, que abre la pantalla Pagos con ese pedido ya elegido.
- Pantalla **Pagos** (`screens/pagos_screen.py`), tipo caja: selector de pedidos pendientes, monto en grande de solo
  lectura, método de pago, tarjeta enmascarada (solo con `TARJETA_SIMULADA`), botón *Pagar*, comprobante e historial
  con filtros; el admin además reembolsa, corrige referencia y notas y elimina rechazados. Cada intento de pago
  genera un `Idempotency-Key` (uuid4) que **se reutiliza si se reintenta el mismo pago** (mismo pedido, método y
  tarjeta). La app no guarda el número de tarjeta ni el CVV. Se deshabilita sola con el semáforo de pagos en rojo.
- Una pantalla nueva recibe `(parent, app)` y usa `app.<cliente>` (`app.users`, `app.pedidos`...), `utils.run_async`
  para no congelar la ventana y `app.sesion_invalida(e)` cuando `e.es_sesion_invalida`.
