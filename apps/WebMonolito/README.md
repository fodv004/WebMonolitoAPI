# Librería web monolítica

Aplicación Node.js monolítica con MVC, Express, EJS y acceso directo a PostgreSQL mediante `pg`. Todas las interacciones son páginas HTML renderizadas en el servidor y formularios `POST`; no contiene API REST, GraphQL, SOAP ni usa JSON/XML como intercambio de datos.

## Alcance

- Registro e inicio de sesión **delegados en el microservicio de auth** (`apps/services/login`, ver más abajo) y administración de usuarios. Las contraseñas se almacenan con bcrypt.
- CRUD de `formatos`, `generos`, `autores`, `conceptos`, `usuarios` y `libros`.
- Administración de las relaciones `libro_autor`, `libro_genero` y `libro_concepto` desde el formulario y detalle del libro.
- Carga local de imágenes o registro de URL para `imagenes`; la opción principal respeta la restricción de una portada por libro.
- La regla de máximo un administrador se impone en PostgreSQL por el índice parcial `un_solo_admin`.

## Dependencias funcionales y multivaluadas

| Tipo | Dependencia | Implementación |
|---|---|---|
| Funcional | `ISBN → título, año, precio, stock, formato` | `libros` |
| Funcional | `id_formato → nombre`, `id_genero → nombre`, `id_autor → nombre, nacionalidad`, `id_concepto → nombre` | Catálogos independientes |
| Funcional | `(ISBN, id_concepto) → definición` | `libro_concepto` |
| Multivaluada | `ISBN ↠ autores`, `ISBN ↠ géneros`, `ISBN ↠ conceptos`, `ISBN ↠ imágenes` | Tablas de unión y `imagenes` independientes |

Esto conserva 4NF: autores, géneros, conceptos e imágenes no se repiten como grupos dentro de `libros`.

## Usuarios: nombre atómico (1FN) y estado de la cuenta

La tabla `usuarios` guarda `nombre`, `apellido_paterno` y `apellido_materno` en columnas separadas, y `estado_cuenta` (`pendiente` / `confirmado`). El registro y el alta de usuarios del monolito piden los tres campos; solo las cuentas `confirmado` pueden iniciar sesión.

- **Instalación desde cero:** `db/01_schema.sql` ya crea la estructura nueva (y registra la migración 001 en `schema_migraciones`).
- **Base de datos existente:** ejecutar **una vez** `db/cambio_usuarios.sql` (transaccional e idempotente; migra los nombres sin perder datos y verifica el resultado antes de confirmar). Debe correr antes de desplegar esta versión del monolito y antes de levantar el microservicio de auth (`apps/services/login`), que comparte la tabla.
- El registro público del monolito (`/registro`) ya no inserta en PostgreSQL: hace `POST /register` al microservicio de auth y la cuenta nace `pendiente` hasta abrir el link que llega a Mailpit. Las altas hechas por el administrador en **Usuarios** (CRUD directo a PostgreSQL) nacen `confirmado`, porque no envían correo.
- Los usuarios migrados pueden quedar sin apellido materno; el administrador lo completa desde **Usuarios → Editar**.

Ver `INSTRUCCIONES.txt` (raíz del repositorio) para el orden completo de ejecución.

## Despliegue en CentOS Stream 10

1. Instala Node.js y las herramientas de compilación necesarias para `bcrypt`:

   ```bash
   sudo dnf install -y nodejs npm gcc-c++ make
   ```

2. Copia el directorio `apps/web-monolito` al servidor y entra a él:

   ```bash
   cd /ruta/a/web-monolito
   cp .env.example .env
   npm install
   ```

3. Con PostgreSQL ya instalado, importa el esquema con el usuario, contraseña y base indicados. El archivo incluye tablas, índices y datos iniciales:

   ```bash
   PGPASSWORD=666 psql -h localhost -U library_user -d library_db -f data/libreria_schema.sql
   ```

4. Edita `.env` solo si la instancia de PostgreSQL no usa `localhost:5432`. Los valores predeterminados ya son `library_user`, `666` y `library_db`.

5. Inicia la aplicación:

   ```bash
   npm start
   ```

   Abre `http://IP_DEL_SERVIDOR:3000`. Si usas firewalld: `sudo firewall-cmd --permanent --add-port=3000/tcp && sudo firewall-cmd --reload`.

El dato de ejemplo del esquema usa un hash ilustrativo. Para que el primer administrador pueda iniciar sesión con una contraseña real, reemplázala por un hash bcrypt generado localmente (por ejemplo con `node -e "require('bcrypt').hash('UnaClaveSegura',12).then(console.log)"`) y ejecuta `UPDATE usuarios SET password_hash='HASH_GENERADO' WHERE correo='admin@libreria.com';`.

## Registro y login delegados en el microservicio de auth

`POST /registro` y `POST /login` del monolito llaman con `fetch` (Node ≥ 18) a `POST /register?format=json` y `POST /login?format=json` del microservicio (`src/services/authClient.js`). El monolito muestra tal cual el mensaje de éxito o de error que responde el servicio (400 datos inválidos, 409 correo duplicado, 401/403 credenciales o cuenta sin confirmar) y, si el servicio no responde, un aviso 503. Tras un login correcto mantiene su propia sesión de Express.  

- Variable: `AUTH_SERVICE_URL` (por defecto `http://localhost:5000`) y opcional `AUTH_SERVICE_TIMEOUT_MS`. El servicio de auth debe estar en marcha antes de usar `/registro` o `/login`.
- El servicio solo acepta contraseñas con hash bcrypt. Las cuentas de demo del seed (`demo1234`, en texto plano) y el marcador del administrador dejan de poder entrar hasta ejecutar **una vez** `node scripts/hashear_passwords_legacy.js` (convierte a bcrypt las contraseñas en texto plano, conservando su valor) y asignar una contraseña real al administrador con el `UPDATE` que indica el script (ver el comando `node -e` de arriba).

## Estructura

`src/models` accede directamente a PostgreSQL, `src/controllers` contiene la lógica de casos de uso, `src/routes` concentra rutas web y `src/views` son vistas EJS. Es un único proceso desplegable, por lo que implementa la macro-arquitectura de monolito modular.
