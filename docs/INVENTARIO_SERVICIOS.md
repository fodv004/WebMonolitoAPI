# Inventario de servicios (apps/services)

Leído del código del repositorio (no de la VM). Los JSON de ejemplo reproducen la **forma** que arma
el código; los valores son ilustrativos. Base para el cliente `apps/JavaDesktop_app`.

| Servicio | Carpeta | Puerto | Archivo principal | BD / Redis |
|---|---|---|---|---|
| login | `login/` | 5000 | `login/app.py` (rutas en `login/routes.py`) | PostgreSQL (psycopg2) + Redis |
| books | `library_soap_service/` | 5001 | `library_soap_service/app.py` (REST en `api/rest.py`, SOAP en `soap/`) | PostgreSQL (psycopg2) + Redis (caché opcional) |
| users | `users/` | 5002 | `users/app.py` (rutas en `routes/users.py`) | PostgreSQL (psycopg 3) + Redis |
| authors | `authors/` | 5003 | `authors/app.py` (rutas en `routes/authors.py`) | PostgreSQL + Redis |
| pedidos | `pedidos/` | 5004 | `pedidos/app.py` (rutas en `routes/pedidos.py`) | PostgreSQL + Redis |
| pagos | `pagos/` | 5005 | `pagos/app.py` (rutas en `routes/pagos.py`) | PostgreSQL + Redis |
| tracking | `tracking/` | 5900 | `tracking/app.py` | Ninguna (memoria del proceso) |

El puerto sale de `PORT`/`FLASK_PORT` del `.env` de cada servicio; los valores de la tabla son los
de `.env.example` / `DEFAULT_PORT`. Los servicios se llaman entre sí con `LOGIN_URL`, `BOOKS_URL`,
`USERS_URL`, `AUTHORS_URL`, `PEDIDOS_URL`, `PAGOS_URL` (`common/config.py`).

---

## Validación del JWT (común a users, authors, pedidos, pagos y escrituras de books)

Implementada en `common/auth.py`. El token lo **emite login** (`login/security.py`, `create_access_token`).

| Aspecto | Valor |
|---|---|
| Header | `Authorization: Bearer <token>` (sin él → `401 TOKEN_AUSENTE`) |
| Algoritmo | `HS256` fijo (`JWT_ALGORITHM`; cualquier otro valor en `.env` aborta el arranque) |
| Secreto | Variable `JWT_SECRET_KEY` del `.env`, **igual en todos los servicios**. Respaldo con aviso: `JWT_SECRET`, luego `SECRET_KEY`. Si no hay ninguno, el servicio no arranca |
| Vigencia | `ACCESS_TOKEN_MINUTES` (por defecto 20 min) |
| Claims obligatorios | `sub`, `user_id`, `role_id`, `jti`, `iat`, `exp`, `type` (= `"access"`) |
| Claims extra que emite login | `role` (`"admin"`/`"cliente"`), `email`, `sid` (id de sesión en Redis) |
| Id de usuario | `user_id` (entero). `sub` es el mismo id como texto |
| Rol | `role_id`: `1` = admin, `2` = cliente (`ADMIN_ROLE_ID`, `CLIENTE_ROLE_ID`) |
| Revocación | Si existe `jwt:revoked:<jti>` en Redis → `401 TOKEN_REVOCADO` (lo escribe `POST /logout`, cambio de contraseña/rol/baja). Redis caído → `503 REDIS_NO_DISPONIBLE` |
| Errores | `401 TOKEN_EXPIRADO`, `401 TOKEN_INVALIDO`, `403 ROL_INSUFICIENTE` |
| Decoradores | `@require_auth` (cualquier rol), `@require_role(ADMIN_ROLE_ID)` (solo admin), `@require_internal_key` (entre servicios: header `X-Internal-Key` == `INTERNAL_API_KEY`) |

Payload de ejemplo:

```json
{"sub": "31", "user_id": 31, "role_id": 2, "role": "cliente", "email": "ana@correo.com",
 "sid": "9f2c…", "jti": "a41b…", "iat": 1762400000, "exp": 1762401200, "type": "access"}
```

Formato de error común (users, authors, pedidos, pagos): `{"error": "<CODIGO>", "message": "<texto>"}`.
login usa su propio sobre y books REST usa `{"error": "...", "mensaje": "..."}` (ver cada sección).

