# Microservicio de autenticación (`apps/services/login`)

Servicio independiente de registro, login y sesión para la librería en línea.
Python 3.12 · Flask · psycopg2 · PostgreSQL (base `library`) · Mailpit (SMTP) · Swagger (flasgger).
Puerto **5000**. Todas las respuestas son **XML por defecto** o **JSON** con `?format=json`.

> Guía completa de instalación y verificación de todos los servicios: [`INSTRUCCIONES.txt`](../../../INSTRUCCIONES.txt) en la raíz del repositorio.

## Endpoints

| Método | Endpoint | Función |
|---|---|---|
| POST | `/register` | Registra un usuario (`pendiente`) y envía el correo de confirmación por Mailpit |
| POST | `/login` | Verifica credenciales contra PostgreSQL y abre la sesión de Flask |
| POST | `/logout` | Cierra la sesión (idempotente) |
| GET | `/session` | Indica si hay una sesión autenticada (`authenticated: true/false`) |
| GET | `/health` | Estado del servicio y de PostgreSQL (200 / 503) |
| GET | `/confirm?token=...` | Confirma la cuenta (`pendiente` → `confirmado`) y redirige a `/confirmed` |
| GET | `/confirmed?status=...` | Página HTML que confirma visualmente el resultado |
| GET | `/apidocs/` | Swagger UI (spec en `/apispec_1.json`) |

`?format=xml` equivale a omitir el parámetro; `?format=json` responde JSON; cualquier otro valor → `400 FORMATO_INVALIDO`.
Los errores usan el mismo sobre que los éxitos:

```json
{"status": "error", "code": "EMAIL_DUPLICADO", "message": "Ya existe una cuenta registrada con ese email."}
```
```xml
<response><status>error</status><code>EMAIL_DUPLICADO</code><message>Ya existe una cuenta registrada con ese email.</message></response>
```

`POST /register` recibe `nombre`, `apellido_paterno`, `apellido_materno`, `email` y `password` (JSON o formulario).
`/confirm` **redirige** a `/confirmed`; si se le pasa `format` explícito responde el resultado en ese formato en lugar de redirigir.

## Ejecución rápida

```bash
cd apps/services/login
python -m venv .venv
.venv\Scripts\activate            # Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # Windows: copy .env.example .env  (y edita SECRET_KEY)
python app.py                     # http://localhost:5000  ->  /apidocs/
```

Antes de arrancar deben existir (ver `INSTRUCCIONES.txt`): la migración `WebMonolito/db/cambio_usuarios.sql`,
`sql/auth_module.sql`, `sql/auth_roles.sql` y Mailpit escuchando en `localhost:1025`.

Validación automática de todos los endpoints (servicio + PostgreSQL + Mailpit en marcha):

```bash
python tests/validar_endpoints.py          # 61 comprobaciones
```

## Decisiones de diseño

- **Contraseña solo como hash, en `usuarios.password_hash`.** No hay tabla de passwords. Se usa **bcrypt (12 rondas)**, el mismo formato que el monolito Node, así una cuenta creada en un servicio inicia sesión en el otro. Las contraseñas en texto plano del seed de demo (`demo1234`) **no** se aceptan aquí.
- **Token de confirmación**: 256 bits aleatorios, de un solo uso, vigencia `CONFIRM_TOKEN_HOURS` (24 h). En BD (`tokens_confirmacion`) solo se guarda su SHA-256.
- **Registro atómico con el correo**: usuario + token + envío SMTP van en una transacción; si Mailpit no responde se devuelve `503 CORREO_NO_ENVIADO` y **no** queda un usuario a medias (se puede reintentar con el mismo email).
- **Sesión**: cookie firmada de Flask llamada `auth_session` (`HttpOnly`, `SameSite=Lax`), distinta de `connect.sid` del monolito para que no choquen aunque compartan host. `/session` revalida contra la BD (cuenta activa y confirmada).
- **Login**: mismo error (`401 CREDENCIALES_INVALIDAS`) para email desconocido y password incorrecto (con tiempo equivalente). Solo con la contraseña correcta se informa `403 CUENTA_NO_CONFIRMADA` / `CUENTA_INACTIVA`.
- **Mínimo privilegio**: el servicio usa el rol `auth_user`, que solo puede leer/insertar en `usuarios`, actualizar **únicamente** `usuarios.estado_cuenta` y operar `tokens_confirmacion`. No tiene acceso a `libros` ni a las tablas del servicio SOAP/books.
- **Sin choque con otros servicios**: rutas propias (`/register /login /logout /session /health /confirm /confirmed`), distintas de `/books`, `/books/<isbn>`, `/books/gallery`, `/cloud-concepts`, `/soap` (servicio de libros, 5001) y de las rutas del monolito (3000).

## Estructura

```
app.py            fábrica de la app, Swagger, manejadores de error, puerto 5000
routes.py         endpoints + documentación Swagger (docstrings YAML)
responses.py      negociación ?format= y serialización XML/JSON
validators.py     validación de registro/login (email, nombres, password)
security.py       bcrypt y tokens
mailer.py         correo de confirmación por SMTP (Mailpit)
db.py, config.py  conexión a PostgreSQL y variables de entorno
templates/        confirmed.html
sql/              auth_module.sql (tabla de tokens), auth_roles.sql (rol auth_user)
tests/            validar_endpoints.py
```

## Limitaciones conocidas

- No hay límite de intentos de login (rate limiting); si el servicio se expone a internet conviene ponerlo detrás de un proxy que lo aplique.
- El servidor de `python app.py` es el de desarrollo de Flask; para producción usar un servidor WSGI (p. ej. gunicorn en Linux).
- No hay endpoint para reenviar el correo de confirmación ni para recuperar contraseña (fuera del alcance solicitado).
