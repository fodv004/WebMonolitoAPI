1- Escribe un microservicio en Flask (no usar blueprints) con una conexión a la base de datos de Postgres para generar
endpoints y realizar las operaciones CRUD de libros. Depositalo en /apps/services/soap.

2- Usa como referencia el esquema de base de datos /data/libreria_schema.sql y el diseño del XML definido en /apps/services/soap/library.xml

3- El microservicio debe de mostrar otdos los libros, un libro, buscar por atributos, modificar un libro, borrar un libro y actualizar un libro

4- Toma en condiseración el problema CROS ya que este servicio será accedido mediatne clientes fuera del dominio

5- Considera los siguientes datos de Postgres: db: library, usuario: library_user y password: library666. Usa las varibles de entorno .env para no exponer las credenciales del servicio