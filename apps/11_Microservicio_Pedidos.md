_Proyecto Library (monorepo WebMonolitoAPI). Ya están completas las PARTES 1 a 3. Antes de empezar, lee docs/ARQUITECTURA.md y apps/services/common. No modifiques otros servicios salvo lo indicado.

ESTA ES LA PARTE 4: microservicio pedidos (apps/services/pedidos, puerto 5004) y su pantalla en la app Tk.

Responsabilidad: crear y gestionar pedidos, líneas de pedido, stock y estados.

Base de datos:
- inventario (isbn PK, stock_disponible, stock_reservado, updated_at)
- pedidos (id, user_id, estado, total, created_at, updated_at, expira_en)
- pedido_lineas (id, pedido_id, isbn, titulo, cantidad, precio_unitario, subtotal); el título y el precio se copian de books al crear el pedido
- pedido_historial (id, pedido_id, estado_anterior, estado_nuevo, actor, fecha)

Estados permitidos (cualquier otra transición → 409):
- PENDIENTE_PAGO → PAGADO | CANCELADO | EXPIRADO
- PAGADO → ENVIADO | CANCELADO
- ENVIADO → ENTREGADO

Endpoints (todas las lecturas de pedidos requieren JWT):
- POST /pedidos (JWT): body {"lineas": [{"isbn", "cantidad"}]}. El user_id sale del token. Valida libros y precios en books, y el usuario en GET {USERS_URL}/users/internal/{id}. Reserva el stock en una transacción con SELECT ... FOR UPDATE; sin stock suficiente → 409 indicando el ISBN.
- GET /pedidos (cliente: solo los suyos; admin: todos, con filtros ?estado=&user_id=)
- GET /pedidos/{id} (dueño o admin), con líneas e historial
- PUT /pedidos/{id} y PATCH /pedidos/{id}/lineas (dueño, solo en PENDIENTE_PAGO), reajustando la reserva de stock
- PATCH /pedidos/{id}/cancelar (dueño en PENDIENTE_PAGO; admin en cualquier estado cancelable): libera el stock
- PATCH /pedidos/{id}/estado (JWT + admin): ENVIADO y ENTREGADO
- DELETE /pedidos/{id} (JWT + admin): solo CANCELADO o EXPIRADO, borrado lógico
- GET /pedidos/internal/{id} y PATCH /pedidos/internal/{id}/estado (X-Internal-Key): para uso del servicio pagos
- GET /inventario y GET /inventario/{isbn} (públicos); POST, PUT y DELETE de /inventario (JWT + admin)

Redis:
- Al crear un pedido, guardar pedido:reserva:<id> con TTL de 15 minutos.
- Tarea en segundo plano cada minuto con el lock lock:pedidos:expirar (SET NX EX 30): pasa a EXPIRADO los pedidos PENDIENTE_PAGO vencidos y libera su stock. PostgreSQL es la fuente de verdad.

App Tk, pantalla Pedidos (diseño tipo carrito y seguimiento):
- Izquierda: catálogo con stock disponible y botón agregar.
- Centro: carrito con cantidades editables y total.
- Derecha: "Mis pedidos" con el estado en color (PENDIENTE_PAGO amarillo, PAGADO verde, ENVIADO azul, ENTREGADO gris, CANCELADO y EXPIRADO rojo), detalle de líneas e historial, y botones editar, cancelar e "Ir a pagar" (este último deshabilitado hasta la Parte 5).
- Admin: pestañas "Gestión" (cambiar el estado de cualquier pedido) e "Inventario" (CRUD de stock).

Pruebas con pytest: creación con reserva, falta de stock, transiciones inválidas, cancelación con liberación de stock, expiración, permisos, concurrencia básica sobre el mismo ISBN.

Comprobación de la Parte 4:
- Cargar stock como admin, crear un pedido como cliente y ver que el stock disponible baja.
- Cancelar el pedido y ver que el stock regresa.
- Para probar la expiración, permitir configurar la reserva en 1 minuto con una variable de entorno y ver el pedido pasar a EXPIRADO.
- Actualiza docs/ARQUITECTURA.md.