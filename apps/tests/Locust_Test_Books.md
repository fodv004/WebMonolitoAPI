1.- Crea un archivo de Python para Locust con una prueba de estrés
con 20 usuarios simultáneos para el microservicio books disponible en:
http://34.51.8.25:5001/books
http://34.51.8.25:5001/books?format=json
http://34.51.8.25:5001/books?format=xml

El microservicio books está protegido con JWT. Antes de las pruebas,
cada usuario debe iniciar sesión en el microservicio de login
(http://34.51.8.25:5000/login) para obtener el token y enviarlo en el
header Authorization: Bearer <token> en cada petición a books.
Las credenciales de prueba deben leerse de variables de entorno
(LOCUST_EMAIL y LOCUST_PASSWORD) y no estar escritas en el código.

2.- Identifica todos los endpoints del microservicio books (puedes
revisar http://34.51.8.25:5001/apidocs y el código en
apps/services/library_soap_service/app.py) y realiza pruebas con
todos. Incluye también http://34.51.8.25:5001/health.
Para endpoints que crean, modifican o borran datos (POST, PUT, PATCH,
DELETE), usa datos de prueba y borra lo que se cree para no ensuciar
la base de datos.

3.- Genera un archivo README.md en la carpeta con las instrucciones
para instalar y usar Locust con su interfaz web (GUI) en Windows 11,
usando como host http://34.51.8.25:5001, 20 usuarios y su spawn rate.

La IP actual de mi VM es: 34.51.8.25

4.- Documenta el código en el archivo locustfile.py
(no usar el nombre locust.py porque choca con la librería de Locust
y marca error al importarla).