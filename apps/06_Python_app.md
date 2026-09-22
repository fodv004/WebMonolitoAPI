Vas a crear una aplicación de escritorio utilizando meramente Python TK en donde el usuario, al acceder, podrá ingresar su usuario y contraseña la cual va a utilizar el microservicio de login. Si no cuenta con una cuenta registrada, existirá un botón para hacer el registro con los campos necesarios (Nombre, Apellido paterno, apellido materno, correo, contraseña). 

Quiero cambiar el envío de correos de mi microservicio de login (apps/services/login) para que mande correos reales usando Gmail por el puerto 587, en lugar de solo Mailpit.

Lo que necesito:

- Que se siga validando el dominio del correo con la consulta MX que ya tengo (dnspython) antes de registrar al usuario, para que acepte gmail, hotmail, outlook, udem.edu, los .com.mx, etc., y rechace dominios que no reciben correo.
- Que mailer.py mande el correo de confirmación por smtp.gmail.com en el puerto 587 con STARTTLS y login (contraseña de aplicación de Gmail).
- Que todo se configure desde el .env, nada de contraseñas en el código. Variables: MAIL_MODE, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
- Que con MAIL_MODE=gmail use Gmail, y con MAIL_MODE=mailpit siga funcionando como ahorita (localhost:1025, sin TLS ni login), para poder cambiar entre uno y otro.
- Actualiza config.py para leer esas variables y el .env.example con valores de ejemplo (sin contraseñas reales).
- Si falla el envío, que no truene el registro: que lo registre en el log y regrese un mensaje claro.
- No cambies las rutas ni la lógica de registro/login que ya funciona, solo lo del correo.

Archivos relevantes: mailer.py, config.py, validators.py, routes.py, .env.example.

Una vez haya ingresado, se debeará mostrar el catálogo de libro en donde se va a mostrar un semaforo de si los microservicios estan funcionando:
- rojo (no funciona)
- verde (si funciona)


Cada una de las card de los libros va a tener un botón de editar o actualizar, y eliminar. Además va a tener una sección de config y 
además va a tener el localstorage para la url y el endpoint. Tabmien habrá una opción de insertar y buscar

Los usuarios registrados pueden hacer crud como ya te mencione.

No hagas tests sobre el sistema, enfócate en que el funcionamiento sea correcto.

Python_app se debe de llamar la carpeta en donde almacenes toda la aplicaicón dentro de la carpeta de apps, además vas a generar un instrucciones.txt en donde menciones como correr todo en mi maquina.

