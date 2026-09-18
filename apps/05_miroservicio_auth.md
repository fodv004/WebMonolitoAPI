

# Microservicio de Autenticación

**Objetivo:** Desarrollar un microservicio idnependiente de autenticaicón y gestión básica de usuario para la plataforma de liberíar en línea existente. El servicio debera desarrollar se con pytho, flash, psycopg 2 y postgresql, utilizar la base de datos actual del proeycot y exponer sus repuestas tanto en xml como en json.

## Requerimientos funcionales

El microservicio deberá implementar las siguientes operaciones:

| Método | Endpoint | Función |
|---|---|---|
| POST | /register  | Registrar un nuevo usuario |
| POST | /login | Autenticar al usuario e iniciar sesión |
| POST | /logout | Cerrar la sesión |
| GET | /session | Consultar si existe una sesión autenticada |
| GET | /health | Verificar el estado del microservicio y PostgreSQL |

Todos los endpoints deberán soportar `?format=xml` y `?format=json`; si no se especifica el parámetro `format`, XML será el formato predeterminado. Por ejemplo: `POST /login` y `POST /login?format=xml` deberán responder XML, mientras que `POST /login?format=json` deberá responder JSON.

El registro deberá solicitar:

- nombre
- apellido paterno
- apellido materno
- email
- password

El correo deberá validarse antes de registrarse y deberá ser único. Además, al completar el registro, el sistema deberá enviar un correo de confirmación al usuario utilizando Mailpit como servidor de correo propio de la instancia (no utilizar pop de Gmail ni servicios de terceros). El microservicio se conectará a Mailpit vía SMTP en localhost, generará un token único de confirmación asociado al usuario, y enviará un correo a la dirección registrada con un link de confirmación (`/confirm?token=...`). El correo enviado deberá poder visualizarse en la interfaz web de Mailpit como evidencia de que el envío funcionó correctamente. Al dar clic en el link de confirmación, el sistema deberá validar el token, actualizar el estado del usuario de `pendiente` a `confirmado`, y redirigir al usuario a una página que confirme visualmente que su cuenta quedó activada. La contraseña nunca deberá almacenarse en texto plano. El sistema almacenará únicamente un hash seguro de la contraseña.

La autenticación deberá verificar las credenciales contra PostgreSQL y, cuando sean correctas, crear una sesión del lado de Flask que permita identificar al usuario en solicitudes posteriores.

## Requerimientos de integración y despliegue

- Crea el microservicio en el directorio `apps/services/login`
- Modifica e integra las tablas necesarias a la base de datos `library`, normalizando la tabla usuario para incluir apellido paterno y materno, y verifica que estos cambios se reflejen y sean consistentes en todo el monolito existente (WebMonolitico) que consume esta tabla.
- Además se tiene que reestructurar la base de datos y su diseño. Vamos a necesitar reestructurar la mayoría de cosas porque vamos a tener el microservicio de books, la aplicación de Electron y ahora el de auth, por lo que algún cambio va a chocar con el otro posiblemente. En adición, tenemos que tomar en cuenta que los nuevos endpoints estén considerados igual para que no choquen entre microservicios.
- Despliega el microservicio en el puerto 5000
- Utiliza Swagger para documentar los endpoints en XML y JSON
- Valida que todos los endpoints funcionen correctamente

Recuerda: no necesitamos almacenar la contraseña dos veces ni crear una tabla exclusivamente para passwords. `password_hash` pertenece naturalmente a la cuenta de usuario.

Los servicios tienen que ser independientes.

0- Antes que cualquier otro cambio, normalizar la tabla usuario de la base de datos library: migrar el/los campos de nombre existentes hacia columnas atómicas nombre, apellido_paterno y apellido_materno (primera forma normal), sin perder los datos de usuarios ya registrados. Este cambio debe escribirse como un script de migración SQL versionado, guardado en WebMonolito/db/cambio_usuarios.sql, que incluya tanto el ALTER TABLE para agregar las columnas nuevas como el UPDATE para migrar los datos existentes antes de eliminar cualquier columna vieja. Este script debe ejecutarse y validarse primero, antes de construir el microservicio de auth, ya que tanto el monolito como el nuevo microservicio dependerán de esta estructura.

Además genera un .txt en /EG4 con las instrucciones de como ejecutar todo y además pasos para poder verificar el funcionamiento de los servicios de los microservicios y de electron.