Todos los servicios (menos tracking) exponen además, públicos:

| Método | Ruta | JWT | Respuesta |
|---|---|---|---|
| GET | `/health` | No | `{"service": "users", "status": "ok", "db": "ok", "redis": "ok", "version": "1.0.0"}` (503 si BD o Redis fallan) |
| GET | `/metrics` | No | `{"service": "users", "uptime_seconds": 120, "requests_total": 10, "errors_4xx": 1, "errors_5xx": 0, "responses_401": 0, "responses_403": 0, "cache_hits": 0, "cache_misses": 0, "redis_errors": 0}` |

---

## 1. login (5000)

Archivo principal: `apps/services/login/app.py`. Swagger en `/apidocs/`.
**Responde XML por defecto**; para JSON agrega `?format=json` a cualquier ruta. Sobre de respuesta:
`{"status": "ok"|"error", "code": "...", "message": "...", "data": {...}}` (errores de validación
agregan `"errors": [{"field", "message"}]`). Acepta cuerpo JSON o formulario.

| Método | Ruta | JWT | Body de entrada | Respuesta JSON de ejemplo (`?format=json`) |
|---|---|---|---|---|
| POST | `/register` | No | `{"nombre", "apellido_paterno", "apellido_materno", "email", "password"}` (password 8–72) | `201` `{"status":"ok","code":"USUARIO_REGISTRADO","message":"Usuario registrado. Revisa tu correo…","data":{"id_usuario":31,"nombre":"Ana","apellido_paterno":"Pérez","apellido_materno":"Ruiz",…}}`. `409 EMAIL_DUPLICADO`, `503 CORREO_NO_ENVIADO` |
| GET | `/confirm?token=…` | No | — | Sin `format`: redirige a `/confirmed?status=…`. Con `format`: sobre con el resultado |
| GET | `/confirmed?status=…` | No | — | Página HTML de resultado de la confirmación |
| POST | `/login` | No | `{"email", "password"}` | `200` `{"status":"ok","code":"LOGIN_EXITOSO","message":"Sesión iniciada.","data":{"authenticated":true,"user":{"id_usuario":31,"nombre":"Ana","apellido_paterno":"Pérez","apellido_materno":"Ruiz","email":"ana@correo.com","es_admin":false,"estado_cuenta":"confirmado","role_id":2,"role":"cliente"},"token":"<jwt>","token_type":"Bearer","expires_in":1200,"refresh_token":"<opaco>","refresh_expires_in":604800}}`. También pone la cookie `auth_session`. `401 CREDENCIALES_INVALIDAS`, `403 CUENTA_INACTIVA`, `403 CUENTA_NO_CONFIRMADA` |
| POST | `/refresh` | No (usa refresh token) | `{"refresh_token": "…"}` | `200` `code: "TOKEN_RENOVADO"`, mismo `data` que login (token y refresh nuevos; el refresh rota). `401 REFRESH_INVALIDO` |
| POST | `/logout` | Opcional (`Authorization: Bearer`) | Opcional `{"refresh_token": "…"}` | `200` `{"status":"ok","code":"LOGOUT_EXITOSO","message":"Sesión cerrada.","data":{"authenticated":false}}`. Revoca el `jti` y borra la sesión. Idempotente |
| GET | `/session` | No (usa la **cookie** de Flask, no el JWT) | — | `200` `code: "SESION_ACTIVA"` con `data.user`, o `code: "SIN_SESION"` con `{"authenticated": false}` |
| POST | `/internal/confirmation` | `X-Internal-Key` | `{"user_id", "email", "nombre"}` | Lo usa users al cambiar el correo |
| GET | `/` | No | — | Redirige a `/apidocs/` |

JWT: login **emite** el token (no lo valida en sus rutas, salvo `decode_own_token` en `/logout`, que acepta tokens vencidos).

---

## 2. books — `library_soap_service` (5001)

Archivo principal: `apps/services/library_soap_service/app.py` (`SERVICE_NAME = "books"`).
REST en `api/rest.py`; SOAP en `/soap` (ver sección SOAP).
**REST responde XML por defecto**; JSON con `?format=json` (valor inválido → `400 FORMATO_INVALIDO`).
Errores REST: `{"error": "<CODIGO>", "mensaje": "<texto>"}`.
`GET /books` y `GET /books/<isbn>` se cachean 60 s en Redis.

