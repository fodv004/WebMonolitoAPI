En el proyecto Library, agregar Redis. Redis debe incorporarse como una capa compartida para almacenar sesiones y refresh tokens, aplicar revocación de JWT, cachear consultas públicas del catálogo y coordinar tareas temporales, manteniendo PostgreSQL como fuente principal de datos; todos los microservicios deben conectarse mediante una URL común protegida y usar tiempos de expiración coherentes.


- Añade Redis al despliegue y configura REDIS_URL=redis://:password@host:6379/0 en login, books, users, autores, pedidos y pagos.

- En login, guarda la sesión y el refresh token en Redis con TTL; conserva el JWT de acceso con expiración de 20 minutos y elimina ambos al ejecutar /logout.
Implementa una lista de revocación en Redis usando jti como clave (jwt:revoked:<jti>) y verifica esa clave en cada servicio antes de aceptar un JWT.

- Cachea GET /books y GET /books/{isbn} con claves como books:list:<filtros> y books:<isbn>, usando TTL corto; invalida esas claves después de cualquier POST, PUT, PATCH o DELETE.

- Añade manejo de desconexión, timeouts, autenticación Redis, métricas y pruebas; Redis debe ser opcional para lecturas cacheadas, pero las operaciones de sesión, revocación y autorización deben fallar de forma segura si Redis no está disponible.

Para esta actividad tambien tendrás que desarrollar 4 microservicios que serán los siguientes:

1- Users: microservicio que administre usuarios, roles, correos y contraseñas.

2- Authors: microservicio que administra autores y sus relaciones con libros.

3- Pedidos: microservicio que crea y gestiona pedidos, líneas de pedido, stock y estados.

4- Pagos: microservicio que registra pagos y actualiza el estado de los pedidos.

Toma en cuenta que estos microservicios deberán de estar dissponibles para la aplicación de Python TK, en la que la aplicación consumira todas la APIS en donde se tiene que tener un semaforo de cada microservicio (Rojo no funcional, verde funcional).

Verifica que login valide credenciales y emite un JWT firmado con SECRET_KEY, algoritmo HS256 y expiración de 20 minutos. Debe renovarse antes de caducar.

* Users, Authors, Pedidos y Pagos: todas las operaciones POST, PUT, PATCH y DELETE deben exigir: Authorization: Bearer <JWT>
* Lecturas GET: pueden mantenerse públicas si solo consultan información; las lecturas administrativas deberían exigir JWT y permisos.
* Validación: cada servicio debe verificar firma, algoritmo, expiración y claims del token antes de modificar datos.
* Secretos: todos los servicios deben compartir JWT_SECRET_KEY, configurada mediante variables de entorno, nunca escrita directamente en el código.
* Roles: el JWT debe incluir user_id y role_id; las operaciones administrativas deben comprobar que el usuario tenga rol autorizado.
* CORS: permitir únicamente los orígenes de las aplicaciones cliente en producción.
* Seguridad adicional: usar HTTPS, no guardar contraseñas ni tokens en logs y devolver 401 para tokens ausentes o inválidos y 403 para roles insuficientes.

Realiza las modificaciones pertinentes en la aplicacion Python TK para hacer uso de todos los microservicios desarrollados con sus semáforos y formularios necesarios. El sistema ya debe de estar completo y debe de permitir hacer operaciones CRUD en todos los microservicios.


Tiene que tener el CRUD como se mencionar por completo, haz una pantalla si es posible para cada microservicio para que exista una clara diferencia (especialmente para usuarios, pedidos y pagos).

Tambien para la implementación de más seguridad tiene que tener por default las peticiones por http. La opción de https tiene qeu estar dentro de configuración en donde el usuario peude realizar este cambio.

=====================================================================
IMPORTANTE: este proyecto se implementa en 6 partes. ESTA ES LA PARTE 1.
Lo anterior es el contexto general. En esta parte SOLO se construye el
ambiente base funcional para todos los microservicios. NO implementes
todavía la lógica de negocio de users, authors, pedidos ni pagos.
No tienes acceso a la VM. Solo trabaja sobre el código del repositorio. Todo lo que se deba ejecutar en la VM (migraciones, systemd, Redis, nginx, pruebas con curl) entrégamelo como comandos o scripts para que yo los corra y te comparta el resultado en un archivo llamado VMComandos.md.
=====================================================================

----- Arquitectura -------

