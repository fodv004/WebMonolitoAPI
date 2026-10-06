Proyecto Library (monorepo WebMonolitoAPI). Ya están completas las PARTES 1 a 4 (ambiente base, users, authors y pedidos). Antes de empezar, lee docs/ARQUITECTURA.md, docs/REDIS.md, apps/services/common y la estructura de apps/services/pedidos. Usa el módulo común para autenticación, Redis, health, métricas, errores y logs. No modifiques otros servicios salvo lo indicado.

No tienes acceso a la VM. Solo trabaja sobre el código del repositorio. Todo lo que se deba ejecutar en la VM (migraciones, scripts, systemd, pruebas con curl) entrégamelo como comandos para que yo los corra y te comparta el resultado.

NO ejecutes ningún tipo de prueba: ni pytest, ni scripts, ni la app, ni comandos que levanten servicios o se conecten a bases de datos o Redis. Escribe los archivos de prueba, pero no los corras. Yo los ejecuto y te comparto el resultado.

Datos reales de la VM que debes respetar:
- La base de datos se llama library (no library_db) y pagos se conecta con library_user.
- La IP pública de la VM es 34.51.0.253.

ESTA ES LA PARTE 5: microservicio pagos (apps/services/pagos, puerto 5005) y su pantalla en la app Tk. Es un pago SIMULADO, sin pasarela real.

Responsabilidad: registrar pagos y actualizar el estado de los pedidos.

Base de datos (migración idempotente en apps/services/pagos/sql/, registrada en schema_migraciones):
- pagos (id, pedido_id, user_id, monto, metodo, estado, referencia, ultimos4, idempotency_key UNIQUE, sincronizado, notas, activo, created_at, updated_at)
- metodo: TARJETA_SIMULADA, TRANSFERENCIA o EFECTIVO
- estado: APROBADO, RECHAZADO o REEMBOLSADO
- Nunca guardar ni registrar en logs el número completo de tarjeta ni el CVV; solo los últimos 4 dígitos.

Endpoints (todas las lecturas requieren JWT):
- POST /pagos (JWT, dueño del pedido), con el header Idempotency-Key. Flujo:
  1. Revisar la llave en Redis (pago:idem:<key>, TTL 24 h) y como respaldo en la columna UNIQUE. Si ya existe, devolver el mismo pago sin cobrar otra vez.
  2. Consultar GET {PEDIDOS_URL}/pedidos/internal/{id} con X-Internal-Key: el pedido debe estar en PENDIENTE_PAGO y ser del user_id del token. El monto sale del pedido, nunca del cliente.
  3. Simular la aprobación: rechazar tarjetas que terminen en 0000.
  4. Si se aprueba, PATCH {PEDIDOS_URL}/pedidos/internal/{id}/estado a PAGADO. Si pedidos no responde, guardar sincronizado=false y reintentar con una tarea en segundo plano que use el lock lock:pagos:sync (SET NX EX 30).
  5. Usar el lock pago:lock:<pedido_id> (SET NX EX 30) durante todo el proceso. Si Redis está caído → 503.
- GET /pagos (cliente: solo los suyos; admin: todos, con filtros ?estado=&metodo=&user_id=)
- GET /pagos/{id} y GET /pagos/pedido/{pedido_id} (dueño o admin)
- PATCH /pagos/{id} (JWT + admin): solo referencia y notas, nunca el monto
- POST /pagos/{id}/reembolso (JWT + admin): pago a REEMBOLSADO y pedido a CANCELADO, con liberación de stock mediante el endpoint interno de pedidos
- DELETE /pagos/{id} (JWT + admin): solo pagos RECHAZADO, borrado lógico (activo=false)
- Revisa en apps/services/pedidos los nombres exactos de los endpoints internos y de los estados; si alguno difiere de lo descrito aquí, usa el que ya existe en pedidos y dímelo.
- Agrega las claves nuevas (pago:idem, pago:lock, lock:pagos:sync) a common/redis_keys.py y a docs/ARQUITECTURA.md.

App Tk, pantalla Pagos (diseño tipo caja o checkout, distinto a las demás pantallas):
- Selector de pedidos pendientes del usuario y monto en grande (solo lectura).
- Método de pago y campo de tarjeta enmascarado que solo aparece con TARJETA_SIMULADA.
- Botón "Pagar" que genera el Idempotency-Key con uuid4 y lo reutiliza si se reintenta el mismo pago.
- Comprobante con referencia y últimos 4 dígitos.
- Historial de pagos con filtros.
- Admin: reembolsar, corregir referencia y notas, y eliminar pagos rechazados.
- Activar el botón "Ir a pagar" de la pantalla Pedidos para que abra esta pantalla con el pedido seleccionado.
- Si el semáforo de pagos está en rojo, deshabilitar la pantalla con un aviso.

Pruebas (solo escribirlas, NO ejecutarlas) con pytest y fakeredis en apps/services/pagos/tests: pago aprobado y rechazado, idempotencia (doble envío = un solo pago), monto manipulado ignorado, pago de un pedido ajeno (403), lock concurrente, pedidos caído con sincronización posterior, reembolso, permisos 401 y 403, y que ningún log contenga números de tarjeta.

Al terminar entrégame:
1. La lista de archivos creados o modificados.
2. Las migraciones nuevas y qué tablas crean o modifican.
3. Los comandos para correr las pruebas en mi computadora (Windows, PowerShell).
4. Los comandos para desplegar en la VM (respaldo, git pull, levantar_servicios.sh).
5. Los comandos curl para comprobar: crear un pedido, pagarlo y verlo en PAGADO; reenviar el mismo pago sin que se duplique; pagar con una tarjeta terminada en 0000 y ver el rechazo; reembolsar como admin y ver el pedido en CANCELADO con el stock liberado.
6. Actualiza docs/ARQUITECTURA.md con los endpoints nuevos.