| Método | Ruta | JWT | Body de entrada | Respuesta JSON de ejemplo (`?format=json`) |
|---|---|---|---|---|
| GET | `/books` | No | — | `200` `[{"isbn":"9780000000001","titulo":"…","anio":2020,"precio":299.0,"stock":12,"formato":"Pasta blanda","autor":"Autor A, Autor B","genero":"Novela","portada":"https://…/img.jpg","image_url":"https://…/img.jpg","href":"http://host:5001/books/9780000000001"}]` (XML agrega `cloudConcepts`) |
| GET | `/books/<isbn>` | No | — | `200` `{"isbn":"…","titulo":"…","anio":2020,"precio":299.0,"stock":12,"formato":"Pasta blanda","portada":"https://…","href":"http://host:5001/books/…"}` (sin `autor` ni `genero`). `404 LIBRO_NO_ENCONTRADO` |
| GET | `/books/gallery` | No | — | `200` `[{"isbn":"…","titulo":"…","imagenes":[{"url":"https://…","principal":true}],"href":"…"}]` |
| GET | `/cloud-concepts` | No | — | `200` `{"modelosCloud":["IaaS","PaaS","SaaS","FaaS"],"libros":[{"isbn":"…","titulo":"…","conceptosCloud":[{"concepto":"…","modelo":"SaaS"}]}]}` |
| GET | `/formats` | No | — | `200` `[{"id_formato":1,"nombre":"Pasta blanda"}]` |
| POST | `/books` | Sí, **admin** | `{"isbn"(≤13), "titulo", "anio", "precio", "stock", "formato"}` + opcionales `"autor"`, `"genero"`, `"portada"` (URL) | `201` tarjeta igual a un elemento de `GET /books`. `409 ISBN_DUPLICADO`, `400 VALIDACION` |
| PUT | `/books/<isbn>` | Sí, **admin** | Cualquier subconjunto de `titulo, anio, precio, stock, formato, autor, genero, portada` | `200` tarjeta. `404 LIBRO_NO_ENCONTRADO` |
| PATCH | `/books/<isbn>` | Sí, **admin** | Igual que PUT (mismo código) | `200` tarjeta |
| DELETE | `/books/<isbn>` | Sí, **admin** | — | `200` `{"status":"ok","mensaje":"Libro … eliminado.","isbn":"…"}`. `409 LIBRO_EN_USO` |
| POST | `/books/internal/stock/reservar` | `X-Internal-Key` | `{"items":[{"isbn":"…","cantidad":2}]}` | `200` `{"status":"ok","items":[{"isbn":"…","stock":10}]}`. `409 STOCK_INSUFICIENTE` (lo usa pedidos) |
| POST | `/books/internal/stock/liberar` | `X-Internal-Key` | Igual | Igual (suma stock) |
| POST | `/soap` | No (una operación usa WS-Security) | Sobre SOAP 1.1 | XML (ver sección SOAP) |

JWT: `api/auth_jwt.py` → `jwt_requerido = require_role(ADMIN_ROLE_ID)` (common/auth.py). Solo las escrituras lo usan.

---

## 3. users (5002)

Archivo principal: `apps/services/users/app.py`. Un cliente solo puede leer o modificar su propia cuenta
(si no → `403 ROL_INSUFICIENTE`).

Objeto usuario (`publico`):
```json
{"id_usuario": 31, "nombre": "Ana", "apellido_paterno": "Pérez", "apellido_materno": "Ruiz",
 "email": "ana@correo.com", "role_id": 2, "role": "cliente", "activo": true,
 "email_verificado": true, "created_at": "2026-10-01T12:00:00", "updated_at": "2026-10-02T09:30:00"}
```