- Repositorio: monorepo WebMonolitoAPI. Los microservicios viven en apps/services/<nombre>. Ya existen apps/services/login (puerto 5000) y el servicio de libros apps/services/library_soap_service (puerto 5001). La app de escritorio está en apps/Python_app (Tkinter) y corre en la máquina local del alumno. Los microservicios corren en la VM de GCP (maquina-01, CentOS Stream 10).
- NO modifiques ni elimines apps/WebMonolito ni el servicio SOAP. Antes de escribir código, lee la estructura actual de login y books y replica sus convenciones.
- Stack: Python 3 + Flask + psycopg + PostgreSQL (base library_db, usuario library_user, localhost:5432) + redis-py + PyJWT + flask-cors + gunicorn.
- Puertos:
  - login: 5000
  - books: 5001
  - users: 5002
  - authors: 5003
  - pedidos: 5004
  - pagos: 5005
  - Redis: 6379, solo en 127.0.0.1
- Cada servicio es dueño de sus propias tablas. Ningún servicio escribe en las tablas de otro; si necesita datos de otro servicio, los pide por HTTP con timeout de 3 segundos. Las llamadas internas usan el header X-Internal-Key.

TTL del sistema:
- JWT de acceso: 20 minutos (renovación proactiva a los 17 minutos).
- session:<session_id> y refresh:<token_hash>: 7 días.
- jwt:revoked:<jti>: el tiempo restante de vida del JWT.
- Caché de catálogo: 60 segundos.
- Reserva de stock: 15 minutos.
- Idempotencia de pagos: 24 horas.
- Locks: 30 segundos.

----- Tareas de la Parte 1 -------

1. Redis en la VM (YA ESTÁ INSTALADO; no tienes acceso a la VM, así que no lo instales ni intentes verificarlo tú)
   - Dame los comandos para que yo verifique en la VM que Redis está activo (systemctl status redis o valkey) y que responde PONG con redis-cli usando la contraseña.
   - Dame los comandos para revisar en su configuración que tenga bind 127.0.0.1, protected-mode yes y requirepass, y qué cambiar si falta algo.
   - En el .env.example de cada servicio deja REDIS_URL=redis://:password@127.0.0.1:6379/0 como plantilla para que yo ponga la contraseña real.
   - Documenta todo eso en docs/REDIS.md, sin incluir contraseñas reales.

2. Módulo común apps/services/common (o copia idéntica en cada servicio si la estructura del repo no permite compartir código). Debe incluir:
   - config.py: lee variables de entorno (PORT, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY, JWT_ALGORITHM=HS256, ACCESS_TOKEN_MINUTES=20, CORS_ALLOWED_ORIGINS, INTERNAL_API_KEY, BOOKS_URL, USERS_URL, AUTHORS_URL, PEDIDOS_URL, PAGOS_URL). Si falta JWT_SECRET_KEY, el servicio no arranca y muestra un error claro.
   - redis_client.py: socket_timeout y socket_connect_timeout de 2 segundos, ping, cache_get, cache_set e invalidación por patrón con SCAN (nunca KEYS). Si Redis falla en una lectura de caché, se registra en el log y se continúa con PostgreSQL.
   - auth.py: validación del JWT en este orden:
     1. Sin header Bearer → 401.
     2. jwt.decode con algorithms=["HS256"] fijo, verificando firma y expiración → si falla, 401.
     3. Faltan claims (sub, user_id, role_id, jti, iat, exp, type="access") → 401.
     4. Existe jwt:revoked:<jti> → 401. Redis caído → 503.
     5. Rol insuficiente → 403.
     Exponer @require_auth, @require_role(ADMIN_ROLE_ID) y @require_internal_key. Los roles son 1 = admin y 2 = cliente.
   - health.py: GET /health público con respuesta {"service", "status", "db", "redis", "version"}; HTTP 200 solo si DB y Redis están bien, 503 si no.
   - metrics.py: GET /metrics con peticiones, errores 4xx/5xx, 401, 403, cache hits y misses, errores de Redis.
   - errors.py: formato uniforme {"error": "<codigo>", "message": "<texto>"}.
   - logging: log HTTP en consola (método, ruta, status, tiempo) con un filtro que oculte Authorization, password, password_actual, password_nueva, refresh_token, token y tarjeta.
   - CORS con flask-cors, usando solo la lista de CORS_ALLOWED_ORIGINS, nunca "*".

