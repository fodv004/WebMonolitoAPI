# Contexto

Este proyecto tiene tres piezas: dos microservicios y una aplicación de escritorio.

- `login`: microservicio de autenticación (rutas `/login` y `/register`).
- `Library_soap_service`: microservicio del catálogo de libros (rutas `/api/books`).
- `/Python_app`: aplicación de escritorio en Tkinter que consume ambos servicios.

Antes de modificar nada, revisa el código de cada pieza y confirma el framework (Flask o Express), cómo se identifican los libros en las rutas actuales (`isbn` o `id`) y qué funciones CRUD ya tiene la app de escritorio. No cambies rutas, esquemas de base de datos ni formatos de respuesta existentes.

# Objetivo

Proteger las operaciones de escritura del servicio de libros exigiendo un JWT válido emitido por el servicio `login`, y adaptar la app de escritorio para usar ese JWT y registrar en consola todo el tráfico HTTP.

# 1. Servicio `login`

- `POST /login` y `POST /register` se mantienen públicos.
- `POST /login` devuelve en JSON un JWT firmado cuando las credenciales son correctas.
- Usa HS256 y una librería estándar (PyJWT en Flask o jsonwebtoken en Express).
- Claims del payload: `user_id`, `email`, `iat`, `exp`.
- Expiración: 1 hora.
- El secreto se lee de la variable de entorno `JWT_SECRET`. No lo dejes escrito en el código. Si la variable no existe, el servicio debe fallar al arrancar con un mensaje claro.

# 2. Servicio `Library_soap_service` (libros)

Rutas públicas (sin token):
- `GET /api/books`
- `GET /api/books/{isbn}`

Rutas protegidas (requieren `Authorization: Bearer <token>`):
- `POST /api/books`
- `PUT /api/books/{id}`
- `PATCH /api/books/{id}`
- `DELETE /api/books/{id}`

Implementa `PATCH /api/books/{id}`, que hoy no existe:
- Actualización parcial: solo se modifican los campos enviados en el body.
- Respeta las mismas validaciones y el mismo formato de respuesta que `PUT`.
- Devuelve 404 si el libro no existe.

Middleware o decorador JWT:
- Lee el header `Authorization: Bearer <token>` y valida la firma con el mismo `JWT_SECRET` que usa `login`.
- Aplícalo únicamente a las rutas protegidas.
- Sin header, o con formato incorrecto: `401 Unauthorized`.
- Token con firma inválida o expirado: `403 Forbidden`.
- Las respuestas de error van en JSON con un mensaje claro.

Nota sobre identificadores: usa `{isbn}` o `{id}` en cada ruta según lo que el código actual ya use. Si hay inconsistencia, documéntala en la respuesta final sin romper nada.

# 3. Aplicación `/Python_app` (Tkinter)

Autenticación:
- Al hacer login correcto, guarda el JWT en memoria durante la sesión (no en disco).

Peticiones protegidas:
- Adjunta automáticamente `Authorization: Bearer <token>` en POST, PUT, PATCH y DELETE hacia el servicio de libros.
- Los GET no necesitan token.
- Agrega en la interfaz la función y el botón para PATCH (actualización parcial) si no existen.

Manejo de errores en la interfaz:
- Si llega 401 o 403, muestra un mensaje al usuario indicando que la sesión no es válida o expiró y pide iniciar sesión de nuevo.

Diseño visual (mejora de la interfaz):
- La interfaz actual es muy básica. Rediséñala para que se vea moderna y ordenada, sin cambiar la lógica ni las funciones existentes.
- Usa solo `tkinter` y `ttk` (con `ttk.Style`), sin librerías nuevas.
- Paleta de colores definida en constantes al inicio del archivo (fondo, color principal, texto, éxito, advertencia, peligro).
- Tipografía consistente (por ejemplo Segoe UI o Helvetica), con título más grande y texto normal legible.
- Barra superior con el nombre de la aplicación y un indicador de sesión ("Sesión iniciada como <email>" o "Sin sesión").
- Pantalla de login centrada, con campos alineados, márgenes y botón principal destacado.
- Tabla de libros (`Treeview`) con encabezados con color, filas alternadas y selección resaltada.
- Botones con color según su función: crear (verde), editar/PUT (azul), PATCH (naranja), eliminar (rojo), con efecto hover y espaciado uniforme.
- Formularios con etiquetas alineadas, padding y campos del mismo ancho.
- Barra de estado inferior que muestre el último resultado (por ejemplo "201 Libro creado" o "403 Sesión expirada") con color verde o rojo según el caso.
- Los mensajes de error 401 y 403 deben verse claramente diferenciados del resto (color de peligro).
- La ventana debe ser redimensionable y mantener los elementos acomodados.