| Método | Ruta | JWT | Body de entrada | Respuesta JSON de ejemplo |
|---|---|---|---|---|
| GET | `/users?q=&role_id=&activo=&page=&per_page=` | Sí, **admin** | — | `200` `{"items":[<usuario>],"page":1,"per_page":20,"total":31,"pages":2}` |
| GET | `/users/me` | Sí | — | `200` `<usuario>` |
| GET | `/users/<id>` | Sí (propio o admin) | — | `200` `<usuario>`. `404 USUARIO_NO_ENCONTRADO` |
| POST | `/users` | Sí, **admin** | `{"nombre","apellido_paterno","apellido_materno","email","password"}` + opcional `"role_id"` (default 2), `"activo"` | `201` `<usuario>` (nace confirmado). `409 EMAIL_DUPLICADO` |
| PUT | `/users/<id>` | Sí (propio o admin) | `nombre, apellido_paterno, apellido_materno`; solo admin: `role_id, activo` | `200` `<usuario>` |
| PATCH | `/users/<id>` | Sí (propio o admin) | Subconjunto de lo anterior | `200` `<usuario>` |
| DELETE | `/users/<id>` | Sí, **admin** | — | `200` `<usuario>` con `"activo": false` (baja lógica) |
| PATCH | `/users/<id>/password` | Sí (propio o admin) | `{"password_nueva"}` + `"password_actual"` si es la propia | `200` `{"status":"ok","message":"Contraseña actualizada. Las sesiones del usuario se cerraron."}` |
| PATCH | `/users/<id>/email` | Sí (propio o admin) | `{"email"}` | `200` `{"status":"ok","user":<usuario>,"message":"Correo actualizado. Se envio un enlace…"}` |
| PATCH | `/users/<id>/role` | Sí, **admin** | `{"role_id"}` | `200` `<usuario>` |
| GET | `/roles` | Sí | — | `200` `[{"role_id":1,"nombre":"admin","descripcion":"…"},{"role_id":2,"nombre":"cliente","descripcion":"…"}]` |
| GET | `/users/internal/<id>` | `X-Internal-Key` | — | `200` `{"id_usuario":31,"nombre":"Ana Pérez Ruiz","email":"…","role_id":2,"activo":true,"email_verificado":true}` |

JWT: `common/auth.py`; el actor sale de `payload["user_id"]` y `payload["role_id"]`.

---

## 4. authors (5003)

Archivo principal: `apps/services/authors/app.py`.

Objeto autor: `{"id_autor": 5, "nombre": "…", "nacionalidad": "Mexicana", "total_libros": 3}`

| Método | Ruta | JWT | Body de entrada | Respuesta JSON de ejemplo |
|---|---|---|---|---|
| GET | `/authors?q=&nacionalidad=&page=&per_page=` | No | — | `200` `{"items":[<autor>],"page":1,"per_page":20,"total":30,"pages":2}` |
| GET | `/authors/<id>` | No | — | `200` `<autor>` |
| GET | `/authors/<id>/books` | No | — | `200` `{"id_autor":5,"enriquecido":true,"books":[{"isbn":"…","titulo":"…"}]}` (`enriquecido:false` y `titulo:null` si books no responde) |
| GET | `/authors/by-book/<isbn>` | No | — | `200` `{"isbn":"…","authors":[<autor>]}` |
| POST | `/authors` | Sí, **admin** | `{"nombre"}` (obligatorio) + opcional `"nacionalidad"` | `201` `<autor>` |
| PUT | `/authors/<id>` | Sí, **admin** | `{"nombre","nacionalidad"}` | `200` `<autor>` |
| PATCH | `/authors/<id>` | Sí, **admin** | Subconjunto | `200` `<autor>` |
| DELETE | `/authors/<id>[?force=true]` | Sí, **admin** | — | `200` `{"status":"ok","id_autor":5,"relaciones_eliminadas":0,"message":"Autor eliminado."}`. `409` si tiene libros y no hay `force` |
| POST | `/authors/<id>/books` | Sí, **admin** | `{"isbn"}` (se valida contra books) | `201` `{"id_autor":5,"isbn":"…","titulo":"…"}`. `409 RELACION_DUPLICADA` |
| DELETE | `/authors/<id>/books/<isbn>` | Sí, **admin** | — | `200` `{"status":"ok","id_autor":5,"isbn":"…","message":"Relacion eliminada."}` |

---

## 5. pedidos (5004)

Archivo principal: `apps/services/pedidos/app.py`. Tablas: `pedidos`, `pedido_lineas`, `pedido_historial`
(`sql/001_pedidos.sql`). Estados: `PENDIENTE_PAGO → PAGADO → ENVIADO → ENTREGADO`, más `CANCELADO` y
`EXPIRADO`. El stock se reserva en books al crear; un `PENDIENTE_PAGO` expira a los `RESERVA_MINUTOS`
(default 15).

