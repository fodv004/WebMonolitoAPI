# Librería web monolítica

Aplicación Node.js monolítica con MVC, Express, EJS y acceso directo a PostgreSQL mediante `pg`. Todas las interacciones son páginas HTML renderizadas en el servidor y formularios `POST`; no contiene API REST, GraphQL, SOAP ni usa JSON/XML como intercambio de datos.

## Alcance

- Registro, inicio de sesión y administración de usuarios. Las contraseñas se almacenan con bcrypt.
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

El login detecta si `password_hash` tiene formato bcrypt (`$2a$`/`$2b$`/`$2y$`); si no lo tiene, compara la contraseña en texto plano. Esto permite que el usuario de prueba `demo@libreria.com` / `demo1234` (incluido en el esquema, sin hashear) entre directamente a la pantalla principal y de búsqueda sin pasos adicionales. Es solo para pruebas/demo: cualquier cuenta real debe guardarse siempre con `password_hash` generado por bcrypt.

## Estructura

`src/models` accede directamente a PostgreSQL, `src/controllers` contiene la lógica de casos de uso, `src/routes` concentra rutas web y `src/views` son vistas EJS. Es un único proceso desplegable, por lo que implementa la macro-arquitectura de monolito modular.