# 4. Logging en consola

Centraliza las peticiones HTTP en una sola función o clase (con `requests`) que imprima en la consola de Python, para cada interacción:

Petición saliente:
- Método HTTP y URL completa.
- Headers, con el token Bearer visible.
- Body o payload.

Respuesta entrante:
- Status code (200, 201, 401, 403, etc.).
- Headers de la respuesta.
- Body de la respuesta.

Usa un formato legible con separadores claros entre petición y respuesta.

# 5. Entregables

Modifica los archivos directamente en el proyecto (no me pegues el código completo en la respuesta). Al terminar, crea un archivo `instrucciones.txt` en la raíz del proyecto con estas secciones:

# 5. Entregables

No ejecutes pruebas, no arranques servicios ni la app, y no hagas peticiones de verificación. Solo modifica los archivos y crea los dos documentos siguientes. Yo validaré todo manualmente y tomaré capturas.

Modifica los archivos directamente en el proyecto (no me pegues el código completo en la respuesta). Al terminar, crea en la raíz del proyecto dos archivos de texto plano, en español y sin formato Markdown:

## Archivo 1: `instrucciones.txt`, con estas secciones en este orden

1. INSTALAR DEPENDENCIAS (esto va primero)
   - Explica que JWT no viene instalado y que se agrega como librería en cada servicio.
   - Comando exacto para cada servicio y para la app de escritorio, indicando dónde se ejecuta (por ejemplo `pip install PyJWT` en los servicios Flask, `npm install jsonwebtoken` en los servicios Express, `pip install requests` en /Python_app).
   - Si el proyecto usa `requirements.txt`, `package.json` o Docker, indica qué archivo actualizaste y cómo reconstruir.
   - Advertencia de instalar `PyJWT` y no `jwt`.

2. CONFIGURAR JWT_SECRET
   - Cómo definir `JWT_SECRET` con el mismo valor en ambos servicios, para Windows (`set` o `$env:`), Mac/Linux (`export`) y `.env` o docker-compose si el proyecto ya los usa.
   - Aviso de que si el valor es distinto entre servicios, el servicio de libros va a responder 403.

3. CAMBIOS REALIZADOS
   - Lista por servicio (`login`, `Library_soap_service`, `/Python_app`) con el nombre de cada archivo modificado o creado y una línea que diga qué cambió (middleware JWT, emisión del token, endpoint PATCH, manejo del token en el cliente, logger, etc.).

3. CÓMO ARRANCAR CADA SERVICIO (ya con las dependencias instaladas)
   - `login`: comando exacto, puerto y URL base.
   - `Library_soap_service`: comando exacto, puerto y URL base.
   - `/Python_app`: comando exacto, indicando que se debe lanzar desde una terminal para poder ver los logs.
   - El orden recomendado de arranque y cómo verificar que cada servicio está arriba.

## Archivo 2: `pruebas.txt`

Incluye solo las pruebas más importantes para demostrar que los cambios funcionan. Para cada una indica: número y nombre, comando curl completo (con las rutas y puertos reales del proyecto), resultado esperado (status code y body) y qué debo capturar en pantalla. Las pruebas son:

1. Login correcto: devuelve 200 y un token JWT.
2. Login con credenciales incorrectas: devuelve error y no token.
3. GET /api/books sin token: 200 (público).
4. GET /api/books/{isbn} sin token: 200 (público).
5. POST /api/books sin token: 401.
6. POST /api/books con header mal formado (sin la palabra Bearer): 401.
7. POST /api/books con token inválido (firma alterada): 403.
8. POST /api/books con token expirado: 403. Incluye un comando de una línea en Python para generar un token ya expirado usando el mismo JWT_SECRET.
9. POST /api/books con token válido: 200 o 201.
10. PUT /api/books/{id} con token válido: 200.
11. PATCH /api/books/{id} con token válido enviando solo un campo: 200, y verificar con un GET que solo ese campo cambió.
12. PATCH /api/books/{id} sin token: 401.
13. DELETE /api/books/{id} sin token: 401, y luego con token válido: 200.
14. App Tkinter: hacer login, crear y editar un libro y mostrar en la terminal los bloques del log (método, URL, header Authorization: Bearer, body, status y respuesta).
15. App Tkinter: forzar un 401 o 403 (por ejemplo con token expirado) y mostrar el mensaje en la interfaz junto con el log en consola.

Al inicio de `pruebas.txt` incluye cómo guardar el token en una variable de terminal para reutilizarlo en los comandos curl (Windows y Mac/Linux). Usa las rutas, puertos y comandos reales del proyecto, no valores inventados.