Pedido completo (`_completo`):
```json
{"id": 7, "user_id": 31, "estado": "PENDIENTE_PAGO", "total": 598.0,
 "created_at": "2026-11-06T10:00:00", "updated_at": "2026-11-06T10:00:00", "expira_en": "2026-11-06T10:15:00",
 "lineas": [{"isbn": "9780000000001", "titulo": "…", "cantidad": 2, "precio_unitario": 299.0, "subtotal": 598.0}],
 "articulos": 2,
 "historial": [{"estado_anterior": null, "estado_nuevo": "PENDIENTE_PAGO", "actor": "user:31", "fecha": "2026-11-06T10:00:00"}]}
```

| Método | Ruta | JWT | Body de entrada | Respuesta JSON de ejemplo |
|---|---|---|---|---|
| POST | `/pedidos` | Sí | `{"lineas":[{"isbn":"…","cantidad":2}]}` | `201` pedido completo. `409 STOCK_INSUFICIENTE`, `404 LIBRO_NO_ENCONTRADO`, `403 USUARIO_NO_VALIDO` |
| GET | `/pedidos?estado=&user_id=&page=&per_page=` | Sí | — | `200` `{"items":[{"id":7,"user_id":31,"estado":"PAGADO","total":598.0,"created_at":"…","updated_at":"…","expira_en":"…","articulos":2}],"page":1,"per_page":20,"total":1,"pages":1}`. **Cliente: siempre solo los suyos** (`user_id` del JWT); admin: todos o filtrados |
| GET | `/pedidos/<id>` | Sí (dueño o admin) | — | `200` pedido completo. `404 PEDIDO_NO_ENCONTRADO` |
| PUT | `/pedidos/<id>` | Sí (dueño) | `{"lineas":[…]}` (reemplaza todas) | `200` pedido completo. Solo en `PENDIENTE_PAGO` (`409 PEDIDO_NO_EDITABLE`, `409 PEDIDO_EXPIRADO`) |
| PATCH | `/pedidos/<id>/lineas` | Sí (dueño) | `{"lineas":[{"isbn","cantidad"}]}` (cantidad 0 = quitar) | `200` pedido completo |
| PATCH | `/pedidos/<id>/cancelar` | Sí (dueño en `PENDIENTE_PAGO`; admin si es cancelable) | — | `200` pedido completo |
| PATCH | `/pedidos/<id>/estado` | Sí, **admin** | `{"estado": "ENVIADO"\|"ENTREGADO"}` | `200` pedido completo. `409 TRANSICION_INVALIDA` |
| DELETE | `/pedidos/<id>` | Sí, **admin** | — | `200` `{"status":"ok","id":7,"message":"Pedido eliminado."}` (solo `CANCELADO`/`EXPIRADO`) |
| GET | `/pedidos/internal/<id>` | `X-Internal-Key` | — | Pedido completo (lo usa pagos) |
| PATCH | `/pedidos/internal/<id>/estado` | `X-Internal-Key` | `{"estado": "PAGADO"\|"CANCELADO"}` | Pedido completo (lo usa pagos) |

---

## 6. pagos (5005)

Archivo principal: `apps/services/pagos/app.py`. Tabla `pagos` (`sql/001_pagos.sql`). Pago **simulado**:
la tarjeta terminada en `0000` se rechaza; el resto se aprueba. El monto sale del pedido.

Objeto pago (`publico`):
```json
{"id": 3, "pedido_id": 7, "user_id": 31, "monto": 598.0, "metodo": "TARJETA_SIMULADA",
 "estado": "APROBADO", "referencia": "PAG-20261106-1A2B3C4D", "ultimos4": "1111",
 "sincronizado": true, "notas": null, "created_at": "2026-11-06T10:05:00", "updated_at": "2026-11-06T10:05:00"}
```