3. Login (puerto 5000)
   - Leer JWT_SECRET_KEY; si no existe, usar SECRET_KEY solo como respaldo de compatibilidad.
   - Emitir el JWT con los claims sub, user_id, role_id, role, jti, iat, exp (20 minutos) y type="access".
   - Migración idempotente: crear la tabla roles (1 = admin, 2 = cliente) y agregar role_id (FK, default 2) a la tabla de usuarios existente. Esta migración vive en apps/services/users/sql/001_roles.sql porque users será el dueño de la tabla, pero se ejecuta en esta parte. Crear o actualizar un usuario admin inicial con datos tomados de variables de entorno.
   - Guardar en Redis: session:<session_id>, refresh:<hash del refresh token> y el set user:sessions:<user_id>, incluyendo el jti vigente en la sesión.
   - POST /refresh: valida el refresh token en Redis, emite un JWT nuevo y rota el refresh token.
   - POST /logout: borra la sesión y el refresh token, y agrega jwt:revoked:<jti> con TTL igual a la vida restante del token.
   - Si Redis no está disponible, login, refresh y logout devuelven 503.
   - Agregar /health y /metrics con el módulo común.

4. Books (puerto 5001)
   - Usar el módulo común de autenticación: POST, PUT, PATCH y DELETE con JWT + admin.
   - Caché de GET /books (books:list:<filtros normalizados>) y GET /books/{isbn} (books:<isbn>) con TTL de 60 segundos, invalidada en cada escritura.
   - Agregar /health y /metrics.

5. Esqueleto de los 4 servicios nuevos: users (5002), authors (5003), pedidos (5004) y pagos (5005). Cada uno con:
   - app.py funcional que ya exponga /health y /metrics.
   - Carpetas config/, db/, routes/, services/, sql/ y tests/.
   - .env.example, requirements.txt, README.md.
   - deploy/<nombre>.service (systemd con gunicorn en 0.0.0.0:<puerto>).
   - Sin endpoints de negocio todavía.

6. Script scripts/levantar_servicios.sh que instale dependencias, ejecute las migraciones y active y reinicie las 6 unidades systemd, y scripts/estado_servicios.sh que muestre systemctl status y haga curl a cada /health.

7. App Python TK (apps/Python_app), sin romper lo que ya funciona de login, libros, PATCH y logs HTTP:
   - Estructura: api/ (cliente HTTP base y un cliente por servicio), screens/, widgets/, config/ y session.py.
   - Cliente HTTP base:
     - Protocolo HTTP por default (http://<IP>:<puerto>). Si se elige HTTPS, https://<IP>/api/<servicio>.
     - Timeout de 5 segundos y header Authorization automático.
     - Logs HTTP en consola sin tokens ni contraseñas.
     - Mensajes claros para 401, 403, 409 y 503.
   - Sesión: token y refresh token solo en memoria; renovación automática a los 17 minutos; ante un 401, un intento de refresh y, si falla, regreso al login.
   - Ventana principal con menú lateral (Inicio, Libros, Autores, Usuarios, Pedidos, Pagos, Configuración, Cerrar sesión). En esta parte, las pantallas de Autores, Usuarios, Pedidos y Pagos muestran "En construcción".
   - Panel de semáforos siempre visible con los 6 servicios. Verde si /health devuelve 200 con status "ok"; rojo en cualquier otro caso. Revisión cada 10 segundos con hilos y root.after() (la ventana nunca se congela), botón "Revisar ahora" y detalle al pasar el mouse (db, redis, tiempo de respuesta, última revisión).
   - Pantalla Configuración:
     - IP de la VM, puerto de cada servicio y protocolo con radio buttons HTTP (default) / HTTPS.
     - Si se elige HTTPS: casilla "Verificar certificado" y selector del archivo .crt, con advertencia visible si se desactiva la verificación.
     - Intervalo y timeout del semáforo.
     - Botones "Probar conexión" y "Restaurar valores por defecto".
     - Se guarda en config.json, sin tokens, y se aplica sin reiniciar la app.

8. Documentación docs/ARQUITECTURA.md con: servicios y puertos, estructura de carpetas, convenciones del módulo común, claims del JWT, roles, claves de Redis con su TTL, variables de entorno y cómo agregar un servicio nuevo. Las siguientes partes del proyecto van a leer este archivo.

9. Pruebas con pytest y fakeredis del módulo común y de login: 401 sin token, mal firmado, con algoritmo distinto, expirado, sin claims o revocado; 403 por rol; 503 con Redis caído; refresh con rotación; logout con revocación; el filtro de logs.

----- Comprobación de la Parte 1 -------

Al terminar, dame la lista de comandos para comprobar que:
- redis-cli (o valkey-cli) con contraseña responde PONG.
- Los 6 servicios están activos y cada GET /health devuelve 200.
- Login devuelve un JWT con user_id y role_id, /refresh lo renueva y, después de /logout, el token anterior recibe 401 en books.
- Books cachea (un cache hit visible en /metrics) y las escrituras sin token dan 401.
- La app Tk muestra los 6 semáforos en verde, y al detener un servicio con systemctl stop su semáforo cambia a rojo.
- Pytest pasa completo.