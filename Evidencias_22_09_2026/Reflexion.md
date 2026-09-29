Lo que más se me complicó de esta actividad no fue hacer la interfaz, sino lograr que la app de escritorio se conectara 
bien con los microservicios que tengo en la VM. Al principio ni siquiera podía correr el servicio de login porque me 
marcaba que faltaba bcrypt, y era porque no había activado el entorno virtual donde tenía instaladas las dependencias.

Ya con los servicios corriendo, la app me daba un error raro de Python en utils.py que escondía el error real. 
Al corregirlo vi que la app estaba buscando los servicios en localhost y no en la IP de la VM, así que lo cambié 
desde la pantalla de configuración sin tocar el código. Después me salía timeout, y para encontrar la causa fui 
descartando cosas. Revisé que el servicio estuviera escuchando en el puerto 5000, que el health respondiera dentro 
de la VM y que la IP externa fuera la correcta. Como todo eso estaba bien, el problema era el acceso desde fuera y 
lo resolví abriendo los puertos en el firewall de la VM. También el link de confirmación del correo apuntaba a localhost, 
y lo arreglé cambiando PUBLIC_BASE_URL en el .env. Además tuve que mandar los correos por Gmail en el puerto 587 porque GCP bloquea el 25.

Cuando un microservicio deja de responder, mi app no se cierra, el semáforo se pone en rojo y muestra un mensaje que 
se entiende. Localmente todo funciona con localhost, pero en remoto hay que cuidar la IP, que cambia al reiniciar la 
VM, el firewall y los links que genera el servicio.

Aprendí que el cliente nunca toca la base de datos. Todo pasa por los endpoints y el microservicio es el único que 
habla con PostgreSQL.