| Método | Ruta | JWT | Body de entrada | Respuesta JSON de ejemplo |
|---|---|---|---|---|
| POST | `/pagos` | Sí (dueño del pedido) + header **`Idempotency-Key`** obligatorio | `{"pedido_id":7,"metodo":"TARJETA_SIMULADA","tarjeta":"4111111111111111","cvv":"123"}` o `{"pedido_id":7,"metodo":"TRANSFERENCIA"}` / `"EFECTIVO"` | `201` `<pago>` + `"repetido": false`; `200` con `"repetido": true` si se reenvía la misma llave. `409 PAGO_EN_PROCESO`, `503 PEDIDOS_NO_DISPONIBLE`, `403` si el pedido no es suyo |
| GET | `/pagos?estado=&metodo=&user_id=` | Sí | — | `200` lista paginada de `<pago>` (cliente: los suyos; admin: todos) |
| GET | `/pagos/<id>` | Sí (dueño o admin) | — | `200` `<pago>`. `404 PAGO_NO_ENCONTRADO` |
| GET | `/pagos/pedido/<pedido_id>` | Sí (dueño o admin) | — | `200` `{"pedido_id":7,"items":[<pago>]}` (más reciente primero) |
| PATCH | `/pagos/<id>` | Sí, **admin** | `{"referencia","notas"}` | `200` `<pago>` |
| POST | `/pagos/<id>/reembolso` | Sí, **admin** | Opcional `{"notas"}` | `200` `<pago>` con `estado: "REEMBOLSADO"` (el pedido pasa a `CANCELADO`). `409 PEDIDO_NO_CANCELABLE` si ya está `ENVIADO`/`ENTREGADO` |
| DELETE | `/pagos/<id>` | Sí, **admin** | — | `200` borrado lógico; solo pagos `RECHAZADO` |

---

## 7. tracking (5900)

Archivo principal: `apps/services/tracking/app.py` (copiado de "Monterrey GPS Tracker").
Flask + Flask-Sock, **sin JWT, sin BD, sin `common/`**. Estado en memoria: últimas 50 posiciones por
vehículo; inactivo tras 15 s sin datos y se olvida tras 600 s. En la VM: 1 worker con hilos
(`deploy/tracking.service`, `VMComandos.md` §23).

| Método | Ruta | JWT | Entrada | Salida |
|---|---|---|---|---|
| GET | `/health` | No | — | `200` `{"status":"ok","vehicles":3,"active_vehicles":2,"map_clients":1}` |
| WS | `/ws?role=gps` | No | Cada mensaje: `{"vehicle_id":"V001","latitude":25.67,"longitude":-100.31,"speed":50,"heading":90}` (exactamente esos 5 campos) | `{"type":"ack"}` o `{"type":"error","detail":"…"}`. La conexión queda ligada al `vehicle_id` del primer mensaje válido |
| WS | `/ws?role=map` | No | Opcional: `{"type":"config","max_vehicles":10,"interval":1.0}` | Al conectar: `{"type":"snapshot","vehicles":[…]}`; luego `{"type":"update","vehicles":[{"vehicle_id":"V001","latitude":25.67,"longitude":-100.31,"speed":50,"heading":90,"received_at":"2026-11-06T16:00:00.123+00:00","active":true}]}` solo cuando hay cambios |
| cualquier otra | — | — | — | `404/405` `{"error":"solo existen /ws y /health"}` |

---

## SOAP (books, `POST /soap` en 5001)

Contrato: `library_soap_service/wsdl/library-classifier.wsdl`. SOAP 1.1, `Content-Type: text/xml`.
Errores como `soap:Fault` con `detail/codigo` y `detail/mensaje`.

| Operación (elemento del Body) | Seguridad | Parámetros | Respuesta |
|---|---|---|---|
| `ObtenerConceptosPendientesRequest` | Ninguna | `correoClasificador` | `ObtenerConceptosPendientesResponse` → lista `conceptoPendiente` (`isbn, tituloLibro, idConcepto, nombreConcepto, definicion, nombreGenero`) |
| `RegistrarClasificacionRequest` | Ninguna | `nombre, apellidos, correo, isbn, idConcepto, modeloCloud (IaaS/PaaS/SaaS/FaaS), tipoCliente, identificadorCliente` | `idClasificacion, fechaClasificacion, mensaje` |
| `ObtenerProgresoUsuarioRequest` | Ninguna | `correoClasificador` | `correo, totalClasificados, totalPendientes` |
| `ObtenerEstadisticasPorModeloRequest` | **WS-Security UsernameToken** en `soap:Header` (`WS_SECURITY_USER` / `WS_SECURITY_PASSWORD_HASH`) | — | `IaaS, PaaS, SaaS, FaaS` (conteos) |

