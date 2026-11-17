En el monorepo EG4, las apps cliente apps/Python_app, apps/Electron_app y apps/JavaDesktop_app
hoy llaman directo a los microservicios por puerto (5000 login, 5001 books, 5002 users,
5003 authors, 5004 pedidos, 5005 pagos, 5900 tracking/WebSocket).

Ahora todo debe pasar por un API Gateway (nginx) en http://34.51.84.143:8080 con este mapeo:
- /catalogo/api/login, /register, /confirm, /refresh, /logout, /session -> login
- /catalogo/api/books, /formats, /cloud-concepts, /soap -> books
- /catalogo/api/users, /roles -> users
- /catalogo/api/authors -> authors
- /catalogo/api/pedidos, /inventario -> pedidos
- /catalogo/api/pagos -> pagos
- /catalogo/api/envios -> tracking
- WebSocket: ws://34.51.84.143:8080/catalogo/api/ws -> tracking

Tareas:
1. En cada app, reemplaza todas las URLs por puerto por una sola URL base del gateway
   (http://34.51.84.143:8080/catalogo/api), definida en un solo lugar configurable
   (archivo de config o variable de entorno), con el prefijo correcto en cada llamada.
2. El WebSocket de tracking debe usar ws://34.51.84.143:8080/catalogo/api/ws.
3. No toques apps/WebMonolito ni apps/services; el monolito sigue llamando directo.
4. No cambies la estructura de carpetas existente.
5. Al final dame una lista de archivos modificados y qué cambió en cada uno.