Proyecto Library (monorepo WebMonolitoAPI). Ya está completa la PARTE 1 (ambiente base). Antes de empezar, lee docs/ARQUITECTURA.md, apps/services/common y la estructura de apps/services/login. Usa el módulo común para autenticación, Redis, health, métricas, errores y logs. No modifiques otros servicios salvo lo indicado.

No tienes acceso a la VM. Solo trabaja sobre el código del repositorio. Todo lo que se deba ejecutar en la VM (migraciones, scripts, systemd, pruebas con curl) entrégamelo como comandos para que yo los corra y te comparta el resultado.

ESTA ES LA PARTE 2: microservicio users (apps/services/users, puerto 5002) y su pantalla en la app Tk.

Responsabilidad: administrar usuarios, roles, correos y contraseñas. Login se queda solo con la autenticación (login, refresh, logout y confirmación de correo).

Base de datos:
- Reutiliza la tabla de usuarios de login (NO la dupliques). Primero lee su esquema actual y muéstrame qué columnas tiene.
- Si una columna ya existe con otro nombre (por ejemplo password en lugar de password_hash, o username en lugar de nombre), usa la existente y NO crees una nueva ni la renombres.
- Agrega solo lo que realmente falte, con ALTER TABLE ... ADD COLUMN IF NOT EXISTS: role_id (FK a roles, default 2) si la Parte 1 no la agregó, activo (default true) y email_verificado, created_at y updated_at si no existen.
- No borres ni modifiques columnas o datos existentes.
- Hashea las contraseñas con EXACTAMENTE el mismo algoritmo que usa login.

Usuario admin inicial:
- Ya existe un admin real creado por el monolito: admin@libreria.com en la tabla usuarios (columna correo). Revisa apps/WebMonolito/data/libreria_schema.sql para identificar la columna booleana que marca a los administradores.
- En la migración, asigna role_id = 1 a todos los usuarios que tengan esa columna en TRUE y role_id = 2 al resto. No borres esa columna, porque el monolito la sigue usando; mantenlas sincronizadas cuando users cambie el rol.
- Variables en el .env de users: ADMIN_EMAIL=admin@libreria.com y ADMIN_PASSWORD (en .env.example solo un valor de ejemplo, nunca la contraseña real).
- Script apps/services/users/scripts/crear_admin.py que yo ejecuto una sola vez en la VM, después de las migraciones:
  - Asigna role_id = 1 y activo = true a ADMIN_EMAIL.
  - Si su password_hash sigue siendo un valor de ejemplo ('hash_de_ejemplo' o 'CAMBIAR_POR_HASH_BCRYPT_REAL'), lo reemplaza por el hash de ADMIN_PASSWORD con el mismo algoritmo que usa login (bcrypt). Si ya tiene un hash real, no lo toca.
  - Es idempotente y no imprime la contraseña en consola ni en logs.
- Dame el comando para ejecutarlo y una consulta SQL para verificar el role_id de admin@libreria.com y de maruchanvalo@gmail.com (que debe quedar como cliente, role_id = 2).

Endpoints:
- GET /users (JWT + admin): paginado, con filtros ?q=&role_id=&activo=
- GET /users/me (JWT)
- GET /users/{id} (JWT: admin o el mismo usuario)
- POST /users (JWT + admin)
- PUT /users/{id} y PATCH /users/{id} (JWT: admin o el mismo usuario; solo admin cambia activo y role_id)
- DELETE /users/{id} (JWT + admin): baja lógica (activo=false)
- PATCH /users/{id}/password (JWT): el usuario envía su contraseña actual; el admin puede restablecerla sin ella
- PATCH /users/{id}/email (JWT): valida el formato y el registro MX con la misma lógica de login, marca email_verificado=false y reutiliza la confirmación de correo de login
- PATCH /users/{id}/role (JWT + admin)
- GET /roles (JWT)
- GET /users/internal/{id} (X-Internal-Key): datos mínimos para pedidos y pagos

Redis:
- Al cambiar contraseña, desactivar al usuario o cambiarle el rol: borrar sus sesiones y refresh tokens (usando user:sessions:<user_id>) y revocar sus jti vigentes en jwt:revoked:<jti>.
- Si Redis falla, responder 503 sin aplicar el cambio (revocar primero y luego hacer commit, o rollback).

Reglas:
- No permitir que el último admin cambie su propio rol ni se desactive.
- Nunca devolver password_hash.

App Tk, pantalla Usuarios (diseño de administración, distinto a las demás pantallas):
- Admin: tabla con búsqueda, filtros por rol y estado, y paginación; formulario para crear y editar; botones para desactivar, cambiar rol, restablecer contraseña y cambiar correo; confirmación antes de cualquier acción destructiva.
- Cliente: solo "Mi perfil", donde puede editar su nombre, cambiar su contraseña (pidiendo la actual) y cambiar su correo.
- Si el semáforo de users está en rojo, deshabilitar la pantalla con un aviso.

Pruebas con pytest: CRUD, permisos (401 y 403), revocación de sesiones al cambiar contraseña o rol, regla del último admin, Redis caído, idempotencia de crear_admin.py.

Comprobación de la Parte 2 (dame los comandos curl y los pasos en la app Tk):
- Ejecutar crear_admin.py, hacer login con admin@libreria.com y confirmar que el JWT trae role_id = 1.
- Hacer login con maruchanvalo@gmail.com y confirmar que el JWT trae role_id = 2.
- Crear un usuario como admin y hacer login con él.
- Un cliente recibe 403 en GET /users.
- Después de cambiarle la contraseña a un usuario, su token anterior recibe 401.
- Actualiza docs/ARQUITECTURA.md con los endpoints nuevos.