No usa JWT. No existe ruta `GET /soap?wsdl`: el WSDL se lee del archivo del repo.

---

## Limitaciones detectadas

**¿pedidos permite crear un pedido y listar los pedidos de un usuario?**
Sí. `POST /pedidos` con `{"lineas":[{"isbn","cantidad"}]}` crea el pedido y reserva stock en books.
`GET /pedidos` devuelve los del usuario del JWT (paginado; filtro `?estado=`). Un admin puede filtrar
cualquier usuario con `?user_id=`. El detalle con líneas e historial está en `GET /pedidos/<id>`.
No guarda dirección de envío ni datos de entrega.

**¿pagos permite registrar un pago simulado y consultar su estado?**
Sí. `POST /pagos` (con header `Idempotency-Key` obligatorio) registra un pago simulado `TARJETA_SIMULADA`
(rechazado si la tarjeta termina en `0000`), `TRANSFERENCIA` o `EFECTIVO`. El estado
(`APROBADO`/`RECHAZADO`/`REEMBOLSADO`) se consulta con `GET /pagos/<id>` o `GET /pagos/pedido/<pedido_id>`.
Un pago aprobado pasa el pedido a `PAGADO`; el campo `sincronizado` indica si pedidos ya se enteró.

**¿Existe algún campo o tabla para guardar un código de rastreo?**
No. Ni `pedidos`, ni `pedido_lineas`, ni `pedido_historial`, ni `pagos` tienen un campo de rastreo,
guía o `vehicle_id`. Lo más cercano es `pagos.referencia` (`PAG-AAAAMMDD-XXXXXXXX`), que es del pago,
no del envío. Los estados `ENVIADO`/`ENTREGADO` los cambia el admin con `PATCH /pedidos/<id>/estado`,
que solo recibe `{"estado"}`. Para ligar un pedido con un camión del tracking hace falta una columna
nueva (por ejemplo `pedidos.codigo_rastreo` o `vehicle_id`), una migración y un endpoint: no existe hoy.

**¿books devuelve portada, descripción, precio, ISBN y disponibilidad?**
Parcialmente:
- ISBN: sí (`isbn`).
- Precio: sí (`precio`, número).
- Portada: sí (`portada` / `image_url`, URL de la imagen principal en la tabla `imagenes`; puede ser `null`).
- Disponibilidad: no hay un campo booleano, pero sí `stock` (entero); disponible ⇔ `stock > 0`.
- Descripción: **no**. La tabla `libros` no tiene columna de descripción o sinopsis, y ningún endpoint la devuelve.

Además, `GET /books/<isbn>` en JSON **no** trae `autor` ni `genero` (solo `GET /books` los trae), y
ambos responden XML si no se manda `?format=json`.

**¿tracking valida JWT o asocia cada simulación a un pedido?**
No a ambas. `/ws` y `/health` son públicos (cualquiera puede mandar posiciones o ver la flota), y el
mensaje solo admite `vehicle_id, latitude, longitude, speed, heading`: un campo extra (por ejemplo
`pedido_id`) se rechaza con `error`. No usa `common/auth.py`, no tiene `JWT_SECRET_KEY` y no habla con
pedidos. Todo vive en memoria y se pierde al reiniciar.

**¿Existe algún endpoint SOAP en el monorepo?**
Sí, uno: `POST /soap` en books (`library_soap_service`, puerto 5001), con 4 operaciones del WSDL
`library-classifier.wsdl` (clasificación de conceptos de libros en modelos Cloud). Solo
`ObtenerEstadisticasPorModelo` pide autenticación (WS-Security, no JWT). No hay endpoints SOAP de
pedidos, pagos ni tracking.

Otras observaciones para el cliente Java:
- login y books responden **XML por defecto**: siempre manda `?format=json`.
- Los formatos de error no son uniformes: login usa `{"status":"error","code","message"}`, books REST
  `{"error","mensaje"}` y el resto `{"error","message"}`.
- El JWT dura 20 min: renuévalo con `POST /refresh` usando el `refresh_token`.
- CORS solo aplica a navegadores; a una app JavaFX no le afecta.
