# Python_app

App de escritorio en Python (Tkinter + ttk) para la librería en línea: cliente de los 6 microservicios del
proyecto (login, books, users, authors, pedidos y pagos), que corren en la VM.

> **Estado:** login, Libros, Autores, Usuarios y Pedidos funcionan completos; Pagos muestra "En construcción"
> (su microservicio solo expone `/health` y `/metrics` todavía).
> Arquitectura general: [`docs/ARQUITECTURA.md`](../../docs/ARQUITECTURA.md).

## Características

- **Login y registro** contra el microservicio de auth. El JWT y el refresh token viven **solo en memoria**.
- **Sesión:** el JWT dura 20 minutos; la app lo renueva sola a los 17. Si un servicio responde 401 intenta un
  refresh y repite la petición; si no se puede, regresa al login. Cerrar sesión revoca el token en el servidor.
- **Menú lateral:** Inicio, Libros, Autores, Usuarios, Pedidos, Pagos, Configuración y Cerrar sesión.
- **Panel de semáforos** siempre visible con los 6 servicios: verde si `GET /health` responde 200 con
  `status: "ok"`, rojo en cualquier otro caso. Se revisa cada 10 s en hilos (la ventana nunca se congela), tiene
  botón **Revisar ahora** y, al pasar el mouse, muestra db, redis, tiempo de respuesta y última revisión.
- **Libros:** tabla con crear (POST), editar (PUT), editar parcial (PATCH), eliminar (DELETE) y buscar.
  Las escrituras requieren **rol admin**: con otro rol el servicio responde 403 y la app lo explica.
- **Autores** (microservicio authors): tabla con búsqueda y paginación y, al lado, los libros del autor
  seleccionado. El admin además crea, edita y elimina autores, busca libros por ISBN o título para relacionarlos y
  quita relaciones; para el cliente esas acciones no aparecen.
- **Libros → detalle:** al seleccionar un libro, la franja bajo la tabla muestra sus datos y sus autores según el
  servicio de autores.
- **Pedidos** (microservicio pedidos), tipo carrito y seguimiento:
  - *Comprar:* catálogo con el stock disponible, carrito con cantidades editables y total, y "Mis pedidos" con el
    estado en color (pendiente amarillo, pagado verde, enviado azul, entregado gris, cancelado y expirado rojo),
    el detalle de líneas e historial, y botones para editar, cancelar e "Ir a pagar" (deshabilitado hasta Pagos).
  - *Gestión* (admin): todos los pedidos con filtros; marcar enviado o entregado, cancelar y eliminar.
  - *Inventario* (admin): cargar, cambiar y quitar stock por libro.
- **Usuarios** (microservicio users):
  - *Admin:* panel de administración con búsqueda, filtros por rol y estado, paginación, alta y edición, y acciones
    sobre el usuario seleccionado: cambiar rol, restablecer contraseña, cambiar correo y desactivar/reactivar
    (con confirmación antes de las destructivas).
  - *Cliente:* solo "Mi perfil": editar su nombre, cambiar su contraseña (pidiendo la actual) y cambiar su correo.
  - Si el semáforo de Usuarios está en rojo la pantalla se deshabilita con un aviso y se reactiva sola al volver.
  - Cambiar tu propia contraseña, correo o rol cierra tus sesiones: la app te regresa al login y te explica por qué.
- **Configuración** (se guarda en `config.json`, sin tokens, y se aplica sin reiniciar):
  - IP de la VM y puerto de cada servicio.
  - Protocolo **HTTP (por defecto)** → `http://<IP>:<puerto>`, o **HTTPS** → `https://<IP>/api/<servicio>`.
  - Con HTTPS: casilla *Verificar certificado* y selector del archivo `.crt`, con advertencia visible si se desactiva.
  - Intervalo y timeout del semáforo.
  - *Probar conexión* (prueba los valores del formulario sin guardarlos) y *Restaurar valores por defecto*.
- **Log HTTP en consola** de cada petición y respuesta, **sin tokens ni contraseñas**.
- Mensajes claros para 401, 403, 409 y 503. Timeout de 5 segundos por petición.

## Estructura

```
Python_app/
├── main.py                 # ventana principal: barra, semáforos, menú lateral, pantallas, renovación del JWT
├── session.py              # JWT + refresh token en memoria
├── utils.py                # run_async: red en un hilo, resultado de vuelta con after()
├── requirements.txt
├── api/
│   ├── http_base.py        # cliente HTTP base (URL, timeout, Authorization, refresh ante 401, log, errores)
│   ├── auth_client.py      # login, register, refresh, logout
│   ├── books_client.py     # CRUD de libros
│   ├── users_client.py  authors_client.py  pedidos_client.py  pagos_client.py
│   └── health.py           # revisión de /health para el semáforo
├── screens/
│   ├── login_screen.py  register_screen.py  home_screen.py
│   ├── catalog_screen.py  book_form.py
│   ├── authors_screen.py         # Autores y sus libros
│   ├── users_screen.py           # Usuarios: administración (admin) / Mi perfil (cliente)
│   ├── pedidos_screen.py         # Pedidos: comprar, gestión e inventario
│   ├── config_screen.py
│   └── placeholder_screen.py     # "En construcción"
├── widgets/
│   ├── theme.py            # paleta, tipografía y estilos ttk
│   ├── semaforos.py  sidebar.py  tooltip.py
│   ├── dialogs.py          # formulario modal genérico
├── config/
│   └── settings.py         # config.json: carga, validación, URL de cada servicio
└── tests/
    └── test_cliente.py     # pytest (sin ventana): configuración, cliente HTTP, sesión, semáforo
```

`config.json` se crea al guardar la configuración. La primera vez hereda la IP que ya tenías en
`local_storage.json` (el archivo de la versión anterior, que ya no se usa).

## Ejecutar

```
cd apps/Python_app
pip install -r requirements.txt
python main.py
```

Lánzala desde una terminal para ver el log de peticiones y respuestas. Abre **Configuración** (desde el login o el
menú lateral), escribe la IP de la VM y pulsa **Guardar**: los semáforos deben ponerse en verde.

Pruebas:

```
pip install pytest
python -m pytest -q tests
```

## Requisitos previos

Los 6 microservicios levantados en la VM (`scripts/levantar_servicios.sh`, ver `VMComandos.md` en la raíz) y los
puertos 5000–5005 abiertos hacia tu máquina. Para iniciar sesión necesitas una cuenta confirmada; para modificar
libros, una con rol admin (el admin inicial se crea con `ADMIN_EMAIL` / `ADMIN_PASSWORD` del `.env` de users).

`instrucciones.txt` describe la versión anterior de la app (2 servicios); se conserva como referencia histórica.
